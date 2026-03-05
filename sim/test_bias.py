# DEPRECATED: This file is no longer maintained as the bias module is no longer used in the design. However, it may still be useful as a reference for how to write cocotb tests and models.

import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from cocotb.types import LogicArray, Logic
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque

class Bias():
    def __init__(self):
        self.bias_r = 0

    def update_bias(self, bias_i):
        self.bias_r = bias_i

    def compute_output(self, data_i):
        return self.bias_r + data_i

class BiasModel():
    def __init__(self, WIDTH_P):
        self.bias_module = Bias()
        self.WIDTH_P = WIDTH_P
        self.data_i = LogicArray(WIDTH_P)
        self.valid_o = Logic(1)

    # compute output
    def produce(self, dut):
        data_valid_o = dut.data_valid_o
        data_o = dut.data_o

        if data_valid_o.value == 1:
            got = data_o.value.to_unsigned()
            expected = self.bias.compute_output(dut.data_i.value.to_unsigned())
            cocotb.log.info(f"Produced output {got}, expected {expected}")
            assert got == expected, f"Expected {expected}, got {got}"

    # update registers
    def consume(self, dut):
        bias_i = dut.bias_i
        bias_valid_i = dut.bias_valid_i

        if bias_valid_i.value == 1:
            self.bias_module.update_bias(bias_i.value.to_unsigned())
        
class ModelRunner():
    def __init__(self, dut):
        self.dut = dut
        self.bias_model = BiasModel(dut.WIDTH_P)

    async def run_input(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            await ReadWrite()
            self.bias_model.consume(self.dut)

    async def run_output(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            await ReadOnly()
            self.bias_model.produce(self.dut)

    async def run(self):
        cocotb.start_soon(self.run_input())
        cocotb.start_soon(self.run_output())


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
    ready_i = dut.ready_i
    ready_o = dut.ready_o
    data_o = dut.data_o

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await FallingEdge(rst_i)

    ready_i.value = 1
    # load bias
    bias_i.value = 15
    bias_valid_i.value = 1
    # load data
    data_i.value = 2
    data_valid_i.value = 1

    await RisingEdge(clk_i)


tests = ["reset_test", "bias_simple_test"]

@pytest.mark.parametrize("testcase", tests)
def test_bias_each(testcase):
    """Runs each test independently. Continues on test failure"""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"bias.sv" ]

    run_test(parameters={}, sources=sources, module_name="test_bias", hdl_toplevel="bias", testcase=testcase)

# TODO: add more tests
# - test backpressure
# - random fuzzing of handshake signals and data

def test_bias_all():
    """Runs each test sequentially as one giant test."""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"bias.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_bias", hdl_toplevel="bias")
