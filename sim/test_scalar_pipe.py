import pytest
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from pathlib import Path
from shared import clock_start, reset_sequence
from runner import run_test
import random

N = 8
FIXED_SHIFT = 16


def to_uint(val, width=32):
    return val & ((1 << width) - 1)


def drive_array(signal, values, width=32):
    for i in range(len(values)):
        signal[i].value = to_uint(values[i], width)


def read_array_s8(signal, n):
    out = []
    for i in range(n):
        raw = int(signal[i].value) & 0xFF
        out.append(raw - 256 if raw >= 128 else raw)
    return out


def quantize(psum, m0, shift=FIXED_SHIFT):
    """Matches quantizer_mul.sv: multiply, round, shift, saturate."""
    product = psum * m0
    rounded = product + (1 << (shift - 1))
    # >> is arithmetic for negative numbers in py
    shifted = rounded >> shift
    return max(-128, min(127, shifted))


def scalar_pipe_ref(data, bias, zp, scale):
    """Golden model for the full pipeline."""
    out = []
    for i in range(len(data)):
        v = data[i] + bias[i]
        v = max(0, v)
        v = v - zp[i]
        v = quantize(v, scale[i])
        out.append(v)
    return out


async def init(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    dut.rst_i.value = 1
    dut.data_valid_i.value = 0
    dut.data_ready_i.value = 1
    drive_array(dut.data_i, [0] * N)
    drive_array(dut.bias_i, [0] * N)
    drive_array(dut.zero_point_i, [0] * N)
    drive_array(dut.scale_i, [0] * N)
    await ClockCycles(dut.clk_i, 5)
    await FallingEdge(dut.clk_i)
    dut.rst_i.value = 0
    await ClockCycles(dut.clk_i, 2)


@cocotb.test()
async def test_basic(dut):
    """Single vector through pipeline, verify each lane."""
    await init(dut)

    data  = [100, -50, 200, 0, 50, 75, -10, 150]
    bias  = [10,   20, -30, 50, -5, 10,  15, -20]
    zp    = [5,     5,   5,  5,  5,  5,   5,   5]
    scale = [1 << FIXED_SHIFT] * N  # 1.0 in Q16

    expected = scalar_pipe_ref(data, bias, zp, scale)

    drive_array(dut.bias_i, bias)
    drive_array(dut.zero_point_i, zp)
    drive_array(dut.scale_i, scale)

    # one valid cycle
    await FallingEdge(dut.clk_i)
    drive_array(dut.data_i, data)
    dut.data_valid_i.value = 1

    await FallingEdge(dut.clk_i)
    dut.data_valid_i.value = 0

    # wait for output
    for cyc in range(20):
        await RisingEdge(dut.clk_i)
        if dut.data_valid_o.value == 1:
            break
    else:
        assert False, "data_valid_o never asserted"

    got = read_array_s8(dut.data_o, N)
    cocotb.log.info(f"expected: {expected}")
    cocotb.log.info(f"got: {got}")
    for i in range(N):
        assert got[i] == expected[i], \
            f"lane {i}: expected {expected[i]}, got {got[i]}"


@cocotb.test()
async def test_saturation(dut):
    """Verify int8 saturation clamps to [-128, 127]."""
    await init(dut)

    # large pos values that should saturate to 127
    data  = [10000] * N
    bias  = [0] * N
    zp    = [0] * N
    scale = [1 << FIXED_SHIFT] * N

    expected = scalar_pipe_ref(data, bias, zp, scale)
    assert all(e == 127 for e in expected)

    drive_array(dut.bias_i, bias)
    drive_array(dut.zero_point_i, zp)
    drive_array(dut.scale_i, scale)

    await FallingEdge(dut.clk_i)
    drive_array(dut.data_i, data)
    dut.data_valid_i.value = 1
    await FallingEdge(dut.clk_i)
    dut.data_valid_i.value = 0

    for _ in range(20):
        await RisingEdge(dut.clk_i)
        if dut.data_valid_o.value == 1:
            break

    got = read_array_s8(dut.data_o, N)
    for i in range(N):
        assert got[i] == 127, f"lane {i}: expected 127, got {got[i]}"


@cocotb.test()
async def test_multi_vector(dut):
    """Push multiple vectors back-to-back, check all outputs."""
    await init(dut)

    vectors = [
        [10, 20, 30, 40, 50, 60, 70, 80],
        [-5, -10, -15, -20, 100, 100, 100, 100],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ]
    bias  = [1, 2, 3, 4, 5, 6, 7, 8]
    zp    = [2, 2, 2, 2, 2, 2, 2, 2]
    scale = [1 << FIXED_SHIFT] * N

    expected_all = [scalar_pipe_ref(v, bias, zp, scale) for v in vectors]

    drive_array(dut.bias_i, bias)
    drive_array(dut.zero_point_i, zp)
    drive_array(dut.scale_i, scale)

    # drive all vectors on consecutive cycles
    for v in vectors:
        await FallingEdge(dut.clk_i)
        drive_array(dut.data_i, v)
        dut.data_valid_i.value = 1

    await FallingEdge(dut.clk_i)
    dut.data_valid_i.value = 0

    # collect outputs
    results = []
    for _ in range(40):
        await RisingEdge(dut.clk_i)
        if dut.data_valid_o.value == 1:
            results.append(read_array_s8(dut.data_o, N))
            if len(results) == len(vectors):
                break

    assert len(results) == len(vectors), \
        f"expected {len(vectors)} outputs, got {len(results)}"

    for idx, (got, exp) in enumerate(zip(results, expected_all)):
        cocotb.log.info(f"vec {idx}: expected={exp}, got={got}")
        for i in range(N):
            assert got[i] == exp[i], \
                f"vec {idx} lane {i}: expected {exp[i]}, got {got[i]}"


#pytest

SOURCES = [
    Path("./rtl/scalar_units/scalar_pipe.sv").resolve(),
    Path("./rtl/scalar_units/add_n.sv").resolve(),
    Path("./rtl/scalar_units/relu_n.sv").resolve(),
    Path("./rtl/utils/elastic.sv").resolve(),
]

PARAMS = {"N": N, "PSUM_W": 32, "M0_W": 32, "FIXED_SHIFT": FIXED_SHIFT}

tests = [
    "test_basic",
    "test_saturation",
    "test_multi_vector",
]


@pytest.mark.parametrize("testcase", tests)
def test_scalar_pipe(testcase):
    try:
        run_test(
            parameters=PARAMS,
            sources=SOURCES,
            module_name="test_scalar_pipe",
            hdl_toplevel="scalar_pipe",
            testcase=testcase,
            sims=["icarus"],
        )
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(f"cocotb test '{testcase}' failed (exit code {exc.code})")
