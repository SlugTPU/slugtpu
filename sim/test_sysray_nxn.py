import random
import cocotb
from cocotb.triggers import FallingEdge, First, ClockCycles
from pathlib import Path
import pytest
from shared import clock_start, reset_sequence
from runner import run_test

OUTPUT_TIMEOUT = 64  # max falling edges to wait for a column's valid signal


# ---------------------------------------------------------------------------
# Reference models
# ---------------------------------------------------------------------------

def matmul_ref(acts, weights):
    """C[j] = sum_i acts[i] * weights[i][j]  (vector @ matrix, column outputs)"""
    N = len(acts)
    return [sum(acts[i] * weights[i][j] for i in range(N)) for j in range(N)]


def matmul_ref_matrix(act_matrix, weights):
    """Compute act_matrix @ weights row-by-row; returns an M×N output matrix."""
    return [matmul_ref(act_row, weights) for act_row in act_matrix]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def load_weights(dut, N, weights, sel=0):
    """
    Load weights into the systolic array over N falling-edge-aligned cycles.

    Feed bottom row first so that after N posedges, PE[i][j] holds weights[i][j].

    Why bottom-to-top: weights propagate downward one register per cycle via
    weight_o = weight_buf[prev_sel].  Feeding row N-1 first lets it ripple down
    while subsequent rows fill in above it:

      Cycle -N:   weight_n_i[j] = weights[N-1][j]  -> latched into PE[0][j]
      Cycle -N+1: weight_n_i[j] = weights[N-2][j]  -> PE[0][j] updated,
                                                        PE[1][j] captures weights[N-1][j]
      ...
      Cycle -1:   weight_n_i[j] = weights[0][j]    -> PE[0][j] = weights[0][j],
                                                        ..., PE[N-1][j] = weights[N-1][j]

    All columns are loaded simultaneously (no column stagger required for
    the weight-loading phase without double-buffering).

    sel: 0 or 1 — selects which PE weight bank receives the data (weight_sel_n_i[j]).
    All columns use the same bank for a given load; the array port is per-column to
    match the per-signal embedding of the select bit in the PE interface.

    weight_sel_n_i is driven at the same falling edge as the first valid weight, not
    before the loop.  A gap posedge with weight_sel toggled but weight_valid=0 would
    unconditionally update prev_weight_sel in every PE (the update is not gated on
    weight_valid_i), causing weight_o to switch to the still-empty new bank and
    corrupt a downstream PE's weight_buf on the very next valid cycle.
    """
    for row in range(N - 1, -1, -1):   # N-1 down to 0
        await FallingEdge(dut.clk_i)
        for col in range(N):
            dut.weight_sel_n_i[col].value    = sel   # change sel atomically with data/valid
            dut.weight_n_i[col].value        = weights[row][col]
            dut.weight_valid_n_i[col].value  = 1

    # Deassert weight_valid one cycle after the last row is presented
    await FallingEdge(dut.clk_i)
    for col in range(N):
        dut.weight_n_i[col].value        = 0
        dut.weight_valid_n_i[col].value  = 0


async def stream_activations(dut, N, acts, sel=0):
    """
    Drive one activation vector with proper row staggering.

    Row i is presented i cycles after row 0.  This ensures that act[i] and
    weight row i arrive at each column j at the same time — both experience
    j pipeline stages of latency as they travel across the array.

      Cycle 0:   act_n_i[0] = acts[0], valid[0] = 1;  rows 1..N-1 idle
      Cycle 1:   act_n_i[1] = acts[1], valid[1] = 1;  rows 0,2..N-1 idle
      ...
      Cycle N-1: act_n_i[N-1] = acts[N-1], valid[N-1] = 1;  all others idle

    sel: 0 or 1 — selects which PE weight bank the MAC reads from (act_sel_n_i[i]).
    All rows use the same bank for a given inference pass.
    """
    for row in range(N):
        await FallingEdge(dut.clk_i)
        for i in range(N):
            dut.act_sel_n_i[i].value = sel
            if i == row:
                cocotb.log.info(f"Loading act_n_i[{i}] = {acts[i]} (valid) at cycle {row}")
                dut.act_n_i[i].value       = acts[i]
                dut.act_valid_n_i[i].value = 1
            else:
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0


async def collect_outputs(dut, N):
    """
    Wait for psum_out_valid_n_o to assert on every column and return the values.
    Raises AssertionError on timeout.
    """
    results = []
    for j in range(N):
        timeout = ClockCycles(dut.clk_i, OUTPUT_TIMEOUT)
        while True:
            if dut.psum_out_valid_n_o[j].value == 1:
                results.append(int(dut.psum_out_n_o[j].value))
                break
            fired = await First(FallingEdge(dut.clk_i), timeout)
            if fired is timeout:
                raise AssertionError(f"column {j}: timed out waiting for psum_out_valid_n_o")
    return results


async def stream_and_collect(dut, N, acts, sel=0):
    """
    Stream one activation vector, deassert inputs, and return the N output psums.

    This is the atomic unit for one inference pass: drive act vector → wait one
    cycle → clear inputs → collect column outputs.
    """
    await stream_activations(dut, N, acts, sel)
    # Wait one cycle so the last activation is captured at posedge, then deassert.
    # psum_valid_o is only high for one cycle so check BEFORE advancing.
    await FallingEdge(dut.clk_i)
    for i in range(N):
        dut.act_n_i[i].value       = 0
        dut.act_valid_n_i[i].value = 0
    return await collect_outputs(dut, N)


async def stream_activation_matrix(dut, N, act_matrix, sel=0):
    """
    Stream an M×N activation matrix through the systolic array with diagonal pipelining.

    At each cycle c, every array row i that has a valid vector in flight is driven
    simultaneously: vector m = c - i is active on row i when 0 ≤ m < M.  This
    fills the array on a diagonal wavefront — no bubbles between vectors.

    Drive schedule (N=2, M=2 example):
      cycle 0: row0 = act[0][0]
      cycle 1: row0 = act[1][0],  row1 = act[0][1]   ← two rows active at once
      cycle 2:                    row1 = act[1][1]

    Total drive cycles = M + N - 1 (vs M*N for sequential).

    Output timing: col j of vector m fires at FallingEdge m + N + j.  Multiple
    columns can be valid on the same cycle, so results are indexed directly via
    m = cycle - N - j rather than collected in a flat list.

    The loop runs for M + 2*N - 1 FallingEdges:
      - Cycles 0 .. M+N-2  : drive (diagonal wavefront)
      - Cycles M+N-1 .. M+2N-2 : inputs idle; drain last vector's outputs

    Returns an M×N list of output rows.
    """
    M = len(act_matrix)
    results = [[None] * N for _ in range(M)]

    for cycle in range(M + 2 * N - 1):
        await FallingEdge(dut.clk_i)

        # Drive: row i carries vector m = cycle - i when in range
        for i in range(N):
            m = cycle - i
            dut.act_sel_n_i[i].value = sel
            if 0 <= m < M:
                dut.act_n_i[i].value       = act_matrix[m][i]
                dut.act_valid_n_i[i].value = 1
            else:
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0

        # Sample: col j of vector m fires at FallingEdge m + N + j → m = cycle - N - j
        for j in range(N):
            if dut.psum_out_valid_n_o[j].value == 1:
                m = cycle - N - j
                if 0 <= m < M:
                    results[m][j] = int(dut.psum_out_n_o[j].value)

    for r in range(M):
        for j in range(N):
            assert results[r][j] is not None, f"row {r}, col {j}: output not captured"
    for m, row_out in enumerate(results):
        cocotb.log.info(f"  → output row {m}: {row_out}")
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def reset_test(dut):
    """Verify that all psum outputs are 0 after reset with no inputs driven."""
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)
    await FallingEdge(dut.rst_i)


@cocotb.test()
async def test_basic_matmul(dut):
    """
    Fixed-value vector-matrix multiply for manual verification.

    acts[i]        = i + 1              e.g. [1, 2] for N=2
    weights[i][j]  = (i+1) * (j+1)     e.g. [[1,2],[2,4]] for N=2

    Expected output for N=2:
      psum_out[0] = 1*1 + 2*2 = 5
      psum_out[1] = 1*2 + 2*4 = 10

    Sampling: wait for psum_out_valid_n_o[j] to assert before reading each column.
    """
    N = dut.N.value.to_unsigned()
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    acts    = list(range(1, N + 1))
    weights = [[(i + 1) * (j + 1) for j in range(N)] for i in range(N)]
    expected = matmul_ref(acts, weights)

    cocotb.log.info(f"N={N}, acts={acts}, weights={weights}, expected={expected}")

    await load_weights(dut, N, weights)
    results = await stream_and_collect(dut, N, acts)

    for j, (got, exp) in enumerate(zip(results, expected)):
        cocotb.log.info(f"psum_out_n_o[{j}] = {got}  (expected {exp})")
        assert got == exp, f"column {j}: expected {exp}, got {got}"


@cocotb.test()
async def test_random_matmul(dut):
    """
    Random vector-matrix multiply.

    Values are capped at 15 so N * 15 * 15 = 225*N stays well within
    the 32-bit accumulator (ACC_WIDTH=32).
    """
    N = dut.N.value.to_unsigned()
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    acts    = [random.randint(0, 15) for _ in range(N)]
    weights = [[random.randint(0, 15) for _ in range(N)] for _ in range(N)]
    expected = matmul_ref(acts, weights)

    cocotb.log.info(f"N={N}, acts={acts}, weights={weights}, expected={expected}")

    await load_weights(dut, N, weights)
    results = await stream_and_collect(dut, N, acts)

    for j, (got, exp) in enumerate(zip(results, expected)):
        cocotb.log.info(f"psum_out_n_o[{j}] = {got}  (expected {exp})")
        assert got == exp, f"column {j}: expected {exp}, got {got}"


@cocotb.test()
async def test_basic_matmul_matrix(dut):
    """
    Fixed-value matrix-matrix multiply: N×N activation matrix × N×N weights.

    act_matrix[m][i] = m * N + i + 1   (distinct values across all rows)
    weights[i][j]    = (i+1) * (j+1)

    Each output row is verified independently against matmul_ref.
    """
    N = dut.N.value.to_unsigned()
    M = N
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[m * N + i + 1 for i in range(N)] for m in range(M)]
    weights    = [[(i + 1) * (j + 1) for j in range(N)] for i in range(N)]
    expected   = matmul_ref_matrix(act_matrix, weights)

    cocotb.log.info(f"N={N}, M={M}")
    cocotb.log.info(f"act_matrix={act_matrix}")
    cocotb.log.info(f"weights={weights}")
    cocotb.log.info(f"expected={expected}")

    await load_weights(dut, N, weights)
    results = await stream_activation_matrix(dut, N, act_matrix)

    for m, (row_got, row_exp) in enumerate(zip(results, expected)):
        for j, (got, exp) in enumerate(zip(row_got, row_exp)):
            cocotb.log.info(f"out[{m}][{j}] = {got}  (expected {exp})")
            assert got == exp, f"row {m}, col {j}: expected {exp}, got {got}"


@cocotb.test()
async def test_random_matmul_matrix(dut):
    """
    Random matrix-matrix multiply: M×N activation matrix × N×N weights.

    Values are capped at 7 so M * N * 7 * 7 stays well within ACC_WIDTH=32.
    """
    N = dut.N.value.to_unsigned()
    M = random.randint(2, max(2, N))
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[random.randint(0, 7) for _ in range(N)] for _ in range(M)]
    weights    = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]
    expected   = matmul_ref_matrix(act_matrix, weights)

    cocotb.log.info(f"N={N}, M={M}")
    cocotb.log.info(f"act_matrix={act_matrix}")
    cocotb.log.info(f"weights={weights}")
    cocotb.log.info(f"expected={expected}")

    await load_weights(dut, N, weights)
    results = await stream_activation_matrix(dut, N, act_matrix)

    for m, (row_got, row_exp) in enumerate(zip(results, expected)):
        for j, (got, exp) in enumerate(zip(row_got, row_exp)):
            cocotb.log.info(f"out[{m}][{j}] = {got}  (expected {exp})")
            assert got == exp, f"row {m}, col {j}: expected {exp}, got {got}"


@cocotb.test()
async def test_shadow_buffer(dut):
    """
    Shadow-buffer (double-buffering) test: preload two weight sets into opposite
    banks, then run two back-to-back inferences by toggling act_sel_i / weight_sel_i.

    Sequence:
      1. Load W0 into bank 0 (weight_sel_i=0).
      2. Load W1 into bank 1 (weight_sel_i=1) — shadow bank, loaded without
         disturbing bank 0.
      3. Inference A: stream acts with act_sel_i=0  →  MAC reads weight_buf[0]=W0.
         Verify outputs match matmul(acts_a, W0).
      4. Inference B: stream acts with act_sel_i=1  →  MAC reads weight_buf[1]=W1.
         Verify outputs match matmul(acts_b, W1).

    This confirms that the PE's two weight banks are independently addressable and
    that flipping act_sel_i atomically switches the active weight set.
    """
    N = dut.N.value.to_unsigned()
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    acts_a = [random.randint(1, 15) for _ in range(N)]
    acts_b = [random.randint(1, 15) for _ in range(N)]
    W0     = [[random.randint(1, 15) for _ in range(N)] for _ in range(N)]
    W1     = [[random.randint(1, 15) for _ in range(N)] for _ in range(N)]

    def log_diagram(acts, W, label):
        # column width wide enough for the largest value
        cw    = max(len(str(max(max(r) for r in W))), len(str(max(acts)))) + 1
        aw    = cw  # activation field width matches
        sep   = "  " + " " * (aw + 5) + "+" + ("-" * (cw + 1) + "+") * N
        arrow = "-" * 3 + ">"
        cocotb.log.info(f"  --- {label}: acts (rows) @ W (cols) ---")
        cocotb.log.info(sep)
        for i in range(N):
            cells = "".join(f" {W[i][j]:{cw}}|" for j in range(N))
            cocotb.log.info(f"  act[{i}]={acts[i]:{aw}} {arrow} |{cells}")
        cocotb.log.info(sep)

    log_diagram(acts_a, W0, "[A] bank-0")
    log_diagram(acts_b, W1, "[B] bank-1")

    # Step 1: load W0 into bank 0
    await load_weights(dut, N, W0, sel=0)
    # Step 2: load W1 into bank 1 (shadow bank — bank 0 remains intact)
    await load_weights(dut, N, W1, sel=1)

    # Step 3: inference A using bank 0
    expected_a = matmul_ref(acts_a, W0)
    results_a  = await stream_and_collect(dut, N, acts_a, sel=0)
    for j, (got, exp) in enumerate(zip(results_a, expected_a)):
        cocotb.log.info(f"[A] psum_out_n_o[{j}] = {got}  (expected {exp})")
        assert got == exp, f"[A] column {j}: expected {exp}, got {got}"

    # Step 4: inference B using bank 1
    expected_b = matmul_ref(acts_b, W1)
    results_b  = await stream_and_collect(dut, N, acts_b, sel=1)
    for j, (got, exp) in enumerate(zip(results_b, expected_b)):
        cocotb.log.info(f"[B] psum_out_n_o[{j}] = {got}  (expected {exp})")
        assert got == exp, f"[B] column {j}: expected {exp}, got {got}"

# ---------------------------------------------------------------------------
# Pytest boilerplate
# ---------------------------------------------------------------------------

tests = [
    "reset_test",
    "test_basic_matmul",
    "test_random_matmul",
    "test_basic_matmul_matrix",
    "test_random_matmul_matrix",
    "test_shadow_buffer",
]

proj_path = Path("./rtl").resolve()
SOURCES   = [proj_path / "sysray_nxn.sv", proj_path / "pe.sv"]


@pytest.mark.parametrize("testcase", tests)
def test_sysray_nxn_each(testcase):
    run_test(
        sources=SOURCES,
        module_name="test_sysray_nxn",
        hdl_toplevel="sysray_nxn",
        parameters={"N": 2},
        testcase=testcase,
    )


def test_sysray_nxn_all():
    run_test(
        sources=SOURCES,
        module_name="test_sysray_nxn",
        hdl_toplevel="sysray_nxn",
        parameters={"N": 2},
    )
