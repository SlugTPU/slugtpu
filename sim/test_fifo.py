import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge
from pathlib import Path
from shared import reset_sequence, clock_start
from runner import run_test
from collections import deque

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)


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

    # stop sending values
    await FallingEdge(clk_i)
    valid_i.value = 0
    await RisingEdge(clk_i)

    # dequeue
    for _ in range(2 ** depth_log2_p.value.to_unsigned()):
        await FallingEdge(clk_i)
        ready_i.value = 1
        await RisingEdge(clk_i)
        assert data_o.value.to_unsigned() == fifo_model.popleft(), "Expected"

@pytest.mark.parametrize("depth_log2_p", [1, 3])
def test_fifo_all(depth_log2_p):
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"fifo.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={"DEPTH_LOG2_P": depth_log2_p}, sources=sources, module_name="test_fifo", hdl_toplevel="fifo")
