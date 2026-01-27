# This file is public domain, it can be freely copied without restrictions.
# SPDX-License-Identifier: CC0-1.0
from __future__ import annotations

import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb_tools.runner import get_runner

LANGUAGE = os.getenv("HDL_TOPLEVEL_LANG", "verilog").lower().strip()

timescale = ("1ps","1ps")

@cocotb.test()
async def fifo_simple_test(dut):
    """Test that data propagates through the FIFO"""

    # Create a 50ns period clock driver on port `clk`
    clock = Clock(dut.clk_i, 50, unit="ns")
    # Start the clock. Start it low to avoid issues on the first RisingEdge
    clock.start(start_high=False)

    # Synchronize with the clock. This will register the initial `d` value
    await RisingEdge(dut.clk_i)


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