"""
test_pe_col.py - cocotb testbench for pe_col

pe.sv change: weight_out now forwards sel ONLY (valid=0, data=0).
col_pe.sv merges sel from chain with valid/data from a dedicated
weight1_in port, so each PE gets its own weight independently.

Topology:
  weight0_in ──────────────────────► [PE0] ──psum_mid──► [PE1] ──► psum_out
  weight1_in (data/valid) ──┐                  │
  weight_mid_raw (sel) ─────┴─► merged ────────┘

Timing:
  Bootstrap (2 cycles):
    B1: drive W_a_pe1 to both weight0_in and weight1_in (same data, same cycle)
    B2: drive W_a_pe0 to weight0_in; weight1_in valid=0 (PE1 already loaded)
    => PE0.buf[0]=W_a_pe0, PE1.buf[0]=W_a_pe1

  Between phases (2 settle cycles):
    Drive valid=0 at new sel for 2 cycles until PE1's sel (from chain) catches up

  Compute (read after C2, no idle needed):
    C1: act0 -> PE0: psum_mid <= psum_in + W_pe0*act0
    C2: act1 -> PE1: psum_out <= psum_mid + W_pe1*act1  <-- READ HERE
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

def pack_weight(valid, sel, data):
    return (valid & 0x1) | ((sel & 0x1) << 1) | ((data & 0xFF) << 2)

async def do_reset(dut):
    dut.rst_i.value      = 1
    dut.act0_in.value    = 0
    dut.act1_in.value    = 0
    dut.weight0_in.value = pack_weight(0, 0, 0)
    dut.weight1_in.value = pack_weight(0, 0, 0)
    dut.psum_in.value    = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await RisingEdge(dut.clk_i)

async def tick(dut):
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_double_buffer_swap(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())
    await do_reset(dut)

    W_a_pe0, W_a_pe1 = 4, 2
    W_b_pe0, W_b_pe1 = 5, 3
    A00,  A10         = 3, 4
    AP00, AP10        = 5, 6

    # -------------------------------------------------------------------------
    # Bootstrap: load W_a into buf[0]  (sel=1 active -> writes buf[~1]=buf[0])
    # -------------------------------------------------------------------------

    # B1: load W_a_pe1 into PE1 and PE0 simultaneously
    dut.weight0_in.value = pack_weight(valid=1, sel=1, data=W_a_pe1)
    dut.weight1_in.value = pack_weight(valid=1, sel=1, data=W_a_pe1)
    dut.act0_in.value = 0; dut.act1_in.value = 0; dut.psum_in.value = 0
    await tick(dut)

    # B2: overwrite PE0 with W_a_pe0; PE1 gets no new write
    dut.weight0_in.value = pack_weight(valid=1, sel=1, data=W_a_pe0)
    dut.weight1_in.value = pack_weight(valid=0, sel=1, data=0)
    await tick(dut)
    # PE0.buf[0]=W_a_pe0, PE1.buf[0]=W_a_pe1

    # -------------------------------------------------------------------------
    # Settle: transition to sel=0 (2 cycles for PE1's sel to catch up via chain)
    # -------------------------------------------------------------------------
    dut.weight0_in.value = pack_weight(valid=0, sel=0, data=0)
    dut.weight1_in.value = pack_weight(valid=0, sel=0, data=0)
    dut.act0_in.value = 0; dut.act1_in.value = 0
    await tick(dut)
    await tick(dut)

    # -------------------------------------------------------------------------
    # Phase 1: buf[0] active (sel=0)
    # Shadow-load W_b into buf[1] while computing with W_a
    # -------------------------------------------------------------------------

    # C1: drive W_b_pe1 to PE1's shadow, W_b_pe1 to PE0's shadow; act0=A00
    dut.weight0_in.value = pack_weight(valid=1, sel=0, data=W_b_pe1)
    dut.weight1_in.value = pack_weight(valid=1, sel=0, data=W_b_pe1)
    dut.act0_in.value = A00; dut.act1_in.value = 0; dut.psum_in.value = 0
    await tick(dut)

    # C2: overwrite PE0 with W_b_pe0; act1=A10 — result registered at end of this edge
    dut.weight0_in.value = pack_weight(valid=1, sel=0, data=W_b_pe0)
    dut.weight1_in.value = pack_weight(valid=0, sel=0, data=0)
    dut.act0_in.value = 0; dut.act1_in.value = A10
    await tick(dut)

    expected_a = W_a_pe0 * A00 + W_a_pe1 * A10   # 4*3 + 2*4 = 20
    assert dut.psum_out.value == expected_a, \
        f"[Phase 1] Expected {expected_a}, got {int(dut.psum_out.value)}"
    cocotb.log.info(f"PASS Phase 1: psum_out={int(dut.psum_out.value)}")

    # -------------------------------------------------------------------------
    # Settle: transition to sel=1
    # -------------------------------------------------------------------------
    dut.weight0_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.weight1_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value = 0; dut.act1_in.value = 0
    await tick(dut)
    await tick(dut)

    # -------------------------------------------------------------------------
    # Phase 2: buf[1] active (sel=1)
    # Shadow-load W_a back into buf[0] while computing with W_b
    # -------------------------------------------------------------------------

    # C1: load W_a_pe1 into both shadows; act0=AP00
    dut.weight0_in.value = pack_weight(valid=1, sel=1, data=W_a_pe1)
    dut.weight1_in.value = pack_weight(valid=1, sel=1, data=W_a_pe1)
    dut.act0_in.value = AP00; dut.act1_in.value = 0; dut.psum_in.value = 0
    await tick(dut)

    # C2: overwrite PE0 with W_a_pe0; act1=AP10 — result registered
    dut.weight0_in.value = pack_weight(valid=1, sel=1, data=W_a_pe0)
    dut.weight1_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value = 0; dut.act1_in.value = AP10
    await tick(dut)

    expected_b = W_b_pe0 * AP00 + W_b_pe1 * AP10   # 5*5 + 3*6 = 43
    assert dut.psum_out.value == expected_b, \
        f"[Phase 2] Expected {expected_b}, got {int(dut.psum_out.value)}"
    cocotb.log.info(f"PASS Phase 2: psum_out={int(dut.psum_out.value)}")
