import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
from cocotb.types import LogicArray, Logic, Array
from collections import deque
import random
from shared import handshake

def logic_add(a: LogicArray, b: LogicArray, width: int) -> LogicArray:
    """
    Adds two LogicArrays, returning the logic array with the given width. 

    Assumes inputs are signed and returns a signed result.
    """
    res = (a.to_signed() + b.to_signed())
    return LogicArray.from_signed(res, width)

def add_n(data_i: Array[LogicArray], bias_i: Array[LogicArray], N: int, width: int) -> Array[LogicArray]:
    """Adds N elements of data_i to bias_i."""
    result = Array([], N)
    for i in range(N):
        result[i] = logic_add(data_i[i], bias_i[i], width)
    return result

# add_n is an elastic module that takes in N elements of data and bias, adds them together, and produces N elements of output.
class add_n_model():
    def __init__(self, N: int, width: int):
        self.N = N
        self.width = width
        self.q = deque(maxlen=1)

    def consume(self, dut):
        cocotb.log.info(f"Consuming input: data_i={[dut.data_i[i].value for i in range(self.N)]}, bias_i={[dut.bias_i[i].value for i in range(self.N)]}")
        self.q.append((dut.data_i, dut.bias_i))

    def produce(self, dut):
        data_o = dut.data_o

        got_n = data_o
        inp_n, bias_n = self.q.popleft()

        for i in range(self.N):
            res = logic_add(inp_n[i].value, bias_n[i].value, self.width)
            # cocotb.log.info(f"Expected {res}, got {got_n[i]}")
            assert got_n[i].value == res, f"Expected {res}, got {got_n[i]}"

class ModelRunner():
    def __init__(self, dut):
        self.dut = dut
        self.model = add_n_model(dut.N.value.to_unsigned(), dut.width_p.value.to_unsigned())

    def start(self):
        cocotb.start_soon(self.run_input())
        cocotb.start_soon(self.run_output())

    async def run_input(self):
        clk_i = self.dut.clk_i
        valid_i, valid_o = self.dut.data_valid_i, self.dut.data_valid_o
        ready_i, ready_o = self.dut.data_ready_i, self.dut.data_ready_o
        rst_i = self.dut.rst_i

        while True:
            await handshake(clk_i, rst_i, ready_o, valid_i)
            cocotb.log.info("Input handshake successful, consuming input")
            self.model.consume(self.dut)

    async def run_output(self):
        clk_i = self.dut.clk_i
        valid_i, valid_o = self.dut.data_valid_i, self.dut.data_valid_o
        ready_i, ready_o = self.dut.data_ready_i, self.dut.data_ready_o
        rst_i = self.dut.rst_i

        while True:
            cocotb.log.info("Waiting for output handshake...")
            await handshake(clk_i, rst_i, ready_i, valid_o)
            self.model.produce(self.dut)
            cocotb.log.info("Output handshake successful, producing output")

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    data_i = dut.data_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)
    await FallingEdge(rst_i)
    cocotb.log.info("Reset complete")


@cocotb.test()
async def add_n_simple_test(dut):
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    bias_i = dut.bias_i
    data_i = dut.data_i
    data_valid_i = dut.data_valid_i
    data_ready_i = dut.data_ready_i
    N = dut.N
    width_p = dut.width_p
    m = ModelRunner(dut)

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    m.start()

    await FallingEdge(rst_i)

    data_ready_i.value = 1
    data_valid_i.value = 1

    for i in range(N.value):
        bias_i[i].value = random.randint(-10, 10)
        data_i[i].value = random.randint(-10, 10)

    await RisingEdge(dut.clk_i)

    await FallingEdge(dut.clk_i)
    data_ready_i.value = 1
    data_valid_i.value = 0
    await FallingEdge(dut.clk_i)


tests = ["reset_test", "add_n_simple_test"]
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