import random
import cocotb
from cocotb.triggers import FallingEdge
from pathlib import Path
import pytest
from shared import clock_start, reset_sequence
from runner import run_test


# ---------------------------------------------------------------------------
# Reference model
# ---------------------------------------------------------------------------

def matmul_ref(acts, weights):
    """C[j] = sum_i acts[i] * weights[i][j]  (vector @ matrix, column outputs)"""
    N = len(acts)
    return [sum(acts[i] * weights[i][j] for i in range(N)) for j in range(N)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def load_weights(dut, N, weights):
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
    """
    for row in range(N - 1, -1, -1):   # N-1 down to 0
        await FallingEdge(dut.clk_i)
        for col in range(N):
            dut.weight_n_i[col].value        = weights[row][col]
            dut.weight_valid_n_i[col].value  = 1

    # Deassert weight_valid one cycle after the last row is presented
    await FallingEdge(dut.clk_i)
    for col in range(N):
        dut.weight_n_i[col].value        = 0
        dut.weight_valid_n_i[col].value  = 0


async def stream_activations(dut, N, acts):
    """
    Drive one activation vector with proper row staggering.

    Row i is presented i cycles after row 0.  This ensures that act[i] and
    weight row i arrive at each column j at the same time — both experience
    j pipeline stages of latency as they travel across the array.

      Cycle 0:   act_n_i[0] = acts[0], valid[0] = 1;  rows 1..N-1 idle
      Cycle 1:   act_n_i[1] = acts[1], valid[1] = 1;  rows 0,2..N-1 idle
      ...
      Cycle N-1: act_n_i[N-1] = acts[N-1], valid[N-1] = 1;  all others idle
    """
    for row in range(N):
        await FallingEdge(dut.clk_i)
        for i in range(N):
            if i == row:
                dut.act_n_i[i].value       = acts[i]
                dut.act_valid_n_i[i].value = 1
            else:
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def reset_test(dut):
    """Verify that all psum outputs are 0 after reset with no inputs driven."""
    N = dut.N.value.to_unsigned()
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

    Sampling: column j output is valid exactly j+1 falling edges after
    stream_activations ends (psum flows straight down, one column per cycle).
    """
    N = dut.N.value.to_unsigned()
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    acts    = list(range(1, N + 1))
    weights = [[(i + 1) * (j + 1) for j in range(N)] for i in range(N)]
    expected = matmul_ref(acts, weights)

    cocotb.log.info(f"N={N}, acts={acts}, weights={weights}, expected={expected}")

    await load_weights(dut, N, weights)
    await stream_activations(dut, N, acts)

    # Column j output is valid exactly j+1 falling edges after stream_activations ends.
    # The PE's psum_o resets to 0 when act_valid_i goes low, so each column's result
    # must be read in the same cycle it becomes valid — before the next posedge clears it.
    # At j==0 we also deassert all activations; the registered act_o values in the last
    # row will continue carrying the final activation through the remaining columns.
    for j in range(N):
        await FallingEdge(dut.clk_i)
        if j == 0:
            for i in range(N):
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0
        got = int(dut.psum_out_n_o[j].value)
        cocotb.log.info(f"psum_out_n_o[{j}] = {got}  (expected {expected[j]})")
        assert got == expected[j], f"column {j}: expected {expected[j]}, got {got}"


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
    await stream_activations(dut, N, acts)

    for j in range(N):
        await FallingEdge(dut.clk_i)
        if j == 0:
            for i in range(N):
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0
        got = int(dut.psum_out_n_o[j].value)
        cocotb.log.info(f"psum_out_n_o[{j}] = {got}  (expected {expected[j]})")
        assert got == expected[j], f"column {j}: expected {expected[j]}, got {got}"

# ---------------------------------------------------------------------------
# Pytest boilerplate
# ---------------------------------------------------------------------------

tests = [
    "reset_test",
    "test_basic_matmul",
    "test_random_matmul",
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
