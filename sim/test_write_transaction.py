import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer, RisingEdge
from pathlib import Path
from shared import reset_sequence, clock_start
from runner import run_test
import random

@cocotb.test()
async def test_simple(dut):
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    data_i = dut.data_i
    ready_i = dut.ready_i
    valid_i = dut.valid_i
    valid_o = dut.valid_o
    ready_o = dut.ready_o

    addr_i = dut.addr_i
    amount = dut.transaction_amount_i
    load_valid_i = dut.load_valid_i
    load_ready_o = dut.load_ready_o

    addr_o = dut.addr_o
    data_o =dut.data_o

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await FallingEdge(rst_i)
    await FallingEdge(clk_i)

    assert load_ready_o.value == 1
    assert valid_o.value == 0
    assert ready_o.value == 0

    await FallingEdge(clk_i)

    count = 8
    start_addr = 0
    load_valid_i.value = 1
    amount.value = count
    addr_i.value = start_addr
    valid_i.value = 0
    ready_i.value = 0
    await FallingEdge(clk_i)

    assert load_ready_o.value == 0
    assert valid_o.value == 0
    assert ready_o.value == 0
    await RisingEdge(clk_i)

    for i in range(count):
        
        ready_i.value = 1
        valid_i.value = 1
        data_i.value = i

        await FallingEdge(clk_i)
        assert valid_o.value == 1
        assert ready_o.value == 1
        assert data_o.value == i
        assert addr_o.value == i+start_addr
        await RisingEdge(clk_i)
    await FallingEdge(clk_i)
    assert load_ready_o.value == 1
    assert valid_o.value == 0



tests = [
    'test_simple'
]

proj_path = Path("./rtl").resolve()
sources = [
    proj_path / "sram/memory_transaction.sv",
]

@pytest.mark.parametrize("testcase", tests)
def test_write_each(testcase):
    """Runs each test independently. Continues on test failure."""
    run_test(parameters={}, sources=sources, module_name="test_write_transaction", hdl_toplevel="memory_transaction", testcase=testcase, sims=['icarus'])

def test_write_all():
    """Runs all tests sequentially in one simulation."""
    run_test(parameters={}, sources=sources, module_name="test_write_transaction", hdl_toplevel="memory_transaction", sims=['icarus'])