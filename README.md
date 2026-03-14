# SlugTPU 

**A Quantized Neural Network Accelerator ASIC**

SlugTPU is an open source tensor processing unit that is designed to accelerate quantized neural network inference. We feature a parameterizable N x N systolic array with a full scalar post processing pipleline, on-chip SRAM, SPI host communication, and off-chip DRAM support via LiteDRAM. The design runs INT8 matrix multiplications with 32 bit accumulation, with hardware quantization to convert outputs back into INT8 for layer chaining.

This ASIC currently targets the GF180MCU process node.

> Part of the UC Santa Cruz CSE 127A/B Capstone Course
---

## Architecture

Our datapath can be organized into three major sections: the **compute core**, the **memory hierarchy**, and the **host interface**.

### Compute Core

The compute core performs tiled matrix multiplication that are followed by per element post-processing.

**Systolic Array**: A parameterizable N x N grid of processing elements (our current default is 8 x 8, which provides 64 MACs per cycle). Activations flow from left to right and partial sums accumulate from top to bottom. Weights are loaded top-down through a chain of shift registers Each PE performs a signed 8-bit multiply-accumulate into a 32 bit accumulator. 

The weight registers are designed to be double buffered, which allows the next layer's weights to be loaded while the current inference is still running, eliminating dead time between layers.

**Scalar Post Processing Pipeline**: A elastic pipeline that processes the systolic array's 32 bit output column by column in 4 stages:

1. **Bias Add**: Adds a 32 bit bias term per output channel
2. **ReLU**: Clamps negative values to zero
3. **Subtract Zero-Point**: Adjusts for quantization offset
4. **Fixed Point Scale + Quantize**: Multiplies by a 32 bit fixed point scale factor, rounds, and saturates to INT8

All stages use valid/ready elastic handshaking for backpressure safe pipelining.

### Memory Hierarchy

**On-Chip SRAM**: Eight SRAM blocks that store activations and intermediate results. The SRAM controller supports simultaneous read and write through an AXI-Lite interface with separate read/write channels. Address decoding uses the bottom 2 bits for bank selection and the upper bits for the intra bank address.

**Off-Chip DRAM**: Full model weights and potentially activation tensors will live in external DRAM. The design will interface with DRAM through a LiteDRAM controller exposing a Wishbone B4 port.

### Host Interface

Our host interfaces with the TPU via SPI. The host loads model data and instructions into DRAM using SPIBone as a bridge, and then sends a issues a flag to `wb_mux_2to1.sv` to give access to the TPU to begin execution.

---

## ISA

SlugTPU uses a CISC-style instruction set where each instruction maps to a high-level data movement or compute operation. Instructions are fetched from DRAM and decoded by the control unit.

| Instruction | Description |
|---|---|
| `Gmem2Smem` | DRAM to SRAM transfer |
| `Smem2Gmem` | SRAM to DRAM transfer |
| `Load_bias/zp/scale` | Load scalar parameters |
| `Load_weights` | Shift weights into systolic array |
| `Matmul` | Read activations, performs tiled matmul |
| `do_relu` | Activation function |
| `to_host_spi` | Send results to host |
| `exit` | Stop execution, return to IDLE |

---

## Verification

All RTL modules are verified with cocotb testbenches driven by pytest. The verification framework follows a producer–consumer model with Python reference models.

**The test framework currently covers:**
- Processing element (PE): MAC correctness, double buffer bank switching
- Systolic array (2 x 2 and N x N): full matrix multiply against NumPy reference
- Scalar pipeline: bias, ReLU, zero-point subtraction, fixed point quantization
- SRAM controller: read/write transactions, bank addressing
- SPI slave: host communication protocol
- FIFO: fill/drain, backpressure, boundary conditions
- Data loader: streaming activation/weight data into compute units
- Triangle shifter: input staggering for systolic array feeding

---

## Getting Started

### Prerequisites

- [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build/releases)
- Python 3 with `pytest` and `cocotb`

### Setup

```bash
source $YOUR_OSS_CAD_INSTALL/oss_cad_suite/environment

pip3 install -U pytest cocotb

# On ARM Mac, you may need to recompile cocotb from source:
python3 -m pip install --force-reinstall --no-binary cocotb cocotb
```

### Running Tests

All commands must be run from the repository root (the Makefile uses relative paths).

```bash
# Single module test
make test_sysray_nxn
make test_scalar_pipe
make test_fifo

# Run a specific test case
python3 -m pytest sim/test_sysray_nxn.py -s -k test_basic_flow

# View waveforms after a test run
gtkwave sim_build/icarus/test_fifo/fifo_simple_test/*/fifo.fst

# Clean build artifacts
make clean
```

### Available Test Targets:


| Target | Module Under Test |
|---|---|
| `test_sysray_nxn` | N x N systolic array |
| `test_sysray_2x2` | 2 x 2 systolic array |
| `test_pe_col` | PE column |
| `test_scalar_pipe` | Test scalar units |
| `test_scalar_stage` | Test scalar units, including loading |
| `test_add_n` | Vectorized bias adder |
| `test_relu_n` | Vectorized ReLU |
| `test_scale_n` | Vectorized fixed point scale |
| `test_quantizer_mul` | Fixed point quantized multiplier |
| `test_fifo` | FIFO |
| `test_spi` | SPI slave |
| `test_sram` | SRAM controller |
| `test_activation_sram` | Activation SRAM |
| `test_read_transaction` | SRAM read transaction |
| `test_write_transaction` | SRAM write transaction |
| `test_tri` | Triangle shifter |
| `test_load` | Data loader |
| `test_bias` | Bias adder |
---

## Open Source Frameworks/Cores Used

[**SPIBone**](https://github.com/xobs/spibone): Host to LiteDRAM bridge. Helps load weights and activations to DRAM.

[**LiteDRAM**](https://github.com/enjoy-digital/litedram): A [LiteX Framework](https://github.com/enjoy-digital/litex) tool handling interface with DRAM

This project was inspired by [TinyTPU](https://github.com/tiny-tpu-v2/tiny-tpu) and Google's [TPU]([https://github.com/google-coral/coralnpu](https://arxiv.org/pdf/1704.04760))


Developed as part of the UCSC CSE 127A/B capstone course.
