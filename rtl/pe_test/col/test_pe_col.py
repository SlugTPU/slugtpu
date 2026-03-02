"""
test_pe_col.py - cocotb testbench for pe_col (2 PEs stacked vertically)

new topology:
weight_in -> pe0 -> weight_mid  -> pe1
              |                     |
            psum_in=0 -> psum_mid -> psum_out

loading uses a shift reg + broadcast latch:
    shift s1: weight_in = w1 (for pe1, bottom), latch = 0
    shift s2: weight_in = w2 (for pe0, top) latch=1
    
At s2 posedge, pe0 captures w2 from weight in, pe1 captures w1 from weight_mid

Compute (buf_sel flips):
    C1: act0 = A00 -> pe0 computes w2 * A00
    C2: act1 = A10 -> pe1 computes psum_mid + w1*A10 = w2*A00 + w1+A10  
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

async def do_reset(dut):
    dut.rst_i.value = 1
    dut.act0_in.value = 0
    dut.act1_in.value = 0
    dut.weight_in.value = 0
    dut.weight_latch.value = 0
    dut.buf_sel.value = 0
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

    W1 = 7 # for PE1 (bottom), sent first so it shifts down
    W2 = 2 # for PE0 (top), sent second, stays at top
    A00 = 5
    A10 = 4

    #Shift phase (buf_sel=0, so shadow = buf[1])

    # sr1: W1 enters PE0's shift register; PE1 sees nothing yet
    dut.weight_in.value = W1
    dut.weight_latch.value = 0
    dut.buf_sel.value = 0
    dut.act0_in.value = 0
    dut.act1_in.value = 0
    dut.psum_in.value = 0
    await tick(dut)

    # sr2: W2 enters PE0, W1 has shifted to PE1. now latch
    dut.weight_in.value    = W2
    dut.weight_latch.value = 1
    await tick(dut)
    # now PE0.buf[1] = W2, PE1.buf[1] = W1

    # compute phase (flip buf_sel so buf[1] is active)

    dut.weight_latch.value = 0
    dut.buf_sel.value = 1

    # C1
    dut.act0_in.value = A00
    dut.act1_in.value = 0
    await tick(dut)
    # PE0.psum_out = 0 + A00*W2

    # C2
    dut.act0_in.value = 0
    dut.act1_in.value = A10
    await tick(dut)
    # PE1.psum_out = (A00*W2) + A10*W1

    # C3: drain. result is registered, read here
    dut.act0_in.value = 0
    dut.act1_in.value = 0
    await tick(dut)

    got = int(dut.psum_out.value)
    expected = W2 * A00 + W1 * A10
    cocotb.log.info(f"psum_out = {got},  expected = {expected}")
    assert got == expected, f"FAIL: expected {expected}, got {got}"
    cocotb.log.info("PASS: test_basic_flow")
