# sim/test_subzp.py
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# ----------------------------
# Helpers
# ----------------------------

def _has(dut, name: str) -> bool:
    return hasattr(dut, name)

def _set_if_exists(dut, name: str, value: int):
    if _has(dut, name):
        getattr(dut, name).value = value

async def _reset(dut, cycles: int = 5):
    # Try common reset names
    rst_names = ["rst_i", "rst", "reset", "reset_i", "rst_ni"]
    # If active-low exists, we’ll treat *_ni as active-low
    active_low = any(_has(dut, n) for n in ["rst_ni", "reset_n", "reset_ni"])

    # Assert reset
    for n in rst_names:
        if _has(dut, n):
            getattr(dut, n).value = 0 if active_low else 1

    # Wait a few cycles
    for _ in range(cycles):
        await RisingEdge(dut.clk_i if _has(dut, "clk_i") else dut.clk)

    # Deassert reset
    for n in rst_names:
        if _has(dut, n):
            getattr(dut, n).value = 1 if active_low else 0

    for _ in range(2):
        await RisingEdge(dut.clk_i if _has(dut, "clk_i") else dut.clk)

async def _start_clock(dut, period_ns: int = 10):
    clk = dut.clk_i if _has(dut, "clk_i") else dut.clk
    cocotb.start_soon(Clock(clk, period_ns, unit="ns").start())
    await Timer(1, unit="ns")

# ----------------------------
# Cocotb smoke tests
# ----------------------------

@cocotb.test()
async def test_smoke_single_transaction(dut):
    """Smoke test: clock/reset, poke a few inputs, run some cycles. No functional checking."""
    await _start_clock(dut, period_ns=10)
    await _reset(dut, cycles=5)

    # Try common valid/ready style signals (best-effort)
    _set_if_exists(dut, "data_valid_i", 0)
    _set_if_exists(dut, "valid_i", 0)
    _set_if_exists(dut, "in_valid_i", 0)

    # If there is some kind of input payload, poke it.
    for name in ["data_i", "in_data_i", "din_i", "payload_i"]:
        if _has(dut, name):
            getattr(dut, name).value = 0

    # Drive one "transaction" for a couple cycles
    _set_if_exists(dut, "data_valid_i", 1)
    _set_if_exists(dut, "valid_i", 1)
    _set_if_exists(dut, "in_valid_i", 1)

    for name in ["data_i", "in_data_i", "din_i", "payload_i"]:
        if _has(dut, name):
            getattr(dut, name).value = 0x12345678

    for _ in range(3):
        await RisingEdge(dut.clk_i if _has(dut, "clk_i") else dut.clk)

    # Deassert
    _set_if_exists(dut, "data_valid_i", 0)
    _set_if_exists(dut, "valid_i", 0)
    _set_if_exists(dut, "in_valid_i", 0)

    for _ in range(10):
        await RisingEdge(dut.clk_i if _has(dut, "clk_i") else dut.clk)

    dut._log.info("Smoke single transaction completed (no checks).")


@cocotb.test()
async def test_smoke_fuzz(dut):
    """Smoke fuzz: randomize inputs for a while. No output assertions."""
    await _start_clock(dut, period_ns=10)
    await _reset(dut, cycles=5)

    clk = dut.clk_i if _has(dut, "clk_i") else dut.clk

    # Identify some likely input signals to wiggle
    candidate_inputs = []
    for n in ["data_i", "in_data_i", "din_i", "payload_i", "sub_i", "zp_i", "zero_point_i"]:
        if _has(dut, n):
            candidate_inputs.append(n)

    candidate_valids = []
    for n in ["data_valid_i", "valid_i", "in_valid_i", "en_i", "enable_i"]:
        if _has(dut, n):
            candidate_valids.append(n)

    # Run for N cycles, randomly driving whatever exists
    for _ in range(200):
        for v in candidate_valids:
            getattr(dut, v).value = random.getrandbits(1)

        for s in candidate_inputs:
            # choose a 32-bit-ish poke; simulator will truncate to signal width
            getattr(dut, s).value = random.getrandbits(32)

        await RisingEdge(clk)

    # Turn off valids at end
    for v in candidate_valids:
        getattr(dut, v).value = 0

    for _ in range(10):
        await RisingEdge(clk)

    dut._log.info("Smoke fuzz completed (no checks).")


# ----------------------------
# Pytest wrapper 
# ----------------------------

from pathlib import Path
import pytest
from runner import run_test

tests = [
    "test_smoke_single_transaction",
    "test_smoke_fuzz",
]

@pytest.mark.parametrize("testcase", tests)
def test_sub_zp_each(testcase):
    sources = [Path("./rtl/sub_zp.sv").resolve()]
    try:
        run_test(
            parameters={},
            sources=sources,
            module_name="test_subzp",  
            hdl_toplevel="sub_zp",
            testcase=testcase,
            sims=["icarus"],           
        )
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(f"cocotb test '{testcase}' failed (exit code {exc.code})")

def test_sub_zp_all():
    sources = [Path("./rtl/sub_zp.sv").resolve()]
    try:
        run_test(
            parameters={},
            sources=sources,
            module_name="test_subzp",
            hdl_toplevel="sub_zp",
            sims=["icarus"],
        )
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(f"cocotb tests failed (exit code {exc.code})")