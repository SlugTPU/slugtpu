import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
import random

tests = ["reset_test", "fifo_simple_test", "fifo_stream_test"]

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)
    await FallingEdge(rst_i)


@cocotb.test()
async def fifo_simple_test(dut):
    """Fills up queue and then empties"""
    depth_log2_p = dut.DEPTH_LOG2_P
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    ready_o = dut.ready_o
    ready_i = dut.ready_i
    valid_i = dut.valid_i
    data_i = dut.data_i
    data_o = dut.data_o

    fifo_model = deque(maxlen=2**depth_log2_p.value.to_unsigned())

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await FallingEdge(rst_i)
    valid_i.value = 0
    ready_i.value = 0

    await RisingEdge(clk_i)
    assert ready_o.value == 1, "Empty FIFO should still be ready to accept input even when ready_i == 0"

    # send values
    for i in range(2 ** depth_log2_p.value.to_unsigned()):
        await FallingEdge(clk_i)
        valid_i.value = 1
        data_i.value = i
        fifo_model.append(i)
        await RisingEdge(clk_i)

    await ReadOnly(clk_i)
    assert not ready_o.value, "ready_o expected to be low when full!"

    # stop sending values
    await FallingEdge(clk_i)
    valid_i.value = 0
    await RisingEdge(clk_i)

    # dequeue
    for _ in range(2 ** depth_log2_p.value.to_unsigned()):
        await FallingEdge(clk_i)
        ready_i.value = 1
        await RisingEdge(clk_i)
        assert data_o.value.to_unsigned() == fifo_model.popleft(), "Did not receive expected value"

    # FIFO should be empty by now

@cocotb.test()
@cocotb.parametrize(with_pressure=[False, True])
async def fifo_random_stream_test(dut, with_pressure):
    clk_i = dut.clk_i
    rst_i = dut.rst_i
    ready_o = dut.ready_o
    ready_i = dut.ready_i
    valid_i = dut.valid_i
    valid_o = dut.valid_o
    data_i = dut.data_i
    data_o = dut.data_o

    fifo_model = deque()

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    await FallingEdge(rst_i)

    if (with_pressure):
        cocotb.start_soon(random_binary_driver(clk_i, valid_i, prob=0.5, max_hold=10))
        cocotb.start_soon(random_binary_driver(clk_i, ready_i, prob=0.5, max_hold=10))
    else:
        valid_i.value = 1
        ready_i.value = 1

    # stream 10 random values
    n_wr = 0
    n_rd = 0
    while (n_wr < 10 and n_rd < 10):
        val = n_wr
        data_i.value = val
        await RisingEdge(clk_i)
        await ReadOnly()

        if valid_i.value == 1 and ready_o.value == 1:
            fifo_model.append(val)
            n_wr += 1

        if valid_o.value == 1:
            if len(fifo_model) > 0:
                assert fifo_model[0] == data_o.value.to_unsigned(), "Didn't match model"

                if ready_i.value == 1:
                    fifo_model.popleft()
                    n_rd += 1

        await FallingEdge(clk_i)


@pytest.mark.parametrize("depth_log2_p", [1, 3])
@pytest.mark.parametrize("testcase", tests)
def test_fifo_each(depth_log2_p, testcase):
    """Runs each test independently. Continues on test failure"""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"fifo.sv" ]

    run_test(parameters={"DEPTH_LOG2_P": depth_log2_p}, sources=sources, module_name="test_fifo", hdl_toplevel="fifo", testcase=testcase)

@pytest.mark.parametrize("depth_log2_p", [1, 3])
def test_fifo_all(depth_log2_p):
    """Runs each test sequentially as one giant test."""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"fifo.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={"DEPTH_LOG2_P": depth_log2_p}, sources=sources, module_name="test_fifo", hdl_toplevel="fifo")
