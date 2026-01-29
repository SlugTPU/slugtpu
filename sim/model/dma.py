"""
Memory hierarchy and double buffering.
  OFF-CHIP (DRAM): Large, slow (80+ cycles)
  ON-CHIP (SRAM): Small, fast (1 cycle), double-buffered

Current idea:

OFF-CHIP:
- Full model weights
- Large activation tensors
    
ON-CHIP:
- Weight Buffer (double-buffered for prefetch)
- Activation Buffer (input to systolic array)
- Accumulator Buffer (output from systolic array)

"""

import numpy as np
from dataclasses import dataclass

@dataclass
class Config:
    array_size: int = 8 # 8x8 systolic array
    
    # buffer size in bytes
    weight_buffer_size: int = 2 * 1024 # 2KB per buffer (x2 for double buffering)
    activation_buffer_size: int = 2 * 1024
    accumulator_buffer_size: int = 4 * 1024 
    
    # timing (cycles)
    sram_latency: int = 1
    dram_latency: int = 80
    dma_setup_cycles: int = 10


#stats

@dataclass
class Stats:
    total_cycles: int = 0
    compute_cycles: int = 0
    stall_cycles: int = 0
    dma_transfers: int = 0
    buffer_switches: int = 0
    dram_bytes_read: int = 0
    dram_bytes_written: int = 0
    
    def efficiency(self) -> float:
        if self.total_cycles == 0:
            return 0.0
        return self.compute_cycles / self.total_cycles
    
    def print(self):
        print("\n" + "=" * 50)
        print("The Holy Mem Stats")
        print("=" * 50)
        print(f"Total cycles: {self.total_cycles}")
        print(f"  Compute: {self.compute_cycles}")
        print(f"  Stalls: {self.stall_cycles}")
        print(f"Efficiency: {self.efficiency():.1%}")
        print(f"DMA transfers: {self.dma_transfers}")
        print(f"Buffer switches: {self.buffer_switches}")
        print(f"DRAM bytes read: {self.dram_bytes_read}")
        print(f"DRAM bytes written: {self.dram_bytes_written}")
        print("=" * 50)


# DRAM

class DRAM:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._mem = {}  # sparse storage: addr -> byte
        self._current_row = -1
        self._row_size = 8192  # 8KB rows
    
    def read(self, addr: int, size: int) -> tuple[bytes, int]: #Read data. return (data, latency_cycles).
        row = addr // self._row_size
        
        if row == self._current_row:
            latency = 10 + (size // 64)
        else:
            self._current_row = row
            latency = self.cfg.dram_latency + (size // 64)
        
        data = bytearray(size)
        for i in range(size):
            data[i] = self._mem.get(addr + i, 0)
        
        return bytes(data), latency
    
    def write(self, addr: int, data: bytes) -> int: # Write data. returns latency_cycles.
        row = addr // self._row_size
        
        if row == self._current_row:
            latency = 10 + (len(data) // 64)
        else:
            self._current_row = row
            latency = self.cfg.dram_latency + (len(data) // 64)
        
        for i, b in enumerate(data):
            self._mem[addr + i] = b
        
        return latency


# DOUBLE BUFFER

class DoubleBuffer:
    """
    Double-buffered SRAM scratchpad.
    
    - Buffer A: active (systolic array reads from this)
    - Buffer B: loading (DMA writes here)
    - Switch: swap A and B
    """
    
    def __init__(self, name: str, size: int):
        self.name = name
        self.size = size
        
        self._buffers = [bytearray(size), bytearray(size)]
        self._active = 0   # active buffer index
        self._loading = 1  # loading buffer index
        
        # DMA state
        self._dma_running = False
        self._dma_cycles_left = 0
        self._dma_data = None
        self._dma_offset = 0
    
    # r/w for systolic array
    
    def read(self, offset: int, size: int) -> bytes:
        # r active buffer
        buf = self._buffers[self._active]
        return bytes(buf[offset:offset + size])
    
    def write(self, offset: int, data: bytes):
        # w active buffer
        buf = self._buffers[self._active]
        buf[offset:offset + len(data)] = data
    
    # DMA ops: This part of code was influenced by an AI model ;-; let me know if there are any inconsistencies or something off
    
    def start_dma(self, data: bytes, offset: int, cycles: int):
        """Start loading data into loading buffer (background)."""
        if self._dma_running:
            raise RuntimeError(f"{self.name}: DMA already running")
        
        self._dma_running = True
        self._dma_cycles_left = cycles
        self._dma_data = data
        self._dma_offset = offset
    
    def tick(self) -> bool:
        """Advance one cycle. Returns True if DMA just completed."""
        if not self._dma_running:
            return False
        
        self._dma_cycles_left -= 1
        
        if self._dma_cycles_left <= 0:
            # Transfer complete
            buf = self._buffers[self._loading]
            buf[self._dma_offset:self._dma_offset + len(self._dma_data)] = self._dma_data
            self._dma_running = False
            self._dma_data = None
            return True
        
        return False
    
    @property
    def dma_running(self) -> bool:
        return self._dma_running
    
    @property
    def dma_cycles_remaining(self) -> int:
        return self._dma_cycles_left if self._dma_running else 0
    
    # buffer switching
    
    def can_switch(self) -> bool:
        return not self._dma_running
    
    def switch(self):
        # swap active and loading buffers
        if self._dma_running:
            raise RuntimeError(f"{self.name}: Cannot switch during DMA")
        self._active, self._loading = self._loading, self._active


class SingleBuffer:
    #single buffer for accumulator
    
    def __init__(self, name: str, size: int):
        self.name = name
        self.size = size
        self._buf = bytearray(size)
    
    def read(self, offset: int, size: int) -> bytes:
        return bytes(self._buf[offset:offset + size])
    
    def write(self, offset: int, data: bytes):
        self._buf[offset:offset + len(data)] = data
    
    def clear(self):
        self._buf = bytearray(self.size)

class TPUMemory:
# whole thing put together. this should handle the main interface the tpu will use. will use DMRAM, double buff SRAM, and DMA    
    def __init__(self, cfg: Config = None):
        self.cfg = cfg or Config()
        
        self.dram = DRAM(self.cfg)
        self.weight_buf = DoubleBuffer("WeightBuffer", self.cfg.weight_buffer_size)
        self.activation_buf = DoubleBuffer("ActivationBuffer", self.cfg.activation_buffer_size)
        self.accumulator = SingleBuffer("Accumulator", self.cfg.accumulator_buffer_size)
        
        self._cycle = 0
        self.stats = Stats()
    
    # setup before tpu run
    
    def host_write_dram(self, addr: int, data: bytes):
        # host CPU writes data to DRAM
        latency = self.dram.write(addr, data)
        self.stats.dram_bytes_written += len(data)
        # don't count toward TPU cycles
    
    def host_read_dram(self, addr: int, size: int) -> bytes:
        # host CPU reads data from DRAM
        data, _ = self.dram.read(addr, size)
        return data
    
    # DMA operations (background transfers). Again, AI helped with a lot of this section (and other DMA related stuff). It seems fine in testing, but if there are any issues let me know!
    
    def dma_load_weights(self, dram_addr: int, size: int, buf_offset: int = 0):
        """Start DMA: DRAM -> Weight Buffer (loading side)."""
        data, latency = self.dram.read(dram_addr, size)
        total_cycles = self.cfg.dma_setup_cycles + latency
        
        self.weight_buf.start_dma(data, buf_offset, total_cycles)
        self.stats.dma_transfers += 1
        self.stats.dram_bytes_read += size
    
    def dma_load_activations(self, dram_addr: int, size: int, buf_offset: int = 0):
        """Start DMA: DRAM -> Activation Buffer (loading side)."""
        data, latency = self.dram.read(dram_addr, size)
        total_cycles = self.cfg.dma_setup_cycles + latency
        
        self.activation_buf.start_dma(data, buf_offset, total_cycles)
        self.stats.dma_transfers += 1
        self.stats.dram_bytes_read += size
    
    def dma_store_outputs(self, dram_addr: int, buf_offset: int, size: int):
        """Transfer accumulator -> DRAM (blocking)."""
        data = self.accumulator.read(buf_offset, size)
        latency = self.dram.write(dram_addr, data)
        
        self._cycle += latency
        self.stats.total_cycles += latency
        self.stats.stall_cycles += latency
        self.stats.dma_transfers += 1
        self.stats.dram_bytes_written += size
    
    # buffer access for systolic array
    
    def read_weights(self, offset: int, size: int) -> bytes:
        return self.weight_buf.read(offset, size)
    
    def read_activations(self, offset: int, size: int) -> bytes:
        return self.activation_buf.read(offset, size)
    
    def write_accumulator(self, offset: int, data: bytes):
        self.accumulator.write(offset, data)
    
    def read_accumulator(self, offset: int, size: int) -> bytes:
        return self.accumulator.read(offset, size)
    
    # timing and control
    
    def tick(self, cycles: int = 1):
        for _ in range(cycles):
            self._cycle += 1
            self.stats.total_cycles += 1
            self.weight_buf.tick()
            self.activation_buf.tick()
    
    def wait_for_weights(self) -> int:
        stalls = 0
        while self.weight_buf.dma_running:
            self.tick()
            stalls += 1
            self.stats.stall_cycles += 1
        return stalls
    
    def wait_for_activations(self) -> int:
        stalls = 0
        while self.activation_buf.dma_running:
            self.tick()
            stalls += 1
            self.stats.stall_cycles += 1
        return stalls
    
    def switch_weight_buffer(self):
        self.weight_buf.switch()
        self.stats.buffer_switches += 1
    
    def switch_activation_buffer(self):
        self.activation_buf.switch()
        self.stats.buffer_switches += 1
    
    def compute(self, cycles: int):
        for _ in range(cycles):
            self.tick()
            self.stats.compute_cycles += 1
    
    @property
    def cycle(self) -> int:
        return self._cycle
