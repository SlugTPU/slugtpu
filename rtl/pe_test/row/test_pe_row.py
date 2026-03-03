"""
test_pe_row.py  -  cocotb testbench for pe_row (2 PEs side by side)

Two matrix test — verifies activation propagation and double buffer swap.

Matrix 1 weights: w00=3 (PE0), w01=5 (PE1)  -> loaded into buf[1]
Matrix 2 weights: wp00=2 (PE0), wp01=4 (PE1) -> loaded into buf[0] while matrix 1 computes

Matrix 1 activations: A00=6, A01=7
Matrix 2 activations: Ap00=8, Ap01=9

Expected outputs (psum_in=0 each cycle):
  C2: PE0 = w00*A00   = 3*6 = 18
  C3: PE0 = w00*A01   = 3*7 = 21,  PE1 = w01*A00  = 5*6 = 30
  C4: PE0 = wp00*Ap00 = 2*8 = 16,  PE1 = w01*A01  = 5*7 = 35
  C5: PE0 = wp00*Ap01 = 2*9 = 18,  PE1 = wp01*Ap00 = 4*8 = 32
  C6:                               PE1 = wp01*Ap01 = 4*9 = 36
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import FallingEdge

async def do_reset(dut):
    dut.rst_i.value         = 1
    dut.act_in.value        = 0
    dut.weight0_in.value    = 0
    dut.weight1_in.value    = 0
    dut.weight_valid0.value = 0
    dut.weight_valid1.value = 0
    dut.buf_sel0.value      = 0
    dut.buf_sel1.value      = 0
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await RisingEdge(dut.clk_i)

async def tick(dut):
    await FallingEdge(dut.clk_i)


@cocotb.test()
async def test_two_matrix(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    # Matrix 1 weights
    w00 = 3;  w01 = 5
    # Matrix 2 weights
    wp00 = 2; wp01 = 4
    # Throwaway (gets overwritten before buf swap)
    wp10 = 99; wp11 = 99; w11 = 99;

    # Matrix 1 activations
    A00 = 6;  A01 = 7
    # Matrix 2 activations
    Ap00 = 8; Ap01 = 9

    # -------------------------------------------------------------------
    # C1: w00->PE0.buf[1] (real),  w11(throwaway)->PE1.buf[1]
    #     buf_sel=0 active -> ~buf_sel=1 is shadow
    # -------------------------------------------------------------------
    dut.weight0_in.value    = w00
    dut.weight1_in.value    = w11   # throwaway, PE1 gets real weight next cycle
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 1
    dut.buf_sel0.value      = 0
    dut.buf_sel1.value      = 0
    dut.act_in.value        = 0
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)
    # PE0.buf[1]=w00, PE1.buf[1]=wp11(throwaway)

    # -------------------------------------------------------------------
    # C2: 
    # -------------------------------------------------------------------
    dut.weight0_in.value    = wp10
    dut.weight1_in.value    = w01
    dut.weight_valid0.value = 1    # wp10 -> PE0.buf[0] (throwaway)
    dut.weight_valid1.value = 1    # w01  -> PE1.buf[1] (overwrites throwaway)
    dut.buf_sel0.value      = 1    # flip: buf[0]=w00 now active on PE0
    dut.buf_sel1.value      = 0    
    dut.act_in.value        = A00
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)
    # PE0.buf[1]=w00 active, PE1.buf[1]=w01 active, buf_sel settled

    psum0 = int(dut.psum0_out.value)
    expected = w00 * A00
    assert psum0 == expected, f"[C2 PE0] Expected {expected}, got {psum0}"
    cocotb.log.info(f"PASS: C2 PE0  expected={expected}  got={psum0}")
    
    # -------------------------------------------------------------------
    # C3: 
    # -------------------------------------------------------------------
    dut.weight0_in.value    = wp00
    dut.weight1_in.value    = wp11
    dut.weight_valid0.value = 1    # wp00 -> PE0.buf[0]
    dut.weight_valid1.value = 1    # wp11 -> PE1.buf[0] (throwaway)
    dut.act_in.value        = A00
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C4: A01->PE0 (computes w00*A01), A00 flows to PE1 (computes w01*A00)
    #     wp01 -> PE1.buf[0] (overwrites throwaway)
    # READ: PE0 = w00*A00 = 18
    # -------------------------------------------------------------------
    psum0 = int(dut.psum0_out.value)
    expected = w00 * A00   # 3*6 = 18
    assert psum0 == expected, f"[C4 PE0] Expected {expected}, got {psum0}"
    cocotb.log.info(f"PASS: C4 PE0  expected={expected}  got={psum0}")

    dut.weight0_in.value    = 0
    dut.weight1_in.value    = wp01
    dut.weight_valid0.value = 0
    dut.weight_valid1.value = 1    # wp01 -> PE1.buf[0] (overwrites wp11)
    dut.act_in.value        = A01
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C5: buf_sel0 flips to 0 (buf[0]=wp00 active), Ap00->PE0
    #     A01 flows to PE1 (computes w01*A01)
    # READ: PE0 = w00*A01 = 21,  PE1 = w01*A00 = 30
    # -------------------------------------------------------------------
    psum0 = int(dut.psum0_out.value)
    expected = w00 * A01   # 3*7 = 21
    assert psum0 == expected, f"[C5 PE0] Expected {expected}, got {psum0}"
    cocotb.log.info(f"PASS: C5 PE0  expected={expected}  got={psum0}")

    psum1 = int(dut.psum1_out.value)
    expected = w01 * A00   # 5*6 = 30
    assert psum1 == expected, f"[C5 PE1] Expected {expected}, got {psum1}"
    cocotb.log.info(f"PASS: C5 PE1  expected={expected}  got={psum1}")

    dut.weight_valid0.value = 0
    dut.weight_valid1.value = 0
    dut.buf_sel0.value      = 0    # flip: buf[0]=wp00 now active on PE0
    dut.act_in.value        = 0    # let buf_sel settle
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C6: Ap00->PE0 (computes wp00*Ap00), A01 flows to PE1 (computes w01*A01)
    # READ: PE1 = w01*A01 = 35  (buf_sel1 still 1, using w01)
    # -------------------------------------------------------------------
    psum1 = int(dut.psum1_out.value)
    expected = w01 * A01   # 5*7 = 35
    assert psum1 == expected, f"[C6 PE1] Expected {expected}, got {psum1}"
    cocotb.log.info(f"PASS: C6 PE1  expected={expected}  got={psum1}")

    dut.act_in.value        = Ap00
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C7: Ap01->PE0 (computes wp00*Ap01), Ap00 flows to PE1
    #     buf_sel1 flips to 0 (buf[0]=wp01 active on PE1)
    # READ: PE0 = wp00*Ap00 = 16
    # -------------------------------------------------------------------
    psum0 = int(dut.psum0_out.value)
    expected = wp00 * Ap00   # 2*8 = 16
    assert psum0 == expected, f"[C7 PE0] Expected {expected}, got {psum0}"
    cocotb.log.info(f"PASS: C7 PE0  expected={expected}  got={psum0}")

    dut.weight_valid1.value = 0
    dut.buf_sel1.value      = 0    # flip: buf[0]=wp01 now active on PE1
    dut.act_in.value        = Ap01
    dut.psum0_in.value      = 0
    dut.psum1_in.value      = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C8: act=0, Ap01 flows to PE1
    # READ: PE0 = wp00*Ap01 = 18
    # -------------------------------------------------------------------
    psum0 = int(dut.psum0_out.value)
    expected = wp00 * Ap01   # 2*9 = 18
    assert psum0 == expected, f"[C8 PE0] Expected {expected}, got {psum0}"
    cocotb.log.info(f"PASS: C8 PE0  expected={expected}  got={psum0}")

    dut.act_in.value   = 0
    dut.psum0_in.value = 0
    dut.psum1_in.value = 0
    await tick(dut)

    # -------------------------------------------------------------------
    # C9: READ: PE1 = wp01*Ap00 = 32
    # -------------------------------------------------------------------
    psum1 = int(dut.psum1_out.value)
    expected = wp01 * Ap00   # 4*8 = 32
    assert psum1 == expected, f"[C9 PE1] Expected {expected}, got {psum1}"
    cocotb.log.info(f"PASS: C9 PE1  expected={expected}  got={psum1}")

    await tick(dut)

    # -------------------------------------------------------------------
    # C10: READ: PE1 = wp01*Ap01 = 36
    # -------------------------------------------------------------------
    psum1 = int(dut.psum1_out.value)
    expected = wp01 * Ap01   # 4*9 = 36
    assert psum1 == expected, f"[C10 PE1] Expected {expected}, got {psum1}"
    cocotb.log.info(f"PASS: C10 PE1  expected={expected}  got={psum1}")

    cocotb.log.info("PASS: test_two_matrix complete")
