import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge
from pathlib import Path
from shared import reset_sequence, clock_start

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

# export metadata for registering CocoTB tests to be ran
def register_tests():
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"fifo.sv" ]

    return { "hdl_toplevel": "fifo", "sources": sources }
