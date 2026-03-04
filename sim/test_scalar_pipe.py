import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from pathlib import Path
from shared import clock_start, reset_sequence
from runner import run_test
import random

class InputModel():
    def __init__(self, dut, data_generator: Iterator[tuple[Array[int], Array[int]]], handshake_generator: Iterator[bool]):
        self.dut = dut
        self.N = dut.N.value.to_unsigned()
        self.data_generator = data_generator
        self.handshake_generator = handshake_generator
        self.nin = 0

    def start(self):
        return cocotb.start_soon(self._run())


    async def _run(self):
        clk_i = self.dut.clk_i
        rst_i = self.dut.rst_i
        valid_i = self.dut.data_valid_i
        ready_i = self.dut.data_ready_i
        ready_o = self.dut.data_ready_o
        data_i = self.dut.data_i
        m0_i = self.dut.m0_i

        await FallingEdge(rst_i)

        # stream random
        for (d, m0) in self.data_generator:
            tx = False

            for i in range(self.N):
                data_i[i].value = d[i]
                m0_i[i].value = m0[i]

            while (not tx):
                valid_i.value = next(self.handshake_generator)

                await RisingEdge(clk_i)

                # cocotb.log.info(f"Tx input: data_i={[data_i[i].value.to_signed() for i in range(self.N)]}, m0_i={[m0_i[i].value.to_signed() for i in range(self.N)]}")
                if valid_i.value and ready_o.value == 1:
                    self.nin += 1
                    tx = True
            await FallingEdge(clk_i)

class OutputModel():
    def __init__(self, dut, handshake_generator, total_nin):
        self.dut = dut
        self.N = dut.N.value.to_unsigned()
        self.total_nin = total_nin
        self.nout = 0
        self.handshake_generator = handshake_generator

    def start(self):
        return cocotb.start_soon(self._run())

    async def _run(self):
        clk_i = self.dut.clk_i
        rst_i = self.dut.rst_i
        valid_o = self.dut.data_valid_o
        ready_i = self.dut.data_ready_i
        data_o = self.dut.data_o

        await FallingEdge(rst_i)

        while self.nout < self.total_nin:
            rx = False
            while (not rx):
                ready_i.value = next(self.handshake_generator)
                await RisingEdge(clk_i)
                if valid_o.value == 1:
                    self.nout += 1
                    rx = True
            await FallingEdge(clk_i)

@cocotb.test()
def test_scalar_pipe_basic(dut):
    """Single vector through pipeline, verify each lane."""
    pass

tests = [
    "test_scalar_pipe_basic",
]

SOURCES = [
    Path("./rtl/scalar_units/scalar_pipe.sv").resolve(),
    Path("./rtl/scalar_units/add_n.sv").resolve(),
    Path("./rtl/scalar_units/relu_n.sv").resolve(),
    Path("./rtl/scalar_units/scale_n.sv").resolve(),
    Path("./rtl/quantizer_mul.sv").resolve(),
    Path("./rtl/utils/elastic.sv").resolve(),
]

@pytest.mark.parametrize("testcase", tests)
def test_scalar_pipe_each(testcase):
    run_test(
        sources=SOURCES,
        module_name="test_scalar_pipe",
        hdl_toplevel="scalar_pipe",
        testcase=testcase,
        sims=["icarus"],
    )

def test_scalar_pipe_all():
    run_test(
        sources=SOURCES,
        module_name="test_scalar_pipe",
        hdl_toplevel="scalar_pipe",
        sims=["icarus"],
    )