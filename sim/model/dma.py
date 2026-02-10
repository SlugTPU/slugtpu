"""
TPU Memory Model - (Transaction Level with Wishbone)

Wishbone Addressing (32-bit bus, byte-addressable, little-endian):
  Address 0x100 = bytes [0x100, 0x101, 0x102, 0x103]
  Write 0xDEADBEEF to 0x100:
    0x100 <- 0xEF (byte 0, bits 7:0)
    0x101 <- 0xBE (byte 1, bits 15:8)
    0x102 <- 0xAD (byte 2, bits 23:16)
    0x103 <- 0xDE (byte 3, bits 31:24)
  
  sel=0xF: all 4 bytes, sel=0x1: byte 0 only, sel=0x5: bytes 0 and 2
"""

from collections import deque
from dataclasses import dataclass


# WISHBONE

@dataclass
class WishboneTransaction:
    """Wishbone bus transaction container."""
    addr: int
    data: int = 0
    we: bool = False      # True=write, False=read
    sel: int = 0xF        # Byte select (0xF = all 4 bytes)


class WishboneMemory:
    """Memory with Wishbone interface. 32-bit data bus, byte-addressable."""
    
    def __init__(self, size_bytes: int, name: str = "Memory"):
        self.name = name
        self.size = size_bytes
        self._mem = bytearray(size_bytes)
    
    def execute(self, txn: WishboneTransaction) -> int:
        """Execute transaction. Returns read data (0 for writes)."""
        if txn.we:
            for i in range(4):
                if txn.sel & (1 << i):
                    addr = txn.addr + i
                    if addr < self.size:
                        self._mem[addr] = (txn.data >> (i * 8)) & 0xFF
            return 0
        else:
            data = 0
            for i in range(4):
                addr = txn.addr + i
                if addr < self.size:
                    data |= self._mem[addr] << (i * 8)
            return data
    
    def read_bytes(self, addr: int, n_bytes: int) -> bytes:
        """Read n bytes via Wishbone transactions."""
        result = bytearray()
        for offset in range(0, n_bytes, 4):
            txn = WishboneTransaction(addr=addr + offset, we=False)
            word = self.execute(txn)
            for i in range(min(4, n_bytes - offset)):
                result.append((word >> (i * 8)) & 0xFF)
        return bytes(result)
    
    def write_bytes(self, addr: int, data: bytes):
        """Write bytes via Wishbone transactions."""
        for offset in range(0, len(data), 4):
            chunk = data[offset:offset + 4]
            word = 0
            sel = 0
            for i, b in enumerate(chunk):
                word |= b << (i * 8)
                sel |= 1 << i
            txn = WishboneTransaction(addr=addr + offset, data=word, we=True, sel=sel)
            self.execute(txn)


# FIFO & OUTPUT BUFFER

class FIFO:
    """8-bit FIFO for weights."""
    
    def __init__(self, name: str = "FIFO"):
        self.name = name
        self._queue: deque = deque()
    
    def push(self, val: int):
        self._queue.append(val & 0xFF)
    
    def push_bytes(self, data: bytes):
        for b in data:
            self._queue.append(b)
    
    def pop(self) -> int:
        """Returns 0 if empty."""
        return self._queue.popleft() if self._queue else 0
    
    @property
    def empty(self) -> bool:
        return len(self._queue) == 0
    
    @property
    def count(self) -> int:
        return len(self._queue)
    
    def clear(self):
        self._queue.clear()
    
    def to_list(self) -> list[int]:
        return list(self._queue)


class OutputBuffer:
    """Collects 8-bit outputs from systolic array."""
    
    def __init__(self):
        self._data: list[int] = []
    
    def push(self, high_byte: int, low_byte: int):
        self._data.append(high_byte & 0xFF)
        self._data.append(low_byte & 0xFF)
    
    def push_byte(self, val: int):
        self._data.append(val & 0xFF)
    
    def get_all(self) -> bytes:
        return bytes(self._data)
    
    def clear(self):
        self._data.clear()
    
    @property
    def count(self) -> int:
        return len(self._data)


# TPU MEMORY SYSTEM

class TPUMemory:
    """    
     LiteDRAM exposes wishbone interface
     Weights loaded from off-chip
     output_buf collects systolic array outputs
    """
    
    def __init__(self, offchip_size: int = 1024 * 1024):
        self.off_chip = WishboneMemory(offchip_size, "OffChipDRAM")
        self.weight_fifo = FIFO("WeightFIFO")
        self.output_buf = OutputBuffer()
    
    # off->on via wishbone
    
    def load_weights(self, addr: int, n_bytes: int):
        """Load weights from off-chip DRAM into weight FIFO."""
        data = self.off_chip.read_bytes(addr, n_bytes)
        self.weight_fifo.push_bytes(data)
    
    def read_activations(self, addr: int, n_bytes: int) -> bytes:
        """Read activations from off-chip (streamed directly, no FIFO)."""
        return self.off_chip.read_bytes(addr, n_bytes)
    
    #on -> off via wishbone
    
    def store_to_offchip(self, addr: int, data: bytes):
        self.off_chip.write_bytes(addr, data)
    
    def store_outputs_to_offchip(self, addr: int):
        self.off_chip.write_bytes(addr, self.output_buf.get_all())
        self.output_buf.clear()
    
    # raw wishbone access
    
    def wishbone_read(self, addr: int) -> int:
        return self.off_chip.execute(WishboneTransaction(addr=addr, we=False))
    
    def wishbone_write(self, addr: int, data: int, sel: int = 0xF):
        self.off_chip.execute(WishboneTransaction(addr=addr, data=data, we=True, sel=sel))
    
    #  Interface Systolic Array 
    
    def get_weight(self) -> int:
        """Pop next weight from FIFO (8-bit)."""
        return self.weight_fifo.pop()
    
    def push_output(self, high: int, low: int):
        """Push 16-bit result as two 8-bit values."""
        self.output_buf.push(high, low)
    
    def push_output_byte(self, val: int):
        self.output_buf.push_byte(val)
    
    def print_status(self):
        print(f"Weight FIFO: {self.weight_fifo.count} bytes")
        print(f"Output Buffer: {self.output_buf.count} bytes")


# TESTBENCH

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def check(self, condition: bool, msg: str):
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(msg)
    
    def check_equal(self, actual, expected, msg: str):
        if actual == expected:
            self.passed += 1
        else:
            self.failed += 1
            self.errors.append(f"{msg}: expected {expected}, got {actual}")
    
    def summary(self) -> str:
        status = "PASS" if self.failed == 0 else "FAIL"
        s = f"[{status}] {self.passed} passed, {self.failed} failed"
        for err in self.errors:
            s += f"\n  ERROR: {err}"
        return s


def test_wishbone_read_write():
    """Verify read returns what was written."""
    result = TestResult()
    mem = TPUMemory()
    
    test_cases = [
        (0x000, 0x00000000),
        (0x100, 0xDEADBEEF),
        (0x200, 0x12345678),
        (0x300, 0xFFFFFFFF),
    ]
    
    for addr, data in test_cases:
        mem.wishbone_write(addr, data)
        readback = mem.wishbone_read(addr)
        result.check_equal(readback, data, f"Addr 0x{addr:03X}")
    
    # Verify no address bleed
    mem.wishbone_write(0x500, 0xAAAAAAAA)
    mem.wishbone_write(0x504, 0xBBBBBBBB)
    result.check_equal(mem.wishbone_read(0x500), 0xAAAAAAAA, "No bleed 0x500")
    result.check_equal(mem.wishbone_read(0x504), 0xBBBBBBBB, "No bleed 0x504")
    
    print(f"test_wishbone_read_write: {result.summary()}")
    return result


def test_wishbone_byte_select():
    """Verify byte select only modifies selected bytes."""
    result = TestResult()
    mem = TPUMemory()
    
    mem.wishbone_write(0x100, 0x00000000, sel=0xF)
    
    # write each byte individually, verify others unchanged
    mem.wishbone_write(0x100, 0x000000AA, sel=0x1)
    result.check_equal(mem.wishbone_read(0x100), 0x000000AA, "sel=0x1")
    
    mem.wishbone_write(0x100, 0x0000BB00, sel=0x2)
    result.check_equal(mem.wishbone_read(0x100), 0x0000BBAA, "sel=0x2")
    
    mem.wishbone_write(0x100, 0x00CC0000, sel=0x4)
    result.check_equal(mem.wishbone_read(0x100), 0x00CCBBAA, "sel=0x4")
    
    mem.wishbone_write(0x100, 0xDD000000, sel=0x8)
    result.check_equal(mem.wishbone_read(0x100), 0xDDCCBBAA, "sel=0x8")
    
    # Non-contiguous: bytes 0 and 2 only
    mem.wishbone_write(0x200, 0xFFFFFFFF, sel=0xF)
    mem.wishbone_write(0x200, 0x00110022, sel=0x5)
    result.check_equal(mem.wishbone_read(0x200), 0xFF11FF22, "sel=0x5")
    
    print(f"test_wishbone_byte_select: {result.summary()}")
    return result


def test_fifo_ordering():
    """Verify weight FIFO maintains first-in-first-out order."""
    result = TestResult()
    mem = TPUMemory()
    
    test_data = bytes([10, 20, 30, 40, 50, 60, 70, 80])
    mem.off_chip.write_bytes(0x1000, test_data)
    mem.load_weights(0x1000, 8)
    
    for i, expected in enumerate(test_data):
        actual = mem.get_weight()
        result.check_equal(actual, expected, f"FIFO index {i}")
    
    result.check(mem.weight_fifo.empty, "FIFO empty after drain")
    
    print(f"test_fifo_ordering: {result.summary()}")
    return result


def test_activation_streaming():
    """Verify activations read directly from off-chip (no FIFO)."""
    result = TestResult()
    mem = TPUMemory()
    
    test_data = bytes([1, 2, 3, 4, 5, 6, 7, 8])
    mem.off_chip.write_bytes(0x2000, test_data)
    
    # Read activations directly
    acts = mem.read_activations(0x2000, 8)
    result.check_equal(list(acts), list(test_data), "Direct activation read")
    
    # Can read same data again (not consumed like FIFO)
    acts2 = mem.read_activations(0x2000, 8)
    result.check_equal(list(acts2), list(test_data), "Re-read activations")
    
    print(f"test_activation_streaming: {result.summary()}")
    return result


def test_load_various_sizes():
    """Verify non-aligned byte counts work correctly."""
    result = TestResult()
    mem = TPUMemory()
    
    for n_bytes in [1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17]:
        mem.weight_fifo.clear()
        test_data = bytes([i & 0xFF for i in range(n_bytes)])
        mem.off_chip.write_bytes(0x0000, test_data)
        mem.load_weights(0x0000, n_bytes)
        
        result.check_equal(mem.weight_fifo.count, n_bytes, f"Load {n_bytes} count")
        result.check_equal(mem.weight_fifo.to_list(), list(test_data), f"Load {n_bytes} data")
    
    print(f"test_load_various_sizes: {result.summary()}")
    return result


def test_output_buffer():
    """Verify high/low byte storage and reconstruction."""
    result = TestResult()
    mem = TPUMemory()
    
    test_values = [0x0000, 0x00FF, 0xFF00, 0xFFFF, 0x1234, 0xABCD]
    
    for val in test_values:
        mem.push_output((val >> 8) & 0xFF, val & 0xFF)
    
    output = mem.output_buf.get_all()
    result.check_equal(len(output), len(test_values) * 2, "Output byte count")
    
    for i, expected in enumerate(test_values):
        actual = (output[i * 2] << 8) | output[i * 2 + 1]
        result.check_equal(actual, expected, f"Output value {i}")
    
    print(f"test_output_buffer: {result.summary()}")
    return result


def test_store_to_offchip():
    """Verify round-trip storage to off-chip."""
    result = TestResult()
    mem = TPUMemory()
    
    outputs = [(0x00, 0x01), (0x00, 0x02), (0x12, 0x34), (0xAB, 0xCD)]
    for high, low in outputs:
        mem.push_output(high, low)
    
    mem.store_outputs_to_offchip(0x5000)
    
    result.check_equal(mem.output_buf.count, 0, "Buffer cleared")
    
    stored = mem.off_chip.read_bytes(0x5000, 8)
    expected = bytes([0x00, 0x01, 0x00, 0x02, 0x12, 0x34, 0xAB, 0xCD])
    result.check_equal(stored, expected, "Stored data")
    
    print(f"test_store_to_offchip: {result.summary()}")
    return result


def test_matmul_8x8():
    """Functional test: 8x8 matrix multiply with known values."""
    result = TestResult()
    mem = TPUMemory()
    
    # W[i][j] = i + j, A[j] = j + 1
    weights = bytes([(i + j) & 0xFF for i in range(8) for j in range(8)])
    activations = bytes([1, 2, 3, 4, 5, 6, 7, 8])
    
    mem.off_chip.write_bytes(0x0000, weights)
    mem.off_chip.write_bytes(0x1000, activations)
    
    mem.load_weights(0x0000, 64)
    result.check_equal(mem.weight_fifo.count, 64, "Weights loaded")
    
    # Expected: Output[i] = sum((i + j) * (j + 1) for j in 0..7)
    expected_outputs = []
    for i in range(8):
        acc = sum((i + j) * (j + 1) for j in range(8))
        expected_outputs.append(acc)
    
    # Compute: weights from FIFO, activations streamed directly
    computed_outputs = []
    for i in range(8):
        acc = 0
        acts = mem.read_activations(0x1000, 8)  # Stream activations each row
        
        for j in range(8):
            w = mem.get_weight()
            a = acts[j]
            acc += w * a
        
        computed_outputs.append(acc)
        mem.push_output((acc >> 8) & 0xFF, acc & 0xFF)
    
    for i in range(8):
        result.check_equal(computed_outputs[i], expected_outputs[i], f"Output[{i}]")
    
    # Verify round-trip storage
    mem.store_outputs_to_offchip(0x2000)
    stored = mem.off_chip.read_bytes(0x2000, 16)
    
    for i in range(8):
        val = (stored[i * 2] << 8) | stored[i * 2 + 1]
        result.check_equal(val, expected_outputs[i], f"Stored[{i}]")
    
    print(f"test_matmul_8x8: {result.summary()}")
    return result


def test_multiple_transactions():
    """Verify sequential load-compute-store cycles."""
    result = TestResult()
    mem = TPUMemory()
    
    for cycle in range(3):
        offset = cycle * 0x1000
        
        weights = bytes([(i + cycle * 10) & 0xFF for i in range(8)])
        acts = bytes([i + 1 for i in range(8)])
        
        mem.off_chip.write_bytes(offset, weights)
        mem.off_chip.write_bytes(offset + 0x100, acts)
        
        mem.weight_fifo.clear()
        mem.load_weights(offset, 8)
        
        streamed_acts = mem.read_activations(offset + 0x100, 8)
        
        for j in range(8):
            w = mem.get_weight()
            a = streamed_acts[j]
            res = w * a
            mem.push_output((res >> 8) & 0xFF, res & 0xFF)
        
        mem.store_outputs_to_offchip(offset + 0x200)
        
        # Verify first output
        first_out = mem.off_chip.read_bytes(offset + 0x200, 2)
        expected = weights[0] * acts[0]
        actual = (first_out[0] << 8) | first_out[1]
        result.check_equal(actual, expected, f"Cycle {cycle} first output")
    
    print(f"test_multiple_transactions: {result.summary()}")
    return result


def run_all_tests():
    print("TPU MEMORY FUNCTIONAL TESTBENCH")
    print("---" "\n")
    
    tests = [
        test_wishbone_read_write,
        test_wishbone_byte_select,
        test_fifo_ordering,
        test_activation_streaming,
        test_load_various_sizes,
        test_output_buffer,
        test_store_to_offchip,
        test_matmul_8x8,
        test_multiple_transactions,
    ]
    
    total_passed = 0
    total_failed = 0
    
    for test_fn in tests:
        r = test_fn()
        total_passed += r.passed
        total_failed += r.failed
        print()
    
    if total_failed == 0:
        print(f"ALL TESTS PASSED! {total_passed} checks")
    else:
        print(f"TESTS FAILED :c {total_passed} passed, {total_failed} failed")
    
    return total_failed == 0


if __name__ == "__main__":
    run_all_tests()