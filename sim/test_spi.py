import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
import random

# Mode 0: CPOL=0, CPHA=0
# IMPORTANT: Drive SCLK/MOSI/CS aligned to clk edges so spi_slave's clk-domain edge detect works.

SYS_CLK_PERIOD_NS = 10



def u32_to_le_bytes(x: int) -> bytes:
    x &= 0xFFFFFFFF
    return bytes([
        (x >> 0) & 0xFF,
        (x >> 8) & 0xFF,
        (x >> 16) & 0xFF,
        (x >> 24) & 0xFF,
    ])


async def wait_cycles(dut, n: int):
    for _ in range(n):
        await RisingEdge(dut.clk)



async def spi_shift_byte(dut, byte_out: int) -> int:
    """
    Mode 0:
      - SCLK idles low
      - Master sets MOSI while SCLK low
      - Slave samples MOSI on rising edge
      - Master samples MISO on rising edge (fine for sim)
    """
    byte_in = 0

    for bit in range(7, -1, -1):
        # Low phase: set MOSI
        dut.sclk.value = 0
        dut.mosi.value = (byte_out >> bit) & 1
        await wait_cycles(dut, SPI_HALF_CYCLES)

        # Rising edge: slave samples here
        dut.sclk.value = 1
        await wait_cycles(dut, 1)  # allow settle for sampling
        byte_in = ((byte_in << 1) | int(dut.miso.value)) & 0xFF
        await wait_cycles(dut, SPI_HALF_CYCLES - 1)

    # Return to idle low
    dut.sclk.value = 0
    await wait_cycles(dut, SPI_HALF_CYCLES)
    return byte_in


async def count_rx_valid(dut, cycles: int = 50000) -> int:
    cnt = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        if int(dut.u_spi_slave.rx_valid.value):
            cnt += 1
    dut._log.info(f"DEBUG rx_valid bytes seen = {cnt}")
    return cnt


async def spi_write_bytes(dut, data: bytes):
    dut.cs_n.value = 0
    await wait_cycles(dut, SPI_HALF_CYCLES)

    for b in data:
        await spi_shift_byte(dut, b)

    # keep CS low a tad longer to avoid boundary glitches
    await wait_cycles(dut, SPI_HALF_CYCLES * 2)

    dut.cs_n.value = 1
    await wait_cycles(dut, SPI_HALF_CYCLES)



@cocotb.test()
async def test_00_smoke(dut):
    cocotb.start_soon(Clock(dut.clk, SYS_CLK_PERIOD_NS, units="ns").start())
    await reset_dut(dut)



tests = ['test_00_smoke']

@pytest.mark.parametrize("testcase", tests)
def test_spi_each(testcase):
    """Runs each test independently. Continues on test failure"""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"spi_slave.sv" ]

    run_test(sources=sources, module_name="test_spi", hdl_toplevel="spi_slave", testcase=testcase)

def test_spi_all():
    """Runs each test sequentially as one giant test."""
    proj_path = Path("./rtl").resolve()
    sources = [ proj_path/"spi_slave.sv" ]

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(sources=sources, module_name="test_spi", hdl_toplevel="spi_slave")
