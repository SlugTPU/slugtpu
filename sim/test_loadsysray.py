import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from pathlib import Path
import pytest
from runner import run_test

N = 2
DATA_WIDTH = 8

async def do_reset(dut):
    dut.rst_i.value        = 1
    dut.act_enable.value   = 0
    dut.act_valid.value    = 0
    dut.weight_enable.value = 0
    dut.weight_valid.value  = 0
    for i in range(N):
        dut.act_i[i].value    = 0
        dut.weight_i[i].value = 0
    await ClockCycles(dut.clk_i, 2)
    dut.rst_i.value = 0
    await ClockCycles(dut.clk_i, 1)


@cocotb.test()
async def test_basic_matmul(dut):
    """
    Simple 2x2 matrix multiply:
      W = [[1, 0],    A = [[2, 3],
           [0, 1]]         [4, 5]]

    Expected output (W * A):
      out[0] = 1*2 + 0*4 = 2
      out[1] = 1*3 + 0*5 = 3  (col 0 of result row 0, row 1)
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    # --- Feed weights (staggered by tri_shift) ---
    # W = identity: W[0][0]=1, W[0][1]=0, W[1][0]=0, W[1][1]=1
    # tri_shift lane 0 has depth 1, lane 1 has depth 2
    # so feed W[1][*] one cycle before W[0][*]

    await FallingEdge(dut.clk_i)
    dut.weight_enable.value  = 1
    dut.weight_valid.value   = 1
    dut.weight_i[0].value    = 0   # W10 (arrives at row 1 after 1 extra cycle)
    dut.weight_i[1].value    = 0   # W11

    await FallingEdge(dut.clk_i)
    dut.weight_i[0].value    = 1   # W00
    dut.weight_i[1].value    = 1   # W11 (identity diagonal)

    await FallingEdge(dut.clk_i)
    dut.weight_valid.value   = 0
    dut.weight_enable.value  = 0

    # --- Feed activations (staggered by tri_shift) ---
    # A col 0: [2, 4], col 1: [3, 5]
    # feed col 1 one cycle before col 0 (same tri_shift stagger)

    await FallingEdge(dut.clk_i)
    dut.act_enable.value  = 1
    dut.act_valid.value   = 1
    dut.act_i[0].value    = 4   # A[1][0]
    dut.act_i[1].value    = 5   # A[1][1]

    await FallingEdge(dut.clk_i)
    dut.act_i[0].value    = 2   # A[0][0]
    dut.act_i[1].value    = 3   # A[0][1]

    await FallingEdge(dut.clk_i)
    dut.act_valid.value   = 0
    dut.act_enable.value  = 0

    # --- Wait for output to drain through output tri_shift ---
    # output tri_shift also has depth N so wait N+a few extra cycles
    await ClockCycles(dut.clk_i, N + 4)

    # --- Check outputs ---
    # Identity matrix so output should equal input activations
    out0 = int(dut.data_o[0].value)
    out1 = int(dut.data_o[1].value)

    cocotb.log.info(f"data_o[0] = {out0}, data_o[1] = {out1}")

    assert out0 == 2, f"Expected data_o[0]=2, got {out0}"
    assert out1 == 3, f"Expected data_o[1]=3, got {out1}"
    cocotb.log.info("PASS: basic matmul identity check")


tests = ["test_basic_matmul"]

proj_path = Path("./rtl").resolve()
sources = [
    proj_path / "loadsysray.sv",
    proj_path / "sysray_nxn.sv",
    proj_path / "tri_shift.sv",
    proj_path / "pe.sv",
]

@pytest.mark.parametrize("testcase", tests)
def test_loadsysray_each(testcase):
    run_test(
        parameters={"N": N, "DATA_WIDTH": DATA_WIDTH},
        sources=sources,
        module_name="test_loadsysray",
        hdl_toplevel="loadsysray",
        testcase=testcase,
    )

def test_loadsysray_all():
    run_test(
        parameters={"N": N, "DATA_WIDTH": DATA_WIDTH},
        sources=sources,
        module_name="test_loadsysray",
        hdl_toplevel="loadsysray",
    )
