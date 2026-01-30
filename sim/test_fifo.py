import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge
from pathlib import Path
from shared import reset_sequence, clock_start
from runner import run_test

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)


@cocotb.test()
async def fifo_simple_test(dut):
    """Test that data propagates through the FIFO"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await ClockCycles(clk_i, 67)

@pytest.mark.parametrize("depth_p", [1, 7])
def test_fifo_all(depth_p):
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"fifo.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={"DEPTH_P": depth_p}, sources=sources, module_name="test_fifo", hdl_toplevel="fifo")
