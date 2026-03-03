from __future__ import annotations
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, Timer
import pytest
from runner import run_test

SEL1 = 1 << 8

def pack(data, sel_bit):
    return (int(bool(sel_bit)) << 8) | (data & 0xFF)

async def drive(sig, val):
    sig.value = int(val)
    await Timer(1, units="ps")

async def init_dut(dut):
    cocotb.start_soon(Clock(dut.clk_i, 10, units="ns").start())
    for sig in [dut.act0, dut.act1, dut.weight0, dut.weight1,
                dut.weight_valid0, dut.weight_valid1, dut.act_valid0, dut.act_valid1]:
        await drive(sig, 0)
    await drive(dut.rst_i, 1)
    for _ in range(5): await RisingEdge(dut.clk_i)
    await drive(dut.rst_i, 0)
    await RisingEdge(dut.clk_i)

async def set_weights(dut, w0, w1, wv0=1, wv1=1):
    await FallingEdge(dut.clk_i)
    await drive(dut.weight0, w0);       await drive(dut.weight1, w1)
    await drive(dut.weight_valid0, wv0); await drive(dut.weight_valid1, wv1)
    await RisingEdge(dut.clk_i)

async def set_acts(dut, a0, a1, av0=1, av1=1):
    await FallingEdge(dut.clk_i)
    await drive(dut.act0, a0);       await drive(dut.act1, a1)
    await drive(dut.act_valid0, av0); await drive(dut.act_valid1, av1)
    await RisingEdge(dut.clk_i)

async def idle(dut, cycles=1):
    await FallingEdge(dut.clk_i)
    await drive(dut.weight_valid0, 0); await drive(dut.weight_valid1, 0)
    await drive(dut.act_valid0, 0);    await drive(dut.act_valid1, 0)
    for _ in range(cycles): await RisingEdge(dut.clk_i)

async def load_weights(dut, W00, W01, W10, W11):
    """
    4-cycle weight load protocol.
    Row 0 (pe00/pe01) → buf[0] via top-level weight ports.
    Row 1 (pe10/pe11) → buf[1] via pe00/pe01 weight_out chain.
    Extra cycles needed because weight_valid_o is suppressed on the
    sel-bit edge transition, causing pe10/pe11 to need the value
    re-driven twice before they successfully latch it.
    """
    await set_weights(dut, pack(W00, 0),    pack(W01, 0))     # C1: buf[0]
    await set_weights(dut, pack(W10, SEL1), pack(W11, SEL1))  # C2: buf[1], edge→wvo=0
    await set_weights(dut, pack(W10, SEL1), pack(W11, SEL1))  # C3: no edge, wvo=1 but pe10 missed
    await set_weights(dut, pack(W10, SEL1), pack(W11, SEL1))  # C4: pe10/pe11 finally latch
    await idle(dut, 1)

@cocotb.test()
async def test_reset(dut):
    await init_dut(dut)
    await RisingEdge(dut.clk_i)
    for pe_psum in [dut.pe00.psum_out, dut.pe01.psum_out,
                    dut.pe10.psum_out, dut.pe11.psum_out]:
        try: val = int(pe_psum.value)
        except ValueError: raise AssertionError(f"X/Z after reset: {pe_psum.value}")
        assert val == 0, f"psum should be 0 after reset, got {val}"
    cocotb.log.info("PASS: test_reset")

@cocotb.test()
async def test_weight_load(dut):
    """Single PE fires with W00=1 to confirm weight was loaded."""
    await init_dut(dut)
    await load_weights(dut, 1, 0, 0, 0)
    await set_acts(dut, pack(5, 0), 0, av0=1, av1=0)
    await idle(dut, 2)
    p = int(dut.pe00.psum_out.value)
    assert p == 5, f"pe00 expected 5, got {p}"
    cocotb.log.info("PASS: test_weight_load")

@cocotb.test()
async def test_single_column(dut):
    """
    W=[[2,3],[4,5]], fire col0 (x00=1, x10=6).
    pe10 fires same cycle as pe00; psum_in=0 → pe10=x10*W10=24.
    """
    await init_dut(dut)
    await load_weights(dut, 2, 3, 4, 5)
    await set_acts(dut, pack(1, 0), pack(6, 1), av0=1, av1=1)
    await idle(dut, 3)
    p10 = int(dut.pe10.psum_out.value)
    assert p10 == 6*4, f"pe10 expected {6*4}, got {p10}"
    cocotb.log.info("PASS: test_single_column")

@cocotb.test()
async def test_two_column_accumulation(dut):
    """
    W=[[2,3],[4,5]], X col0=(1,6), col1=(2,7).
    pe10 in col1: psum_in=pe00_col0=1*2=2, mac=7*4=28 → total=30.
    """
    await init_dut(dut)
    await load_weights(dut, 2, 3, 4, 5)
    W00, W10 = 2, 4
    x00, x10, x01, x11 = 1, 6, 2, 7
    await set_acts(dut, pack(x00, 0), pack(x10, 1), av0=1, av1=1)
    await set_acts(dut, pack(x01, 0), pack(x11, 1), av0=1, av1=1)
    await idle(dut, 4)
    p10 = int(dut.pe10.psum_out.value)
    expected_p10 = x00*W00 + x11*W10
    assert p10 == expected_p10, f"pe10 expected {expected_p10}, got {p10}"
    cocotb.log.info("PASS: test_two_column_accumulation")

@cocotb.test()
async def test_weight_chain_propagation(dut):
    """pe10 must get its weight via the chain from pe00, not directly."""
    await init_dut(dut)
    await load_weights(dut, 1, 1, 7, 9)
    await set_acts(dut, 0, pack(3, 1), av0=0, av1=1)
    await idle(dut, 3)
    p10 = int(dut.pe10.psum_out.value)
    assert p10 == 3*7, f"pe10 expected {3*7}, got {p10}"
    cocotb.log.info("PASS: test_weight_chain_propagation")

@cocotb.test()
async def test_fuzz(dut):
    """20 random weight/activation combinations verified against software model."""
    import random
    rng = random.Random(0xC0FFEE)
    for case in range(20):
        await init_dut(dut)
        W00=rng.randint(0,15); W10=rng.randint(0,15)
        W01=rng.randint(0,15); W11=rng.randint(0,15)
        x10=rng.randint(0,15)
        await load_weights(dut, W00, W01, W10, W11)
        await set_acts(dut, 0, pack(x10, 1), av0=0, av1=1)
        await idle(dut, 3)
        p10 = int(dut.pe10.psum_out.value)
        assert p10 == x10*W10, f"Case {case}: expected {x10*W10}, got {p10}"
    cocotb.log.info("PASS: test_fuzz (20 cases)")

# ---------------------------------------------------------------------------
# Pytest wrappers
# ---------------------------------------------------------------------------
tests = ["test_reset","test_weight_load","test_single_column",
         "test_two_column_accumulation","test_weight_chain_propagation","test_fuzz"]
ROOT = Path(__file__).resolve().parents[1]  # .../slugtpu

SOURCES = [
    (ROOT / "rtl" / "pe_test" / "sysray" / "pe.sv").resolve(),
    (ROOT / "rtl" / "pe_test" / "sysray" / "sysray.sv").resolve(),
]

@pytest.mark.parametrize("testcase", tests)
def test_sysray_each(testcase):
    try:
        run_test(parameters={}, sources=SOURCES,
                 module_name="test_sysray", hdl_toplevel="sysray", testcase=testcase)
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(f"'{testcase}' failed (exit {exc.code})")

def test_sysray_all():
    try:
        run_test(parameters={}, sources=SOURCES,
                 module_name="test_sysray", hdl_toplevel="sysray")
    except SystemExit as exc:
        if exc.code != 0:
            pytest.fail(f"cocotb tests failed (exit {exc.code})")