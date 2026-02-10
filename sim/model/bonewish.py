"""
ISA based TPU sim w/ by Wishbone mem (kinda)
Behavioral compute w/ transaction lvl mem
"""

import numpy as np
from dma import TPUMemory, WishboneMemory

try:
    from test_systolic_array import run_test as run_systolic_array
except ImportError:
    from sim.model.test_systolic_array import run_test as run_systolic_array

N = 2  # systolic array dime
TILE_BYTES_I8 = N * N
TILE_BYTES_I32 = N * N * 4


def pack(arr, dtype=np.int8):
    return arr.astype(dtype).tobytes()

def unpack(data, shape, dtype=np.int8):
    return np.frombuffer(data, dtype=dtype).reshape(shape).copy()


class TPU:

    def __init__(self, sram_size=4096):
        self.dram = TPUMemory()
        self.sram = WishboneMemory(sram_size, "SRAM")
        self.biases = None
        self.zp = None
        self.qsf = None
        self.res = None

    #  Host preload dat into DRAM before TPU runs

    def host_store(self, addr, arr, dtype=np.int8):
        self.dram.store_to_offchip(addr, pack(arr, dtype))

    def host_read(self, addr, shape, dtype=np.int8):
        n = int(np.prod(shape)) * np.dtype(dtype).itemsize
        return unpack(self.dram.read_activations(addr, n), shape, dtype)

    # ISA magic

    def gmem2smem(self, dram_addr, sram_addr, nbytes):
        self.sram.write_bytes(sram_addr, self.dram.read_activations(dram_addr, nbytes))

    def smem2gmem(self, sram_addr, dram_addr, nbytes):
        self.dram.store_to_offchip(dram_addr, self.sram.read_bytes(sram_addr, nbytes))

    def load_bias(self, dram_addr, shape):
        n = int(np.prod(shape)) * 4
        self.biases = unpack(self.dram.read_activations(dram_addr, n), shape, np.int32)

    def load_zp(self, dram_addr, shape):
        n = int(np.prod(shape)) * 4
        self.zp = unpack(self.dram.read_activations(dram_addr, n), shape, np.int32)

    def load_qsf(self, dram_addr, shape):
        n = int(np.prod(shape)) * 4
        self.qsf = unpack(self.dram.read_activations(dram_addr, n), shape, np.int32)

    def load_weights(self, dram_addr, nbytes):
        self.dram.load_weights(dram_addr, nbytes)

    def do_matmul(self, sram_addr, feedback, store_sram_addr=None):
        A = unpack(self.sram.read_bytes(sram_addr, TILE_BYTES_I8), (N, N))
        W = unpack(bytes([self.dram.get_weight() for _ in range(TILE_BYTES_I8)]), (N, N))

        accum = self.res if self.res is not None else 0
        _, out = run_systolic_array(A.tolist(), W.tolist())
        self.res = np.array([[out["c00"], out["c01"]],
                             [out["c10"], out["c11"]]]) + accum

        if feedback:
            return

        result = self.qsf * (np.maximum(0, self.res + self.biases) - self.zp)
        self.sram.write_bytes(store_sram_addr, pack(result, np.int32))
        self.res = None

    def read_result(self, sram_addr, shape=(N, N)):
        return unpack(self.sram.read_bytes(sram_addr, int(np.prod(shape)) * 4), shape, np.int32)


# Test: 4x4 tiled matmul matching behavioral_compute_unit.sim()
#(This is just a sample)
# DRAM
DRAM_ACT   = 0x000 # activation tiles, 0x10 apart
DRAM_WT    = 0x100 # weight tiles, 0x10 apart
DRAM_BIAS  = 0x200
DRAM_ZP    = 0x210
DRAM_QSF   = 0x220

# SRAM
SRAM_A0    = 0x000 # activation tile slot 0
SRAM_A1    = 0x010 # activation tile slot 1
SRAM_OUT   = 0x100 # output tiles, 0x20 apart (16 bytes each for 2x2 int32)


def test_integrated():
    tpu = TPU()

    activations = np.array([[1,2,1,2],[3,4,1,2],[2,1,1,1],[3,3,1,1]])
    weights = np.array([[4,3,1,1],[2,1,1,1],[2,3,1,2],[2,3,2,1]])
    bias = np.array([1,1,1,1])
    zp = np.array([-1,-1,-1,-1])
    qsf = np.array([2,2,2,2])
    
    #preload act. tiles to DRAM
    for mi in range(2):
        for ki in range(2):
            addr = DRAM_ACT + (mi * 2 + ki) * 0x10
            tile = activations[mi*2:(mi+1)*2, ki*2:(ki+1)*2]
            tpu.host_store(addr, tile)

    # weight tiles to DRAM, where W[k_tile][n_tile]
    for ki in range(2):
        for ni in range(2):
            addr = DRAM_WT + (ki * 2 + ni) * 0x10
            tile = weights[ki*2:(ki+1)*2, ni*2:(ni+1)*2]
            tpu.host_store(addr, tile)

    # pipeline params (same for all tiles in this case)
    bias_2x1 = np.array([[1],[1]])
    zp_2x1   = np.array([[-1],[-1]])
    qsf_2x1  = np.array([[2],[2]])
    tpu.host_store(DRAM_BIAS, bias_2x1, np.int32)
    tpu.host_store(DRAM_ZP,   zp_2x1,   np.int32)
    tpu.host_store(DRAM_QSF,  qsf_2x1,  np.int32)

    # run actual isa. C[m,n] = sum_k A[m,k] @ W[k,n] for ea. output tile

    for mi in range(2):
        tpu.load_bias(DRAM_BIAS, (2, 1))
        tpu.load_zp(DRAM_ZP, (2, 1))
        tpu.load_qsf(DRAM_QSF, (2, 1))

        tpu.gmem2smem(DRAM_ACT + (mi * 2 + 0) * 0x10, SRAM_A0, TILE_BYTES_I8)
        tpu.gmem2smem(DRAM_ACT + (mi * 2 + 1) * 0x10, SRAM_A1, TILE_BYTES_I8)

        for ni in range(2):
            out_addr = SRAM_OUT + (mi * 2 + ni) * 0x20

            # partial sum
            tpu.load_weights(DRAM_WT + (0 * 2 + ni) * 0x10, TILE_BYTES_I8)
            tpu.do_matmul(SRAM_A0, feedback=True)

            # or accumulate + post-process + store
            tpu.load_weights(DRAM_WT + (1 * 2 + ni) * 0x10, TILE_BYTES_I8)
            tpu.do_matmul(SRAM_A1, feedback=False, store_sram_addr=out_addr)

    # check w/ numpy
    ref = (np.maximum(0, activations @ weights + bias) - zp) * qsf

    for mi in range(2):
        for ni in range(2):
            out_addr = SRAM_OUT + (mi * 2 + ni) * 0x20
            got = tpu.read_result(out_addr)
            expected = ref[mi*2:(mi+1)*2, ni*2:(ni+1)*2]
            assert np.allclose(got, expected), \
                f"Tile ({mi},{ni}) mismatch:\n  expected:\n{expected}\n  got:\n{got}"

if __name__ == "__main__":
    test_integrated()