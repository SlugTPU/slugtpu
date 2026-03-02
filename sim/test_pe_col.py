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
    dut.rst_i.value     = 1
    dut.act0_in.value   = 0
    dut.act1_in.value   = 0
    dut.weight_in.value = pack_weight(0, 0, 0)
    dut.psum_in.value   = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await RisingEdge(dut.clk_i)

async def tick(dut):
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_basic_flow(dut):

    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    W10  = 1
    W00  = 2
    A00  = 3
    A10  = 4

    # Cycle B1: W01 arrives at PE0
    dut.weight_in.value = pack_weight(valid=1, sel=0, data=W10)
    dut.act0_in.value   = 0
    dut.act1_in.value   = 0
    dut.psum_in.value   = 0
    await FallingEdge(dut.clk_i)

    # Cycle B2: W01 flows down to PE1, W00 arrives at PE0
    dut.weight_in.value = pack_weight(valid=1, sel=0, data=W00)
    await FallingEdge(dut.clk_i)

    # Cycle C1: swap sel=1 so buf[1] is active, act0=A00 into PE0
    dut.weight_in.value = pack_weight(valid=1, sel=1, data=0)
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0
    await FallingEdge(dut.clk_i)

    # Cycle C2: act1=A10 into PE1, psum_mid from PE0 now available
    dut.weight_in.value = pack_weight(valid=1, sel=1, data=0)
    dut.act0_in.value   = 0
    dut.act1_in.value   = A10
    await FallingEdge(dut.clk_i)
    
    # Cycle C3: psum_out is registered — read here
    #dut.weight_in.value = pack_weight(valid=0, sel=0, data=0)
    #dut.act0_in.value   = 0
    #dut.act1_in.value   = 0
    #await FallingEdge(dut.clk_i)

    expected = (W00 * A00) + (W10 * A10)
    assert dut.psum_out.value == expected, \
        f"Expected {expected}, got {int(dut.psum_out.value)}"
    cocotb.log.info(f"PASS: basic_flow  psum_out={int(dut.psum_out.value)}")

tests = ["test_basic_flow"]

proj_path = Path("./rtl").resolve()
sources = [ proj_path/"pe_test"/"col"/"pe.sv", proj_path/"pe_test"/"col"/"col_pe.sv" ]

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