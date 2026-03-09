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
    Load weights into the systolic array with a diagonal column stagger.

    Column j starts its row sweep j cycles after column 0, mirroring the
    diagonal wavefront used by stream_activation_matrix.  At each cycle c,
    column j is active when 0 <= c - j < N and receives weights[N-1-(c-j)][j]
    (bottom-to-top sweep, same as before).

    Drive schedule (N=2 example):
      cycle 0: col0 = w[1][0]
      cycle 1: col0 = w[0][0],  col1 = w[1][1]   ← two columns active
      cycle 2:                   col1 = w[0][1]

    Total drive cycles: 2*N - 1.  After the sweep, one deassert cycle clears
    weight_valid for all columns.

    sel: 0 or 1 — selects which PE weight bank receives the data.
    weight_sel_n_i is driven atomically with the first valid weight for each
    column; driving it before valid would toggle prev_weight_sel in every PE
    and corrupt the downstream weight_buf.
    """
    for cycle in range(2 * N - 1):
        await FallingEdge(dut.clk_i)
        for col in range(N):
            row_idx = cycle - col          # position in the bottom-to-top sweep
            if 0 <= row_idx < N:
                row = N - 1 - row_idx      # row_idx=0 → bottom row (N-1)
                dut.weight_sel_n_i[col].value   = sel
                dut.weight_n_i[col].value       = weights[row][col]
                dut.weight_valid_n_i[col].value = 1
            else:
                dut.weight_n_i[col].value       = 0
                dut.weight_valid_n_i[col].value = 0

    # Deassert weight_valid one cycle after the last column finishes
    await FallingEdge(dut.clk_i)
    for col in range(N):
        dut.weight_n_i[col].value       = 0
        dut.weight_valid_n_i[col].value = 0




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
    results = [[None] * N for _ in range(N)]

    for cycle in range(N + 2 * N - 1):
        await FallingEdge(dut.clk_i)

        # Drive: row i carries vector m = cycle - i when in range
        for i in range(N):
            m = cycle - i
            dut.act_sel_n_i[i].value = sel
            if 0 <= m < N:
                dut.act_n_i[i].value       = act_matrix[m][i]
                dut.act_valid_n_i[i].value = 1
            else:
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0

        # Sample: col j of vector m fires at FallingEdge m + N + j → m = cycle - N - j
        for j in range(N):
            if dut.psum_out_valid_n_o[j].value == 1:
                m = cycle - N - j
                if 0 <= m < N:
                    results[m][j] = int(dut.psum_out_n_o[j].value)

    for r in range(N):
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
    # always square!
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

    cocotb.start_soon(load_weights(dut, N, weights))
    for _ in range(N):                          # wait for col 0 to finish loading
        await FallingEdge(dut.clk_i)
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
    # always square!
    M = N
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[random.randint(0, 7) for _ in range(N)] for _ in range(M)]
    weights    = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]
    expected   = mat_mat_mul_ref(act_matrix, weights)

    cocotb.log.info(f"N={N}, M={M}")
    cocotb.log.info(f"act_matrix={act_matrix}")
    cocotb.log.info(f"weights={weights}")
    cocotb.log.info(f"expected={expected}")

    cocotb.start_soon(load_weights(dut, N, weights))
    for _ in range(N):                          # wait for col 0 to finish loading
        await FallingEdge(dut.clk_i)
    results = await stream_activation_matrix(dut, N, act_matrix)

    for m, (row_got, row_exp) in enumerate(zip(results, expected)):
        for j, (got, exp) in enumerate(zip(row_got, row_exp)):
            cocotb.log.info(f"out[{m}][{j}] = {got}  (expected {exp})")
            assert got == exp, f"row {m}, col {j}: expected {exp}, got {got}"

@cocotb.test()
async def test_shadow_buffer(dut):
      N = dut.N.value.to_unsigned()

      await clock_start(dut.clk_i)
      await reset_sequence(dut.clk_i, dut.rst_i)

      act_matrix0 = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]
      act_matrix1 = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]
      weights0    = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]
      weights1    = [[random.randint(0, 7) for _ in range(N)] for _ in range(N)]

      cocotb.log.info(f"begin testing shadow buffer with N={N}")

      # Fire bank 0 loading; streaming starts N FEs later
      cocotb.start_soon(load_weights(dut, N, weights0, sel=0))
      for _ in range(N):
          await FallingEdge(dut.clk_i)   # col 0 bank 0 settled

      # Schedule bank 1 loading to start N FEs from now (when bank 0 finishes)
      async def load_bank1():
          for _ in range(N):
              await FallingEdge(dut.clk_i)
          await load_weights(dut, N, weights1, sel=1)
      cocotb.start_soon(load_bank1())

      # Stream layer 0 (reads bank 0 via act_sel=0)
      results0 = await stream_activation_matrix(dut, N, act_matrix0, sel=0)
      # Bank 1 is now settled; stream layer 1 immediately (reads bank 1 via act_sel=1)
      results1 = await stream_activation_matrix(dut, N, act_matrix1, sel=1)

      # Assert both layers
      assert results0 == mat_mat_mul_ref(act_matrix0, weights0)
      assert results1 == mat_mat_mul_ref(act_matrix1, weights1)

# ---------------------------------------------------------------------------
# Pytest boilerplate
# ---------------------------------------------------------------------------

tests = [
    "reset_test",
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
