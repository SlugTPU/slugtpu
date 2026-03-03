"""
Timing:
    Cycle B1: W loads into W01
    Cycle B2: W flows down to W00
    Cycle C1: sel swaps, act0=A00 into PE0
    Cycle C2: act1=A10 into PE1 — PE0 result in psum_mid
    Cycle C3: psum_out = W00*A00 + W01*A10
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import FallingEdge
from pathlib import Path
import pytest
from runner import run_test

def pack_weight(valid, sel, data):
    """
    [0]   = valid  (1 = write data into shadow buffer)
    [1]   = sel    (selects active buffer)
    [9:2] = data
    """
    return (valid & 0x1) | ((sel & 0x1) << 1) | ((data & 0xFF) << 2)

async def do_reset(dut):
    dut.rst_i.value = 1

    dut.act0_in.value = 0
    dut.act1_in.value = 0
    dut.act0_valid.value = 0
    dut.act1_valid.value = 0

    dut.weight_in.value = 0
    dut.weight_valid.value = 0

    dut.psum_in.value = 0

    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await RisingEdge(dut.clk_i)

async def tick(dut):
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_basic_flow(dut):
    """
    Load two unique weights via shift + latch, then compute.

    W2 = 2 -> PE0 (top) A00= 5
    W1 = 7 -> PE1 (bottom) A10 = 4

    Expected psum_out = W2*A00 + W1*A10 = 2*5 + 7*4 = 10 + 28 = 38
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    await FallingEdge(dut.clk_i)
    W1 = 7 # for PE1 (bottom), sent first so it shifts down
    W2 = 2 # for PE0 (top), sent second, stays at top
    A00 = 5
    A10 = 4

    #Shift phase (buf_sel=0, so shadow = buf[1])

    # sr1: W1 enters PE0's shift register; PE1 sees nothing yet
    dut.weight_in.value = W1
    dut.weight_valid.value = 1
    dut.act0_in.value = 0
    dut.act1_in.value = 0
    dut.act0_valid.value = 0
    dut.act1_valid.value = 0
    dut.psum_in.value = 0
    await FallingEdge(dut.clk_i)

    # sr2: W2 enters PE0, W1 has shifted to PE1. now latch
    dut.weight_in.value    = W2
    dut.weight_valid.value = 1
    await FallingEdge(dut.clk_i)
    # now PE0.buf[1] = W2, PE1.buf[1] = W1

    # compute phase (flip buf_sel so buf[1] is active)

    dut.weight_valid.value = 0

    # C1
    dut.act0_in.value = A00
    dut.act1_in.value = 0
    dut.act0_valid.value = 1
    dut.act1_valid.value = 0
    await FallingEdge(dut.clk_i)
    # PE0.psum_out = 0 + A00*W2

    # C2
    dut.act0_in.value = 0
    dut.act1_in.value = A10
    dut.act0_valid.value = 0
    dut.act1_valid.value = 1
    await FallingEdge(dut.clk_i)
    # PE1.psum_out = (A00*W2) + A10*W1

    # C3: drain. result is registered, read here
    dut.act0_in.value = 0
    dut.act1_in.value = 0
    dut.act0_valid.value = 0
    dut.act1_valid.value = 0
    await FallingEdge(dut.clk_i)

    got = int(dut.psum_out.value)
    expected = W2 * A00 + W1 * A10
    cocotb.log.info(f"psum_out = {got},  expected = {expected}")
    assert got == expected, f"FAIL: expected {expected}, got {got}"
    cocotb.log.info("PASS: test_basic_flow")

tests = ["test_basic_flow"]

proj_path = Path("./rtl").resolve()
sources = [ proj_path/"pe_test"/"col"/"oldpe.sv", proj_path/"pe_test"/"col"/"col_pe.sv" ]

@pytest.mark.parametrize("testcase", tests)
def test_bias_each(testcase):
    """Runs each test independently. Continues on test failure"""
    run_test(parameters={}, sources=sources, module_name="test_pe_col", hdl_toplevel="pe_col", testcase=testcase)

# TODO: add more tests
# - test backpressure
# - random fuzzing of handshake signals and data

def test_bias_all():
    """Runs each test sequentially as one giant test."""
    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_pe_col", hdl_toplevel="pe_col")