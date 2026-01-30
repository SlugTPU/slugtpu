import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge

async def clock_start(clk_i, period_ns=10):
    """Start clock with given period (in ns)"""
    c = Clock(clk_i, period_ns, units="ns")
    cocotb.start_soon(c.start(start_high=False))

async def reset_sequence(clk_i, rst_i, num_cycles=10):
    """Reset sequence"""
    await FallingEdge(clk_i)
    rst_i.value = 1
    await ClockCycles(clk_i, num_cycles)
    await FallingEdge(clk_i)
    rst_i.value = 0

