import random
import cocotb
from cocotb.triggers import FallingEdge
from pathlib import Path
import pytest
from shared import clock_start, reset_sequence
from runner import run_test


# ---------------------------------------------------------------------------
# Reference models
# ---------------------------------------------------------------------------

def vec_mat_mul_ref(acts, weights):
    """C[j] = sum_i acts[i] * weights[i][j]  (vector @ matrix, column outputs)"""
    N = len(acts)
    return [sum(acts[i] * weights[i][j] for i in range(N)) for j in range(N)]


def mat_mat_mul_ref(act_matrix, weights):
    """Compute act_matrix @ weights row-by-row; returns an M×N output matrix."""
    return [vec_mat_mul_ref(act_row, weights) for act_row in act_matrix]


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
async def test_basic_matmul_matrix(dut):
    """
    Fixed-value matrix-matrix multiply: N×N activation matrix × N×N weights.

    Each output row is verified independently against matmul_ref.
    """
    N = dut.N.value.to_unsigned()
    M = N
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[m * N + i + 1 for i in range(N)] for m in range(M)]
    weights    = [[(i + 1) * (j + 1) for j in range(N)] for i in range(N)]
    expected   = mat_mat_mul_ref(act_matrix, weights)

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
    expected   = mat_mat_mul_ref(act_matrix, weights)

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



# ---------------------------------------------------------------------------
# Pytest boilerplate
# ---------------------------------------------------------------------------

tests = [
    "reset_test",
    "test_basic_matmul_matrix",
    "test_random_matmul_matrix",
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
