import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge
import random

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

async def handshake(clk_i, ready, valid):
    while True:
        await RisingEdge(clk_i)
        if (ready.value == 1 and valid.value == 1):
            break

# stringifies a dict with string keys and integer values into path-safe names
def stringify_dict(dic):
    # TODO: possibly fail on reserved characters?
    return "_".join(f"{k}_{v}" for k, v in sorted(dic.items()))

async def random_binary_driver(clk_i, signal_i, prob=0.5, max_hold=1, stop_event=None):
    """
    Randomly toggle a binary signal on or off
    
    Args:
        clk_i: The clock signal.
        signal_i: The signal to toggle
        prob: Probability (0.0 to 1.0) of the signal being high.
        max_hold: Maximum number of cycles to stay in high or low
    """
    while True:
        if (stop_event is not None and stop_event.is_set()):
            break

        new_val = 1 if random.random() < prob else 0
        signal_i.value = new_val

        hold_cycles = random.randint(1, max_hold)

        for _ in range(hold_cycles):
            await RisingEdge(clk_i)

        await FallingEdge(clk_i)
