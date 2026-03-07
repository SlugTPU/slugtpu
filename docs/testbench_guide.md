# SlugTPU Testbench Guide

Testbenches live in `sim/` and are written in Python using [cocotb](https://www.cocotb.org/) with [pytest](https://pytest.org/) as the test runner. Each testbench file corresponds to one RTL module.

---

## Infrastructure Overview

| File | Role |
|---|---|
| `sim/shared.py` | Common cocotb helpers (`clock_start`, `reset_sequence`, `handshake`) |
| `sim/runner.py` | `run_test()` — builds and runs with both Icarus and Verilator |
| `sim/test_<module>.py` | Per-module testbench |

---

## Architecture: The Four Layers

Every testbench for an elastic (ready/valid) module is built from the same four layers.

```
data_generator ──> InputModel ──> DUT ──> OutputModel
                       |                      |
                  handshake_gen          handshake_gen
                       |                      |
                   ModelRunner (reference model)
                   .consume()            .produce() + assert
```

### 1. Reference Model

A pure Python model of what the DUT should compute. It uses a FIFO queue (`deque`) to pair inputs with outputs across pipeline latency.

```python
from collections import deque

class MyModel:
    def __init__(self):
        self.q = deque()

    def consume(self, dut):
        # Called on every input handshake.
        # Snapshot DUT input ports and push to queue.
        x = dut.data_i.value.to_signed()
        self.q.append(x)

    def produce(self, dut):
        # Called on every output handshake.
        # Pop from queue, compute expected, assert against DUT output.
        x = self.q.popleft()
        expected = my_python_function(x)
        got = dut.data_o.value.to_signed()
        assert got == expected, f"got {got}, expected {expected}"
```

**Key rules:**
- `consume()` is called at the **input** handshake (before the data travels through the pipeline).
- `produce()` is called at the **output** handshake (when the result is valid).
- The queue handles arbitrary pipeline depth automatically; you do not need to know the latency.
- For approximate computations (fixed-point, quantization), use a relative error tolerance instead of exact equality:
  ```python
  assert abs(got - expected) / (abs(expected) + 1e-12) < 0.10
  ```

**Why a `deque` even for a single elastic stage?**
The `deque` is not modeling a FIFO in the DUT — it is solving a timing problem in the testbench. `consume()` and `produce()` are driven by two independent coroutines watching two different handshake points. Even for a single-stage module, the testbench cannot read the input ports at the moment the output fires, because the DUT may have already latched new inputs by then. The `deque` bridges this gap: `consume()` snapshots the input values the instant they are accepted and parks them in the queue; `produce()` pops that snapshot when the corresponding output fires. The queue depth at any given moment reflects how many transactions are in flight — for a single elastic stage this is at most 1, but the pattern works identically for deeper pipelines and multi-cycle modules without any changes. If the DUT takes N cycles to produce a result, up to N snapshots can be queued simultaneously and they will be retired in order as outputs arrive.

### 2. ModelRunner

Wraps the reference model and wires its `consume`/`produce` methods to the DUT's handshake signals by spawning two persistent cocotb coroutines.

```python
class ModelRunner:
    def __init__(self, dut):
        self.dut = dut
        self.model = MyModel()

    def start(self):
        cocotb.start_soon(self.run_input())
        cocotb.start_soon(self.run_output())

    async def run_input(self):
        clk_i = self.dut.clk_i
        rst_i  = self.dut.rst_i
        while True:
            await handshake(clk_i, rst_i, self.dut.data_ready_o, self.dut.data_valid_i)
            self.model.consume(self.dut)

    async def run_output(self):
        clk_i = self.dut.clk_i
        rst_i  = self.dut.rst_i
        while True:
            await handshake(clk_i, rst_i, self.dut.data_ready_i, self.dut.data_valid_o)
            self.model.produce(self.dut)
```

`handshake(clk_i, rst_i, ready, valid)` from `shared.py` blocks until both `ready` and `valid` are high on a rising clock edge (and the DUT is not in reset).

Notice the argument order:
- **Input side**: `ready = data_ready_o` (DUT says it can accept), `valid = data_valid_i` (testbench says it is sending)
- **Output side**: `ready = data_ready_i` (testbench says it can accept), `valid = data_valid_o` (DUT says output is valid)

### 3. InputModel

Drives the DUT inputs. It iterates a **data generator** and uses a **handshake generator** to control `valid_i` on each cycle. It waits until the current transaction is accepted before advancing to the next.

```python
class InputModel:
    def __init__(self, dut, data_generator, handshake_generator):
        self.dut = dut
        self.data_generator = data_generator
        self.handshake_generator = handshake_generator

    def start(self):
        return cocotb.start_soon(self._run())

    async def _run(self):
        await FallingEdge(self.dut.rst_i)   # wait for reset to deassert

        for data in self.data_generator:
            tx = False
            self.dut.data_i.value = data    # latch data onto the bus

            while not tx:
                self.dut.data_valid_i.value = next(self.handshake_generator)
                await RisingEdge(self.dut.clk_i)
                if self.dut.data_valid_i.value and self.dut.data_ready_o.value == 1:
                    tx = True               # transaction accepted, advance

            await FallingEdge(self.dut.clk_i)  # drive outputs after falling edge
```

**Important:** Data is set on the bus **before** the `while not tx` loop and kept stable until the handshake fires. Only `valid_i` toggles each cycle.

### 4. OutputModel

Drives `ready_i` on the output side. It runs until `total_nin` transactions have been received, then its coroutine task completes — the test awaits this to know when to stop.

```python
class OutputModel:
    def __init__(self, dut, handshake_generator, total_nin):
        self.dut = dut
        self.handshake_generator = handshake_generator
        self.total_nin = total_nin
        self.nout = 0

    def start(self):
        return cocotb.start_soon(self._run())

    async def _run(self):
        await FallingEdge(self.dut.rst_i)

        while self.nout < self.total_nin:
            rx = False
            while not rx:
                self.dut.data_ready_i.value = next(self.handshake_generator)
                await RisingEdge(self.dut.clk_i)
                if self.dut.data_valid_o.value == 1:
                    self.nout += 1
                    rx = True
            await FallingEdge(self.dut.clk_i)
```

---

## Generators

Generators are plain Python generator functions. They decouple data content from flow control.

### Data generator

Yields one tuple of input values per transaction:

```python
def data_generator() -> Iterator[int]:
    for _ in range(total_nin):
        yield random.randint(-128, 127)
```

For vector inputs (parameterized width `N`):

```python
def data_generator() -> Iterator[tuple[list[int], list[int]]]:
    for _ in range(total_nin):
        data = [random.randint(-10, 10) for _ in range(N)]
        bias = [random.randint(-10, 10) for _ in range(N)]
        yield (data, bias)
```

### Handshake (flow control) generator

Returns `True` or `False` each cycle to drive a valid or ready signal.

```python
# Always accept / always drive valid — no stalls
def yes_generator():
    while True:
        yield True

# Random backpressure — 20% chance of stall each cycle
def backpressure_generator():
    while True:
        yield random.random() > 0.2

# Alternating stalls
def alternating_generator():
    while True:
        yield True
        yield False
```

---

## Writing a Cocotb Test

Each test case is an `async` function decorated with `@cocotb.test()`.

```python
@cocotb.test()
async def test_my_module_basic(dut):
    """Description of what this test covers."""
    clk_i = dut.clk_i
    rst_i  = dut.rst_i
    total_nin = 20

    def data_generator():
        for _ in range(total_nin):
            yield random.randint(-128, 127)

    def yes_generator():
        while True:
            yield True

    m  = ModelRunner(dut)
    im = InputModel(dut, data_generator(), yes_generator())
    om = OutputModel(dut, yes_generator(), total_nin)

    await clock_start(clk_i)
    await reset_sequence(clk_i, rst_i)

    m.start()
    task_im = im.start()
    task_om = om.start()

    await task_om.complete          # block until all outputs received

    # Clean up — deassert handshake signals
    await FallingEdge(clk_i)
    dut.data_ready_i.value = 0
    dut.data_valid_i.value = 0
    await FallingEdge(clk_i)
```

**Startup order always follows this sequence:**
1. `clock_start` — starts the clock coroutine
2. `reset_sequence` — holds reset high for several cycles, then releases
3. `.start()` on ModelRunner first, then InputModel, then OutputModel
4. `await task_om.complete` — tests ends when all outputs are received

---

## The Pytest Boilerplate

Every testbench file ends with the same pytest boilerplate. Copy it verbatim and fill in the three variables.

```python
tests = [
    "test_my_module_basic",
    "test_my_module_backpressure",
]

SOURCES = [
    Path("./rtl/my_module.sv").resolve(),
    Path("./rtl/utils/elastic.sv").resolve(),   # include all RTL dependencies
]

@pytest.mark.parametrize("testcase", tests)
def test_my_module_each(testcase):
    run_test(
        sources=SOURCES,
        module_name="test_my_module",   # name of this Python file (no .py)
        hdl_toplevel="my_module",       # name of the top-level SV module
        parameters={},
        testcase=testcase,
    )

def test_my_module_all():
    run_test(
        sources=SOURCES,
        module_name="test_my_module",
        hdl_toplevel="my_module",
        parameters={},
    )
```

- `test_my_module_each` runs one named testcase per pytest invocation — useful for `-k` filtering and for seeing which individual test fails.
- `test_my_module_all` runs every `@cocotb.test()` in sequence as a single pytest test — faster for CI.
- `parameters` is a dict of Verilog parameter overrides, e.g. `{"N": 4, "WIDTH": 8}`.

---

## Common Patterns

### Testing a module with RTL parameters

Read parameters from the DUT object at the top of the test — do not hardcode them:

```python
N           = dut.N.value.to_unsigned()
FIXED_SHIFT = dut.FIXED_SHIFT.value.to_unsigned()
```

Pass overrides via `run_test(parameters={"N": 4})`.

### Keeping bias/scale constant across transactions

Some tests want to vary data but keep weight parameters fixed per test run:

```python
def data_generator():
    bias  = [random.randint(-10, 10) for _ in range(N)]   # fixed once
    scale = [float_to_fixed(random.random(), FIXED_SHIFT) for _ in range(N)]
    for _ in range(total_nin):
        data = [random.randint(-10, 10) for _ in range(N)] # varies each tx
        yield (data, bias, scale)
```

### Reset test

Every testbench should include a `reset_test` as its first test case. It verifies that the DUT comes out of reset with all outputs in their idle/zero state and that `reset_sequence` completes without error.

**Key rules:**
- Do **not** zero-initialize inputs before reset. `reset_sequence` holds `rst_i` high for several cycles, which forces all internal state to its reset values regardless of what the inputs are doing.
- `await FallingEdge(dut.rst_i)` after `reset_sequence` to wait for the reset signal itself to deassert before sampling outputs.
- Only assert on outputs that are architecturally defined to be 0 (or idle) after reset — do not assert on `X`/`Z` values.

```python
@cocotb.test()
async def reset_test(dut):
    """Verify outputs are idle after reset with no inputs driven."""
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)
    await FallingEdge(dut.rst_i)
```

Add `"reset_test"` as the **first entry** in the `tests` list so it always runs first:

```python
tests = ["reset_test", "test_my_module_basic", ...]
```

### Backpressure test

Use `yes_generator` on input and `backpressure_generator` on output (or vice versa). The test structure is otherwise identical:

```python
@cocotb.test()
async def test_my_module_backpressure(dut):
    ...
    def backpressure_generator():
        while True:
            yield random.random() > 0.2

    im = InputModel(dut, data_generator(), yes_generator())
    om = OutputModel(dut, backpressure_generator(), total_nin)  # <-- backpressure here
    ...
```

---

## Full File Template

```python
from typing import Iterator
import pytest
import cocotb
from cocotb.triggers import RisingEdge, FallingEdge
from pathlib import Path
from shared import clock_start, reset_sequence, handshake
from cocotb.types import Array
from runner import run_test
import random


# ---------------------------------------------------------------------------
# Reference model
# ---------------------------------------------------------------------------

class MyModel:
    def __init__(self):
        self.q = deque()

    def consume(self, dut):
        x = dut.data_i.value.to_signed()
        self.q.append(x)

    def produce(self, dut):
        x = self.q.popleft()
        expected = x  # replace with actual computation
        got = dut.data_o.value.to_signed()
        assert got == expected, f"got {got}, expected {expected}"


# ---------------------------------------------------------------------------
# ModelRunner
# ---------------------------------------------------------------------------

class ModelRunner:
    def __init__(self, dut):
        self.dut = dut
        self.model = MyModel()

    def start(self):
        cocotb.start_soon(self.run_input())
        cocotb.start_soon(self.run_output())

    async def run_input(self):
        while True:
            await handshake(self.dut.clk_i, self.dut.rst_i,
                            self.dut.data_ready_o, self.dut.data_valid_i)
            self.model.consume(self.dut)

    async def run_output(self):
        while True:
            await handshake(self.dut.clk_i, self.dut.rst_i,
                            self.dut.data_ready_i, self.dut.data_valid_o)
            self.model.produce(self.dut)


# ---------------------------------------------------------------------------
# InputModel
# ---------------------------------------------------------------------------

class InputModel:
    def __init__(self, dut, data_generator, handshake_generator):
        self.dut = dut
        self.data_generator = data_generator
        self.handshake_generator = handshake_generator

    def start(self):
        return cocotb.start_soon(self._run())

    async def _run(self):
        await FallingEdge(self.dut.rst_i)
        for data in self.data_generator:
            tx = False
            self.dut.data_i.value = data
            while not tx:
                self.dut.data_valid_i.value = next(self.handshake_generator)
                await RisingEdge(self.dut.clk_i)
                if self.dut.data_valid_i.value and self.dut.data_ready_o.value == 1:
                    tx = True
            await FallingEdge(self.dut.clk_i)


# ---------------------------------------------------------------------------
# OutputModel
# ---------------------------------------------------------------------------

class OutputModel:
    def __init__(self, dut, handshake_generator, total_nin):
        self.dut = dut
        self.handshake_generator = handshake_generator
        self.total_nin = total_nin
        self.nout = 0

    def start(self):
        return cocotb.start_soon(self._run())

    async def _run(self):
        await FallingEdge(self.dut.rst_i)
        while self.nout < self.total_nin:
            rx = False
            while not rx:
                self.dut.data_ready_i.value = next(self.handshake_generator)
                await RisingEdge(self.dut.clk_i)
                if self.dut.data_valid_o.value == 1:
                    self.nout += 1
                    rx = True
            await FallingEdge(self.dut.clk_i)


# ---------------------------------------------------------------------------
# Cocotb tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_my_module_basic(dut):
    """No backpressure — baseline correctness."""
    total_nin = 20

    def data_generator():
        for _ in range(total_nin):
            yield random.randint(-128, 127)

    def yes_generator():
        while True:
            yield True

    m  = ModelRunner(dut)
    im = InputModel(dut, data_generator(), yes_generator())
    om = OutputModel(dut, yes_generator(), total_nin)

    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    m.start()
    task_im = im.start()
    task_om = om.start()

    await task_om.complete
    await FallingEdge(dut.clk_i)
    dut.data_ready_i.value = 0
    dut.data_valid_i.value = 0
    await FallingEdge(dut.clk_i)


@cocotb.test()
async def test_my_module_backpressure(dut):
    """Random output backpressure."""
    total_nin = 20

    def data_generator():
        for _ in range(total_nin):
            yield random.randint(-128, 127)

    def yes_generator():
        while True:
            yield True

    def backpressure_generator():
        while True:
            yield random.random() > 0.2

    m  = ModelRunner(dut)
    im = InputModel(dut, data_generator(), yes_generator())
    om = OutputModel(dut, backpressure_generator(), total_nin)

    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    m.start()
    task_im = im.start()
    task_om = om.start()

    await task_om.complete
    await FallingEdge(dut.clk_i)
    dut.data_ready_i.value = 0
    dut.data_valid_i.value = 0
    await FallingEdge(dut.clk_i)


# ---------------------------------------------------------------------------
# Pytest runner boilerplate
# ---------------------------------------------------------------------------

tests = [
    "test_my_module_basic",
    "test_my_module_backpressure",
]

SOURCES = [
    Path("./rtl/my_module.sv").resolve(),
    Path("./rtl/utils/elastic.sv").resolve(),
]

@pytest.mark.parametrize("testcase", tests)
def test_my_module_each(testcase):
    run_test(
        sources=SOURCES,
        module_name="test_my_module",
        hdl_toplevel="my_module",
        parameters={},
        testcase=testcase,
    )

def test_my_module_all():
    run_test(
        sources=SOURCES,
        module_name="test_my_module",
        hdl_toplevel="my_module",
        parameters={},
    )
```

---

## Running Tests

Add an entry to the root `Makefile`:

```makefile
test_my_module:
	python3 -m pytest sim/test_my_module.py -s
```

Then run from the project root:

```bash
make test_my_module
```

The `-s` flag passes stdout through so cocotb log output is visible in the terminal.

Waveforms are saved to `sim/sim_build/<simulator>/<module>/<testcase>/` as `.fst` files (Verilator) or `.vcd` files (Icarus).
