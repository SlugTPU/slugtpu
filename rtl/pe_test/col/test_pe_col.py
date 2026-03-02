"""
test_pe_col.py - cocotb testbench for pe_col (2 PEs stacked vertically)

Topology:
    weight_in --> [PE0] --> weight_out
                    |
                 psum_mid
                    |
                 [PE1] --> psum_out

Timing:
    Cycle B1: W loads into PE0
    Cycle B2: W flows down to PE1
    Cycle C1: sel swaps, act0=A00 into PE0
    Cycle C2: act1=A10 into PE1 — PE0 result in psum_mid
    Cycle C3: psum_out = W*A00 + W*A10  <-- read here
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

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
    """
    Bootstrap W into both PEs via weight flow-down, then stream skewed activations.

    W   = 3
    A00 = 4  (PE0, cycle 1)
    A10 = 5  (PE1, cycle 2 — skewed by 1)

    Expected: W * (A00 + A10) = 3 * 9 = 27
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    W   = 7
    W2  = 2
    A00 = 5
    A10 = 4

    # Cycle B1: W arrives at PE0
    dut.weight_in.value = pack_weight(valid=1, sel=0, data=W)
    dut.act0_in.value   = 0
    dut.act1_in.value   = 0
    dut.psum_in.value   = 0
    await tick(dut)

    # Cycle B2: W2 flows down to PE1
    dut.weight_in.value = pack_weight(valid=1, sel=0, data=W2)
    await tick(dut)

    # Cycle C1: swap sel=1 so buf[1] is active, act0=A00 into PE0
    dut.weight_in.value = pack_weight(valid=1, sel=1, data=0)
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0
    await tick(dut)

    # Cycle C2: act1=A10 into PE1, psum_mid from PE0 now available
    dut.weight_in.value = pack_weight(valid=1, sel=1, data=0)
    dut.act0_in.value   = 0
    dut.act1_in.value   = A10
    await tick(dut)

    # Cycle C3: psum_out is registered — read here
    dut.weight_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value   = 0
    dut.act1_in.value   = 0
    await tick(dut)

    expected = W2 * A00 + W * A10  
    assert dut.psum_out.value == expected, \
        f"Expected {expected}, got {int(dut.psum_out.value)}"
    cocotb.log.info(f"PASS: basic_flow  psum_out={int(dut.psum_out.value)}")
