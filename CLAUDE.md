# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SlugTPU is a simple neural network accelerator ASIC. The core compute engine is a systolic array of Processing Elements (PEs) that perform MAC (multiply-accumulate) operations. A scalar post-processing pipeline handles bias, ReLU, zero-point subtraction, and fixed-point quantization.

## Setup

Requires OSS CAD Suite (2026-01-27 build) sourced into the environment:
```
source $OSS_CAD_INSTALL/oss_cad_suite/environment
```

On ARM Mac, CocoTB may need to be recompiled:
```
python3 -m pip install --force-reinstall --no-binary cocotb cocotb
```

**Always run make from the repo root** — the Makefile uses relative paths.

## Commands

```bash
# Run a specific test
make test_fifo
make test_sysray_2x2
make test_scalar_pipe
# (see Makefile for full list)

# Run a specific pytest test case directly
python3 -m pytest sim/test_sysray_2x2.py -s -k test_basic_flow

# Lint all RTL
make lint   # uses verilator --lint-only -Wall --sv

# View waveforms (auto-generated in sim_build/ after make)
gtkwave sim_build/icarus/test_fifo/fifo_simple_test/*/fifo.fst

# Clean build artifacts
make clean
```

## Architecture

### RTL (`rtl/`)
- **`pe.sv`** — Processing Element. Performs 8-bit MAC, double-buffers weights using a select bit (MSB of weight/act data). The top bit is a "select" bit for double-buffering, not data.
- **`sysray_nxn.sv`** — Parameterized N×N systolic array; instantiates `pe` in a 2D grid with weight flowing top-down and activations flowing left-right.
- **`sysray_2x2.sv`** — Fixed 2×2 systolic array (used for testing).
- **`scalar_units/scalar_pipe.sv`** — Post-processing pipeline: bias add → ReLU → zero-point subtract → fixed-point scale → int8 quantize. Uses valid/ready elastic handshaking between stages.
- **`scalar_units/`** — Individual pipeline stages: `add_n.sv`, `relu_n.sv`, `scale_n.sv`, `scalar_stage.sv`.
- **`utils/elastic.sv`** — Reusable elastic (skid-buffer) register implementing valid/ready handshake.
- **`sram/`** — SRAM controller, read/write transaction modules, activation SRAM.
- **`lib/sram/`** — GF180MCU SRAM hard macro black boxes.

### Simulation (`sim/`)
- Tests use **CocoTB** + **pytest**. Each `test_*.py` file targets one RTL module.
- **`runner.py`** — Central test runner; runs tests against both `icarus` and `verilator` by default. Build outputs go to `sim_build/<sim>/<module>/<testcase>/`.
- **`shared.py`** — Shared helpers: `clock_start`, `reset_sequence`, `handshake` (blocks until valid+ready), `random_binary_driver`.
- **`model/`** — Python behavioral models of the systolic array and PE for golden reference.

### Naming Conventions
- Ports follow LowRISC style: `_i` suffix for inputs, `_o` for outputs, `_n` for active-low (also used for array indexing in the systolic array).
- Active-high synchronous reset (`rst_i`).
- Parameterized widths: `DATA_WIDTH=8`, `ACC_WIDTH=32`.

### Key Design Detail: PE Double-Buffering
The PE uses the MSB of weight/activation data as a "select" bit to ping-pong between two weight buffers. An edge detector on `weight_sel` gates the `weight_valid_o` signal. This allows loading the next set of weights while the current inference is running.

## Writing Testbenches

The full template and guide is in `docs/testbench_guide.md`. Summary below.

### Four-Layer Pattern (for elastic valid/ready modules)

Every testbench for a valid/ready module uses the same structure:

```
data_generator → InputModel → DUT → OutputModel
                     |                   |
               ModelRunner.consume()  ModelRunner.produce() + assert
```

**Reference Model** — pure Python, uses a `deque` to pair inputs with outputs across pipeline latency. `consume()` is called on each input handshake; `produce()` on each output handshake. The `deque` is necessary even for single-stage modules because the two coroutines are independent and the DUT may have latched new inputs by the time the output fires.

**ModelRunner** — spawns two persistent coroutines that call `consume`/`produce` on every handshake. Uses `handshake(clk_i, rst_i, ready, valid)` from `shared.py`.

**InputModel** — drives DUT inputs. Iterates the data generator; keeps data stable on the bus and only toggles `valid_i` via the handshake generator until the transaction is accepted.

**OutputModel** — drives `ready_i`. Runs until `total_nin` output transactions are received; the test `await`s its task to know when to stop.

### Startup Order (always follow this sequence)
1. `await clock_start(dut.clk_i)`
2. `await reset_sequence(dut.clk_i, dut.rst_i)`
3. `m.start()` → `task_im = im.start()` → `task_om = om.start()`
4. `await task_om.complete`

### Handshake Generators

```python
def yes_generator():          # no stalls
    while True: yield True

def backpressure_generator(): # ~20% stall
    while True: yield random.random() > 0.2

def alternating_generator():  # on/off
    while True:
        yield True
        yield False
```

### Pytest Boilerplate

Every test file ends with:

```python
tests = ["test_foo_basic", "test_foo_backpressure"]

SOURCES = [Path("./rtl/my_module.sv").resolve(), ...]

@pytest.mark.parametrize("testcase", tests)
def test_foo_each(testcase):
    run_test(sources=SOURCES, module_name="test_foo",
             hdl_toplevel="my_module", parameters={}, testcase=testcase)

def test_foo_all():
    run_test(sources=SOURCES, module_name="test_foo",
             hdl_toplevel="my_module", parameters={})
```

- Read RTL parameters from the DUT object, don't hardcode: `N = dut.N.value.to_unsigned()`
- Pass parameter overrides via `run_test(parameters={"N": 4})`
- For approximate results (fixed-point, quantization): `assert abs(got - expected) / (abs(expected) + 1e-12) < 0.10`
- Add a `make test_<module>` target to the Makefile; always run with `-s` to see cocotb log output
