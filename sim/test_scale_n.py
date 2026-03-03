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


def float_to_fixed(f_val, frac_bits):
    """Converts a float to a fixed-point integer."""
    scaling_factor = 1 << frac_bits 
    return int(f_val * scaling_factor + 0.5)

def fixed_to_float(fixed_val, frac_bits):
    """Converts a fixed-point integer back to a float."""
    scaling_factor = 1 << frac_bits
    return float(fixed_val) / scaling_factor

class mul_n_model():
    def __init__(self, N, width=8):
        self.N = N
        # Assume width is 8 bits for quantization
        self.width = width
        self.q = deque(maxlen=1)

    def consume(self, dut):
        self.q.append((dut.data_i.value, dut.m0_i.value))

    def produce(self, dut):
        data_o = dut.data_o
        inp_n, m0_n = self.q.popleft()
        FIXED_SHIFT_P = dut.FIXED_SHIFT_P.value
        # expected = quantized_mul_n(inp_n, m0_n, dut.ACC_WIDTH_P.value.to_unsigned(), dut.M0_WIDTH_P.value.to_unsigned(), dut.FIXED_SHIFT_P.value.to_unsigned(), self.N)

        for i in range(self.N):
            got = data_o[i].value.to_signed()
            expected = inp_n[i].to_signed() * fixed_to_float(m0_n[i].to_signed(), FIXED_SHIFT_P.to_unsigned())

            cocotb.log.info(f"Producing with input {dut.data_i[i].value.to_signed()} and m0 {dut.m0_i[i].value.to_signed()}: got {got}, expected {expected}")
            # check for accuracy
            assert abs(got - expected) < 0.5, f"Output mismatch at index {i}: got {got}, expected {expected}"


class ModelRunner():
    def __init__(self, dut):
        self.dut = dut
        self.model = mul_n_model(dut.N.value.to_unsigned())

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
async def scale_n_simple_test(dut):
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    data_i = dut.data_i
    m0_i = dut.m0_i
    data_valid_i = dut.data_valid_i
    data_ready_i = dut.data_ready_i
    N = dut.N
    FIXED_SHIFT_P = dut.FIXED_SHIFT_P
    m = ModelRunner(dut)

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    m.start()

    await FallingEdge(rst_i)

    data_ready_i.value = 1
    data_valid_i.value = 1

    for i in range(N.value):
        m0_i[i].value = random.randint(-10, 10) << FIXED_SHIFT_P.value.to_unsigned()
        data_i[i].value = random.randint(-10, 10)

    await RisingEdge(dut.clk_i)

    await FallingEdge(dut.clk_i)
    data_ready_i.value = 1
    data_valid_i.value = 0
    await FallingEdge(dut.clk_i)


tests = ["reset_test", "scale_n_simple_test"]
proj_path = Path("./rtl").resolve()
sources = [ proj_path/"utils/elastic.sv", proj_path/"scalar_units/scale_n.sv", proj_path/"quantizer_mul.sv"]

@pytest.mark.parametrize("testcase", tests)
def test_scale_n_each(testcase):
    """Runs each test independently. Continues on test failure"""
    run_test(parameters={}, sources=sources, module_name="test_scale_n", hdl_toplevel="scale_n", testcase=testcase)

def test_scale_n_all():
    """Runs each test sequentially as one giant test."""

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_scale_n", hdl_toplevel="scale_n")