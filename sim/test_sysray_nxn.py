import random
import cocotb
from cocotb.triggers import FallingEdge
from pathlib import Path
import pytest
from shared import clock_start, reset_sequence
from runner import run_test


def vec_mat_mul_ref(acts, weights):
    """C[j] = sum_i acts[i] * weights[i][j]  (vector @ matrix, column outputs)"""
    N = len(acts)
    return [sum(acts[i] * weights[i][j] for i in range(N)) for j in range(N)]


def mat_mat_mul_ref(act_matrix, weights):
    """Compute act_matrix @ weights row-by-row; returns an M×N output matrix."""
    return [vec_mat_mul_ref(act_row, weights) for act_row in act_matrix]


# Note: the following 2 helper functions independently drive weights and activations with diagonal pipelining, 
#       however for testing shadow buffering, they have limited usecases as they also drive the valid signals
#       well. For double buffering, use the load_two_banks and stream_two_matrices functions instead, 
#       which drive both the data and valid signals in a coordinated way.

async def load_weights(dut, N, weights, sel=0):
    """
    Load weights into the systolic array with a diagonal column stagger.
    """
    for cycle in range(2 * N - 1):
        await FallingEdge(dut.clk_i)
        for col in range(N):
            row_idx = cycle - col          # position in the bottom-to-top sweep
            if 0 <= row_idx < N:
                row = N - 1 - row_idx      # row_idx=0 → bottom row (N-1)
                dut.weight_sel_n_i[col].value   = sel
                dut.weight_n_i[col].value       = weights[row][col]
                dut.weight_valid_n_i[col].value = 1
            else:
                dut.weight_n_i[col].value       = 0
                dut.weight_valid_n_i[col].value = 0

    # Deassert weight_valid one cycle after the last column finishes
    await FallingEdge(dut.clk_i)
    for col in range(N):
        dut.weight_n_i[col].value       = 0
        dut.weight_valid_n_i[col].value = 0


async def stream_activation_matrix(dut, N, act_matrix, sel=0):
    """
    Stream an N×N activation matrix through the systolic array with diagonal pipelining.

    Returns an N×N list of output rows.
    """
    results = [[None] * N for _ in range(N)]

    for cycle in range(N + 2 * N - 1):
        await FallingEdge(dut.clk_i)

        # Drive: row i carries vector m = cycle - i when in range
        for i in range(N):
            m = cycle - i
            dut.act_sel_n_i[i].value = sel
            if 0 <= m < N:
                dut.act_n_i[i].value       = act_matrix[m][i]
                dut.act_valid_n_i[i].value = 1
            else:
                dut.act_n_i[i].value       = 0
                dut.act_valid_n_i[i].value = 0

        # Sample: col j of vector m fires at FallingEdge m + N + j → m = cycle - N - j
        for j in range(N):
            if dut.psum_out_valid_n_o[j].value == 1:
                m = cycle - N - j
                if 0 <= m < N:
                    results[m][j] = dut.psum_out_n_o[j].value.to_signed()

    for r in range(N):
        for j in range(N):
            assert results[r][j] is not None, f"row {r}, col {j}: output not captured"
    for m, row_out in enumerate(results):
        cocotb.log.info(f"  → output row {m}: {row_out}")
    return results

async def load_weight_banks(dut, N, weight_banks):                                                                                                          
    K = len(weight_banks)  # number of weight banks to load

    # bank0: cycles 0..2N-2, bank1: N..3N-2, bank2: 2N..4N-2
    for cycle in range((K+1)*N - 1):          
        await FallingEdge(dut.clk_i)                                                                                                                           
        for col in range(N):                                                                                                                                   
            # stripped cycle index to retrieve column's loading pattern 
            # (i.e. bank0 col0 loads at t=0, bank0 col1 loads at t=1, ..., bank0 colN-1 loads at t=N-1, ..., bank_n col0 loads at t=kN)
            t = cycle - col
            k = t // N      # bank index
            bk_idx = t % N  # bank k's row index

            if 0 <= t < K*N:                                                                                                                              
                dut.weight_sel_n_i[col].value   = k % 2
                dut.weight_n_i[col].value       = weight_banks[k][N-1-(bk_idx)][col]                                                                                    
                dut.weight_valid_n_i[col].value = 1                                                                                                            
            else:                                                                                                                                            
                dut.weight_n_i[col].value       = 0                                                                                                            
                dut.weight_valid_n_i[col].value = 0

    await FallingEdge(dut.clk_i)
    dut.weight_valid_n_i[N-1].value = 0

async def stream_two_activations(dut, N, mat0, mat1):                                                                                             
    results0 = [[None]*N for _ in range(N)]                                                                                                                    
    results1 = [[None]*N for _ in range(N)]                                                                                                                    
                                                                                                                                                                
    for cycle in range(2*N + 2*N - 1):                                                                                                                         
        await FallingEdge(dut.clk_i)                                                                                                                           
        for i in range(N):                                                                                                                                     
            m = cycle - i
            if 0 <= m < N:                                                                                                                                     
                dut.act_sel_n_i[i].value   = 0                                                                                                              
                dut.act_n_i[i].value       = mat0[m][i]                                                                                                        
                dut.act_valid_n_i[i].value = 1                                                                                                                 
            elif N <= m < 2*N:                                                                                                                                 
                dut.act_sel_n_i[i].value   = 1                                                                                                              
                dut.act_n_i[i].value       = mat1[m-N][i]                                                                                                      
                dut.act_valid_n_i[i].value = 1                                                                                                                 
            else:                                                                                                                                              
                dut.act_n_i[i].value       = 0                                                                                                                 
                dut.act_valid_n_i[i].value = 0                                                                                                                 
                
        for j in range(N):                                                                                                                                     
            if dut.psum_out_valid_n_o[j].value == 1:
                m = cycle - N - j                                                                                                                              
                if 0 <= m < N:                                                                                                                                 
                    results0[m][j] = dut.psum_out_n_o[j].value.to_signed()
                elif N <= m < 2*N:                                                                                                                             
                    results1[m-N][j] = dut.psum_out_n_o[j].value.to_signed()

    return results0, results1 


@cocotb.test()
async def reset_test(dut):
    """Verify that all psum outputs are 0 after reset with no inputs driven."""
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)
    await FallingEdge(dut.rst_i)


@cocotb.test()
async def test_basic_matmul_matrix(dut):
    """
    Fixed-value matrix-matrix multiply: N×N activation matrix × N×N weights.

    Each output row is verified independently against matmul_ref.
    """
    N = dut.N.value.to_unsigned()
    # always square!
    M = N
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[m * N + i + 1 for i in range(N)] for m in range(M)]
    weights    = [[(i + 1) * (j + 1) for j in range(N)] for i in range(N)]
    expected   = mat_mat_mul_ref(act_matrix, weights)

    cocotb.log.info(f"N={N}, M={M}")
    cocotb.log.info(f"act_matrix={act_matrix}")
    cocotb.log.info(f"weights={weights}")
    cocotb.log.info(f"expected={expected}")

    cocotb.start_soon(load_weights(dut, N, weights))
    for _ in range(N):                          # wait for col 0 to finish loading
        await FallingEdge(dut.clk_i)
    results = await stream_activation_matrix(dut, N, act_matrix)

    for m, (row_got, row_exp) in enumerate(zip(results, expected)):
        for j, (got, exp) in enumerate(zip(row_got, row_exp)):
            cocotb.log.info(f"out[{m}][{j}] = {got}  (expected {exp})")
            assert got == exp, f"row {m}, col {j}: expected {exp}, got {got}"

    await FallingEdge(dut.clk_i)


@cocotb.test()
async def test_random_matmul_matrix(dut):
    """
    Random matrix-matrix multiply: M×N activation matrix × N×N weights.

    Values are capped at 7 so M * N * 7 * 7 stays well within ACC_WIDTH=32.
    """
    N = dut.N.value.to_unsigned()
    # always square!
    M = N
    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix = [[random.randint(-128, 127) for _ in range(N)] for _ in range(M)]
    weights    = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    expected   = mat_mat_mul_ref(act_matrix, weights)

    cocotb.log.info(f"N={N}, M={M}")
    cocotb.log.info(f"act_matrix={act_matrix}")
    cocotb.log.info(f"weights={weights}")
    cocotb.log.info(f"expected={expected}")

    cocotb.start_soon(load_weights(dut, N, weights))
    for _ in range(N):                          # wait for col 0 to finish loading
        await FallingEdge(dut.clk_i)
    results = await stream_activation_matrix(dut, N, act_matrix)

    for m, (row_got, row_exp) in enumerate(zip(results, expected)):
        for j, (got, exp) in enumerate(zip(row_got, row_exp)):
            cocotb.log.info(f"out[{m}][{j}] = {got}  (expected {exp})")
            assert got == exp, f"row {m}, col {j}: expected {exp}, got {got}"

    await FallingEdge(dut.clk_i)

@cocotb.test()
async def test_shadow_buffer(dut):
    N = dut.N.value.to_unsigned()

    await clock_start(dut.clk_i)
    await reset_sequence(dut.clk_i, dut.rst_i)

    act_matrix0 = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    act_matrix1 = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    weights0    = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]
    weights1    = [[random.randint(-128, 127) for _ in range(N)] for _ in range(N)]

    expected0   = mat_mat_mul_ref(act_matrix0, weights0)
    expected1  = mat_mat_mul_ref(act_matrix1, weights1)

    cocotb.log.info(f"act_matrix0={act_matrix0}")
    cocotb.log.info(f"weights0={weights0}")
    cocotb.log.info(f"expected0={expected0}")

    cocotb.log.info(f"act_matrix1={act_matrix1}")
    cocotb.log.info(f"weights1={weights1}")
    cocotb.log.info(f"expected1={expected1}")

    cocotb.start_soon(load_weight_banks(dut, N, [weights0, weights1]))                                                                                                
    for _ in range(N):                                                                                                                                             
        await FallingEdge(dut.clk_i)           # bank0 col0 done → stream                                                                                          
    result0, result1 = await stream_two_activations(dut, N, act_matrix0, act_matrix1)    
    cocotb.log.info(f"result0={result0}, expected0={expected0}")
    cocotb.log.info(f"result1={result1}, expected1={expected1}")
    for m in range(N):
          for j in range(N):
              got0 = result0[m][j]
              exp0 = expected0[m][j]
              got1 = result1[m][j]
              exp1 = expected1[m][j]
              assert got0 == exp0, f"bank 0, row {m}, col {j}: expected {exp0}, got {got0}"
              assert got1 == exp1, f"bank 1, row {m}, col {j}: expected {exp1}, got {got1}"

    await FallingEdge(dut.clk_i)

tests = [
    "reset_test",
    "test_basic_matmul_matrix",
    "test_random_matmul_matrix",
    "test_shadow_buffer",
]

proj_path = Path("./rtl").resolve()
SOURCES   = [proj_path / "sysray_nxn.sv", proj_path / "pe.sv"]


@pytest.mark.parametrize("testcase", tests)
def test_sysray_nxn_each(testcase):
    run_test(
        sources=SOURCES,
        module_name="test_sysray_nxn",
        hdl_toplevel="sysray_nxn",
        parameters={"N": 8},
        testcase=testcase,
    )


def test_sysray_nxn_all():
    run_test(
        sources=SOURCES,
        module_name="test_sysray_nxn",
        hdl_toplevel="sysray_nxn",
        parameters={"N": 8},
    )
