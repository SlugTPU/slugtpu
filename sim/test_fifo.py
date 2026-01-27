# This file is public domain, it can be freely copied without restrictions.
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge
from cocotb_tools.runner import get_runner

LANGUAGE = os.getenv("HDL_TOPLEVEL_LANG", "verilog").lower().strip()

timescale = ("1ps","1ps")

async def clock_start(clk_i, period_ns=10):
    """Start clock with given period (in ns)"""
    c = Clock(clk_i, period_ns, units="ns")
    cocotb.start_soon(c.start(start_high=False))

async def reset_sequence(clk_i, rst_i, num_cycles=10):
    """Reset sequence"""
    await FallingEdge(clk_i)
    rst_i.value = 1
    await ClockCycles(clk_i, num_cycles)
    await FallingEdge(clk_i)
    rst_i.value = 0


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


def test_simple_fifo_runner():
    sim = os.getenv("SIM", "icarus")

    proj_path = Path("./rtl").resolve()

    if LANGUAGE == "verilog":
        sources = [proj_path/"fifo.sv"]

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel="fifo",
        always=True,
        timescale=timescale
    )

    runner.test(hdl_toplevel="fifo", test_module="test_fifo,")


if __name__ == "__main__":
    test_simple_fifo_runner()