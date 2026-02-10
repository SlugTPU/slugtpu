import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
import random


@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)
    await FallingEdge(rst_i)


@cocotb.test()
async def bias_simple_test(dut):
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    bias_i = dut.bias_i
    bias_valid_i = dut.bias_valid_i
    data_i = dut.data_i
    data_valid_i = dut.data_valid_i
    data_valid_o = dut.data_valid_o

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await FallingEdge(rst_i)

    # load bias
    bias_i.value = 15
    bias_valid_i = 1
    # load data
    data_i.value = 2
    data_i.valid_i = 1

    await RisingEdge(clk_i)
    await ReadOnly()

    assert data_valid_o.value == 1, "Expected data_valid_o to be high"
    assert data_o.to_unsigned() == 17, "Expected 17, got {data_o.to_unsigned()}"


tests = ["reset_test", "bias_simple_test"]

@pytest.mark.parametrize("testcase", tests)
def test_bias_each(testcase):
    """Runs each test independently. Continues on test failure"""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"bias.sv" ]

    run_test(parameters={}, sources=sources, module_name="test_bias", hdl_toplevel="bias", testcase=testcase)

def test_bias_all():
    """Runs each test sequentially as one giant test."""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"bias.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_bias", hdl_toplevel="bias")
