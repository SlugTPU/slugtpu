import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

async def do_reset(dut):
    dut.rst_i.value         = 1
    dut.act0.value          = 0
    dut.act1.value          = 0
    dut.weight0.value       = 0
    dut.weight1.value       = 0
    dut.weight_valid0.value = 0
    dut.weight_valid1.value = 0
    dut.act_valid0.value    = 0
    dut.act_valid1.value    = 0
    await RisingEdge(dut.clk_i)
    await RisingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await RisingEdge(dut.clk_i)


@cocotb.test()
async def test_basic_flow(dut):
    """
    Check at C5:
      psum_out1 = A00*W00 + A01*W10
    """
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    await do_reset(dut)

    SEL = 1 << 8

    W00 = 2;  W01 = 3;  W10 = 4;  W11 = 10
    WP00 = 9; WP11 = 10; WP10 = 2; WP01 = 3
    A00 = 1;  A01 = 2;  A10 = 6;  A11 = 7
    WPP10 = 3; WPP00 = 4; WPP01 = 2; WPP11 = 5
    AP00 = 3; AP01 = 5; AP10 = 4; AP11 = 7
    APP00 = 4
    # -------------------------------------------------------------------
    # C1: 
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value       = W10
    dut.weight1.value       = 0
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 0
    dut.act0.value          = 0
    dut.act1.value          = 0
    dut.act_valid0.value    = 0
    dut.act_valid1.value    = 0

    # -------------------------------------------------------------------
    # C2:
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value       = W00
    dut.weight1.value       = W11
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 1
    dut.act0.value          = 0
    dut.act1.value          = 0
    dut.act_valid0.value    = 0
    dut.act_valid1.value    = 0

    # -------------------------------------------------------------------
    # C3:
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value       = WP10 | SEL
    dut.weight1.value       = W01
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 1
    dut.act0.value          = A00
    dut.act1.value          = 0
    dut.act_valid0.value    = 1
    dut.act_valid1.value    = 0

    # -------------------------------------------------------------------
    # C4: 
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value       = WP00 | SEL
    dut.weight1.value       = WP11 | SEL
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 1
    dut.act0.value          = A10
    dut.act1.value          = A01
    dut.act_valid0.value    = 1
    dut.act_valid1.value    = 1

    # -------------------------------------------------------------------
    # C5: 
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value = WPP10
    dut.weight1.value = WP01 | SEL
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 1
    dut.act0.value = AP00 | SEL
    dut.act1.value = A11
    
    cocotb.log.info(f"psum_out1 raw = {dut.psum_out1.value}")
    psum1 = int(dut.psum_out1.value)
    expected1 = A00 * W00 + A01 * W10   # 1*2 + 2*4 = 10
    assert psum1 == expected1, f"[C5 psum_out1] Expected {expected1}, got {psum1}"
    cocotb.log.info(f"PASS: C5 psum_out1  expected={expected1}  got={psum1}")
    cocotb.log.info(f"psum_out2 at C5 = {dut.psum_out2.value}")
    # -------------------------------------------------------------------
    # C6:
    # -------------------------------------------------------------------
    await FallingEdge(dut.clk_i)
    dut.weight0.value = WPP00
    dut.weight1.value = WPP11
    dut.act0.value = AP10 | SEL
    dut.act1.value = AP01 | SEL
    
    cocotb.log.info(f"psum_out1 raw = {dut.psum_out1.value}")
    psum1 = int(dut.psum_out1.value)
    expected1 = A11 * W10 + A10 * W00
    assert psum1 == expected1, f"[C6 psum_out1] Expected {expected1}, got {psum1}"
    cocotb.log.info(f"PASS: C6 psum_out1 expected={expected1}  got={psum1}")
    
    cocotb.log.info(f"psum_out2 raw = {dut.psum_out2.value}")
    psum2 = int(dut.psum_out2.value)
    expected2 = A00 * W01 + A01 * W11
    assert psum2 == expected2, f"[C6 psum_out2] Expected {expected2}, got {psum2}"
    cocotb.log.info(f"PASS: C6 psum_out2  expected={expected2}  got={psum2}")

    #-------------------------------------------------------------------
    # C7:
    # ------------------------------------------------------------------- 
    await FallingEdge(dut.clk_i)
    dut.weight0.value = W10 | SEL
    dut.weight1.value = WPP01
    dut.act0.value = APP00
    dut.act1.value = AP11 | SEL
    
    cocotb.log.info(f"psum_out1 raw = {dut.psum_out1.value}")
    psum1 = int(dut.psum_out1.value)
    expected1 = AP00 * WP00 + AP01 * WP10
    assert psum1 == expected1, f"[C7 psum_out1] Expected {expected1}, got {psum1}"
    cocotb.log.info(f"PASS: C7 psum_out1 expected={expected1}  got={psum1}")
    
    cocotb.log.info(f"psum_out2 raw = {dut.psum_out2.value}")
    psum2 = int(dut.psum_out2.value)
    expected2 = A10 * W01 + A11 * W11
    assert psum2 == expected2, f"[C7 psum_out2] Expected {expected2}, got {psum2}"
    cocotb.log.info(f"PASS: C7 psum_out2  expected={expected2}  got={psum2}")

