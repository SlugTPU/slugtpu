import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

async def do_reset(dut):
    dut.rst_i.value = 1

    dut.act0.value = 0
    dut.act1.value = 0

    dut.weight0.value = 0
    dut.weight1.value = 0

    dut.weight_valid0 = 0
    dut.weight_valid1 = 0
    
    dut.act_valid0.value = 0
    dut.act_valid1.value = 0

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
    
    # C1
    await FallingEdge(dut.clk_i)

    W11 = 5; W01 = 3; W10 = 4; W00 = 2;
    A10 = 3; A00 = 1; A11 = 2; A10 = 6;
    WP11 = 1; WP01 = 1; WP10 = 1; WP00 = 1;
    AP01 = 1;
    
    dut.act0.value = 0
    dut.act1.value = 0
    dut.act_valid0.value = 0
    dut.act_valid1.value = 0

    dut.weight0.value = W10
    dut.weight1.value = 0
    dut.weight_valid0.value = 1
    dut.weight_valid1.value = 0

    # C2
    await FallingEdge(dut.clk_i)
    dut.weight0.value = W00
    dut.weight1.value = W11
    dut.weight_value1.value = 1
    
    # C3
    await FallingEdge(dut.clk_i)
    dut.weight0.value = WP10 | 1<<8
    dut.weight1.value = W01
    dut.act0_in.value = A00
    dut.act1_in.value = 0
    dut.act0_valid.value = 1
    dut.act1_valid.value = 0

    # C4
    await FallingEdge(dut.clk_i)
    dut.weight0.value = WP00 | 1<<8
    dut.weight1.value = WP11 | 1<<8
    dut.act0_in.value = A01
    dut.act1_in.value = A10
    dut.act1_valid.value = 1

    # C5
    await FallingEdge(dut.clk_i)
    dut.weight0.value = WPP10
    dut.weight1.value = WP01
    dut.act0_in.value = AP01 | 1<<8
    dut.act1_in.value = A11


    got = int(dut.psum_out.value)
    expected = W2 * A00 + W1 * A10
    cocotb.log.info(f"psum_out = {got},  expected = {expected}")
    assert got == expected, f"FAIL: expected {expected}, got {got}"
    cocotb.log.info("PASS: test_basic_flow")
