import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
from cocotb.types import LogicArray, Logic
import random

def logic_add(a: LogicArray, b: LogicArray, width: int) -> LogicArray:
    """
    Adds two LogicArrays, returning the logic array with the given width. 

    Assumes inputs are signed and returns a signed result.
    """
    res = (a.to_signed() + b.to_signed()) & (1 << width) - 1
    return LogicArray.from_signed(res, width)

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)
    await FallingEdge(rst_i)


@cocotb.test()
async def add_n_simple_test(dut):
    width_p = dut.width_p
    N = dut.N_p

tests = ["reset_test", "load_simple_test"]
proj_path = Path("./rtl").resolve()
sources = [ proj_path/"utils/elastic.sv", proj_path/"scalar_units/add_n.sv"   ]

@pytest.mark.parametrize("testcase", tests)
def test_bias_each(testcase):
    """Runs each test independently. Continues on test failure"""
    run_test(parameters={}, sources=sources, module_name="test_add_n", hdl_toplevel="add_n", testcase=testcase)

def test_bias_all():
    """Runs each test sequentially as one giant test."""

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_add_n", hdl_toplevel="add_n")