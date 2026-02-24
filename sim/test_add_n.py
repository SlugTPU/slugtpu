import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles, FallingEdge, ReadWrite, ReadOnly
from pathlib import Path
from shared import reset_sequence, clock_start, random_binary_driver
from runner import run_test
from collections import deque
import random

@cocotb.test()
async def reset_test(dut):
    """Test for Initialization"""
    clk_i = dut.clk_i
    rst_i = dut.rst_i

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)
    await FallingEdge(rst_i)


@cocotb.test()
async def add_simple_test(dut):
    N = 8
    INT32_MIN = -(2**31)
    INT32_MAX =  (2**31) - 1

    def rand_s32():
        return random.randint(INT32_MIN, INT32_MAX)

    def to_uint(val):
        return val & 0xFFFFFFFF

    def drive_array(signal, values):
        """Drive an unpacked array MSB-first (cocotb reverses index order)."""
        for i in range(N):
            signal[i].value = to_uint(values[i])

    def read_array(signal):
        """Read an unpacked array, returning signed values."""
        return [signal[i].value.to_signed() for i in range(N)]

    bias_i = [rand_s32() for _ in range(N)]

    input_matrix = [
        [rand_s32() for _ in range(N)]
        for _ in range(N)
    ]

    # Start clock
    cocotb.start_soon(Clock(dut.clk_i, 10, unit="ns").start())

    # Reset
    dut.rst_i.value = 1
    dut.data_valid_i.value = 0
    dut.data_ready_i.value = 1
    drive_array(dut.data_i, [0] * N)
    drive_array(dut.bias_i, bias_i)

    await FallingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    dut.rst_i.value = 0

    errors = 0

    for row_idx, row in enumerate(input_matrix):
        await FallingEdge(dut.clk_i)
        drive_array(dut.data_i, row)
        drive_array(dut.bias_i, bias_i)
        dut.data_valid_i.value = 1

        # Sample output 1 cycle later
        await FallingEdge(dut.clk_i)

        if dut.data_valid_o.value != 1:
            dut._log.error(f"Row {row_idx}: data_valid_o not asserted")
            errors += 1

        got_values = read_array(dut.data_o)

        for i in range(N):
            got = got_values[i]
            raw = row[i] + bias_i[i]
            exp = ((raw + 2**31) % 2**32) - 2**31
            if got != exp:
                dut._log.error(
                    f"Row {row_idx}, element {i}: expected {exp}, got {got} "
                    f"(data={row[i]}, bias={bias_i[i]})"
                )
                errors += 1
            else:
                dut._log.info(
                    f"Row {row_idx}, element {i}: OK  data={row[i]:+d}  "
                    f"bias={bias_i[i]:+d}  sum={exp:+d}"
                )

    await FallingEdge(dut.clk_i)
    dut.data_valid_i.value = 0

    assert errors == 0, f"Test failed with {errors} errors"
    dut._log.info("All checks passed!")
    await FallingEdge(dut.clk_i)


tests = ["reset_test", "load_simple_test"]
proj_path = Path("./rtl").resolve()
sources = [ proj_path/"utils/elastic.sv", proj_path/"scalar_units/add_n.sv"   ]

@pytest.mark.parametrize("testcase", tests)
def test_bias_each(testcase):
    """Runs each test independently. Continues on test failure"""
    
    

    run_test(parameters={}, sources=sources, module_name="test_add_n", hdl_toplevel="add_n", testcase=testcase)

def test_bias_all():
    """Runs each test sequentially as one giant test."""

    # debug print parameters can be idea if a simulator fails silently without telling you why
    # print(f"DEBUG PARAMETERs: {depth_p}")

    run_test(parameters={}, sources=sources, module_name="test_add_n", hdl_toplevel="add_n")