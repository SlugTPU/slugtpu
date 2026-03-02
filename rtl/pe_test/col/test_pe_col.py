"""
test_pe_col.py  –  cocotb testbench for pe_col (2 PEs stacked vertically)

Topology:
    act0, weight  →  [PE0]  →  psum_mid  = W × A0
                                   ↓
    act1, weight  →  [PE1]  →  psum_out  = W × A0 + W × A1 = W × (A0 + A1)

Because psum flows through TWO registered stages we must wait 2 clock cycles
after inputs are stable before reading psum_out.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

def pack_weight(valid, sel, data):
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

async def load_weight(dut, data, sel):
    dut.weight_in.value = pack_weight(valid=1, sel=sel, data=data)
    await RisingEdge(dut.clk_i)
    dut.weight_in.value = pack_weight(valid=0, sel=sel, data=0)

async def tick(dut):
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_reset(dut):
    """psum_out should be 0 after reset."""
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)
    assert dut.psum_out.value == 0, f"Expected 0, got {dut.psum_out.value}"
    cocotb.log.info("PASS: reset")


@cocotb.test()
async def test_two_pe_accumulation(dut):
    """
    Core test: psum_out = W * (A00 + A10)

    W   = 3
    A00 = 4   (fed into PE0)
    A10 = 5   (fed into PE1)

    PE0 output (psum_mid) = W * A00        =  3 * 4  = 12   (after 1 cycle)
    PE1 output (psum_out) = psum_mid + W * A10 = 12 + 15 = 27   (after 2 cycles)
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    W   = 3
    A00 = 4
    A10 = 5

    # load W into buf[1] on both PEs (sel=0 active -> write ~sel=1)
    await load_weight(dut, data=W, sel=0)

    # swap sel=1 so buf[1] becomes active, drive activations
    dut.weight_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0 #delay
    dut.psum_in.value   = 0
    await tick(dut)

    dut.act0_in.value   = 0
    dut.act1_in.value   = A10 
    await tick(dut)

    await tick(dut)

    expected = W * (A00 + A10)   # 3 * (4 + 5) = 27
    assert dut.psum_out.value == expected, \
        f"Expected {expected}, got {dut.psum_out.value}"
    cocotb.log.info(f"PASS: two_pe_accumulation  psum_out={dut.psum_out.value}")


@cocotb.test()
async def test_psum_in_offset(dut):
    """An initial psum_in offset should be carried through both stages."""
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    W      = 2
    A00    = 3
    A10    = 4
    offset = 10

    await load_weight(dut, data=W, sel=0)

    dut.weight_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0
    dut.psum_in.value   = offset
    await tick(dut)
    
    dut.act0_in.value   = 0
    dut.act1_in.value   = A10
    await tick(dut)

    await tick(dut)
    
    expected = offset + W * (A00 + A10)   # 10 + 2*(3+4) = 24
    assert dut.psum_out.value == expected, \
        f"Expected {expected}, got {dut.psum_out.value}"
    cocotb.log.info(f"PASS: psum_in_offset  psum_out={dut.psum_out.value}")


@cocotb.test()
async def test_zero_activations(dut):
    """With both activations = 0, psum_out should equal psum_in."""
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    await load_weight(dut, data=255, sel=0)

    dut.weight_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value   = 0
    dut.act1_in.value   = 0
    dut.psum_in.value   = 0

    await tick(dut)
    await tick(dut)

    assert dut.psum_out.value == 0, \
        f"Expected 0, got {dut.psum_out.value}"
    cocotb.log.info("PASS: zero_activations")


@cocotb.test()
async def test_double_buffer_swap(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    W_a = 4
    W_b = 2
    A00 = 3
    A10 = 3

    # --- Phase 1: buf[0] is active with W_a, stream activations
    # load W_a into buf[0] (sel=1 active -> write ~1=0... wait)
    # actually: sel=0 active -> write into buf[~0] = buf[1]
    # so to get W_a into buf[0], we need sel=1 active when loading
    await load_weight(dut, data=W_a, sel=1)   # W_a -> buf[0]

    # use buf[0] (sel=0), stream act tiles AND simultaneously load W_b into buf[1]
    # Cycle 1: skew - feed A00, delay A10, AND load W_b into shadow buf[1]
    dut.weight_in.value = pack_weight(valid=1, sel=0, data=W_b)  # load W_b into buf[1] while computing
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0
    dut.psum_in.value   = 0
    await tick(dut)

    # Cycle 2: W_b finished loading, feed A10 with sel still 0
    dut.weight_in.value = pack_weight(valid=0, sel=0, data=0)
    dut.act0_in.value   = 0
    dut.act1_in.value   = A10
    await tick(dut)

    # Cycle 3: read result
    await tick(dut)

    expected_a = W_a * (A00 + A10)   # 4 * 6 = 24
    assert dut.psum_out.value == expected_a, \
        f"[buf[0]] Expected {expected_a}, got {dut.psum_out.value}"
    cocotb.log.info(f"PASS: buf[0] active  psum_out={dut.psum_out.value}")

    # --- Phase 2: flip to buf[1] which already has W_b loaded
    # stream new activation tiles with sel=1
    dut.weight_in.value = pack_weight(valid=0, sel=1, data=0)
    dut.act0_in.value   = A00
    dut.act1_in.value   = 0
    dut.psum_in.value   = 0
    await tick(dut)

    dut.act0_in.value = 0
    dut.act1_in.value = A10
    await tick(dut)

    await tick(dut)

    expected_b = W_b * (A00 + A10)   # 2 * 6 = 12
    assert dut.psum_out.value == expected_b, \
        f"[buf[1]] Expected {expected_b}, got {dut.psum_out.value}"
    cocotb.log.info(f"PASS: buf[1] active  psum_out={dut.psum_out.value}")
