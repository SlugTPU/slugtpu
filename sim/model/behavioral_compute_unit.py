"""
Note: This file is almost 100% human generated (thats why it sucks)
"""

import numpy as np
import math
from test_systolic_array import run_test as run_systolic_array

class TPU_Compute_Unit:
    
    def __init__(self):
        
        weights = np.load('tflite_weights.npz')
        biases = np.load('tflite_biases.npz')
        scales = np.load('tflite_scales.npz')
        zero_points = np.load('tflite_zero_points.npz')
        multipliers = np.load('tflite_multipliers.npz')
        # print(weights)
        # print(biases)
        # print(scales)
        # print(zero_points)
        # print(multipliers)

        # for key in weights.files:
        #     print(f"{key}: {weights[key]}")

        # for key in biases.files:
        #     print(f"{key}: {biases[key]}")

        # for key in multipliers.files:
        #     print(f"{key}: {multipliers[key]}")

        # for key in scales.files:
        #     print(f"{key}: {scales[key]}")

        # for key in zero_points.files:
        #     print(f"{key}: {zero_points[key]}")
        
        self.layer1_weights = weights["layer1_weights"]
        self.layer2_weights = weights["layer2_weights"]
        self.layer1_bias = biases["layer1_bias"]
        self.layer2_bias = biases["layer2_bias"]

        self.layer1_zero_point = zero_points["layer1_output_zero_point"][0]
        self.layer2_zero_point = zero_points["layer2_output_zero_point"][0]
        self.output_zero_point = zero_points["output_zero_point"]
        self.input_zero_point = zero_points["input_zero_point"]

        self.output_scale = scales["output_scale"]
        self.input_scale = scales["input_scale"]
        self.layer2_scale = scales["layer2_output_scale"]

        self.layer1_qsf = multipliers["layer1_M_float32"]
        self.layer2_qsf = multipliers["layer2_M_float32"]

        self.layer1_bias_scale = scales["layer1_bias_scale"]
        self.layer2_bias_scale = scales["layer2_bias_scale"]
        
        self.on_chip = {}
        self.off_chip_additional = {}
        self.biases = None
        self.zp = None
        self.qsf = None
        self.fifo = []
        self.res = None

    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))

    def basic_correctness_test(self):
        # USE NETRON DON'T LISTEN TO AI
        expected_output = np.load('expected_output.npz')['arr_0']
        float_input = np.load('input_quantized.npz')['arr_0']

        test_input_quantized = float_input / self.input_scale + self.input_zero_point

        layer1_32 = np.matmul(test_input_quantized.astype(np.int32), self.layer1_weights.T.astype(np.int32)) + (self.layer1_bias.astype(np.int32))
        # print(layer1_32)
        layer1_relu = np.maximum(0, layer1_32)
        
        layer1_q = (layer1_relu - self.layer1_zero_point).astype(np.float32) * self.layer1_qsf.astype(np.float32)
        # layer1_q = layer1_relu.astype(np.float32) * self.layer1_qsf.astype(np.float32) + self.layer1_zero_point.astype(np.float32)
        print(layer1_q)

        layer1_q = layer1_q.astype(np.int8)
        self.check = layer1_q
        print(layer1_q)

        layer2_32 = (np.matmul(layer1_q.astype(np.int32), self.layer2_weights.T.astype(np.int32)) + (self.layer2_bias.astype(np.int32) ))
        layer2_q = ((layer2_32 - self.layer2_zero_point.astype(np.int32) ).astype(np.float32) * self.layer2_qsf.astype(np.float32) )
        # layer2_q = layer2_32.astype(np.float32) * self.layer2_qsf.astype(np.float32) + self.layer2_zero_point.astype(np.float32)
        # print(layer2_q)

        # This is where we stop TPU and do sigmoid on host/cpu

        output = self.sigmoid((layer2_q.astype(np.float32) + self.layer2_zero_point.astype(np.float32)) * self.layer2_scale.astype(np.float32))
        output = output / self.output_scale + self.output_zero_point
        print(np.round(output.flatten()).astype(np.int8))
        print(expected_output.astype(np.int8))

    def high_level_sim(self):
        expected_output = np.load('expected_output.npz')['arr_0']
        float_input = np.load('input_quantized.npz')['arr_0']

        test_input_quantized = float_input / self.input_scale + self.input_zero_point

        SYSTOLIC_DIM = 2
        # These are hardcoded testing values
        # First Matmul is 32x20 * 20x16 = 32x16
        #       8 output tiles, 4 down, two across
        #       K dim : ceil(20/8) = 3 loops per output tile
        # Second is 32x16 * 16x1 = 32X1
        #       4 output tiles, 2 loops, low systolic array occupancy

        layer1_kdim = self.layer1_weights.shape[1]
        layer1_mdim = test_input_quantized.shape[0]
        layer1_ndim = self.layer1_weights.shape[0]
        # m = 32, k = 20, n = 16
        C = np.zeros(shape=(layer1_mdim,layer1_ndim), dtype=np.int8)
        for m_tile in range (math.ceil(layer1_mdim/SYSTOLIC_DIM)): # 4
            for n_tile in range(math.ceil(layer1_ndim/SYSTOLIC_DIM)): # 2
                C_row = m_tile
                C_col = n_tile
                #in real systolic array, we would shift 0 as input partial sum
                accum = np.zeros(shape=(SYSTOLIC_DIM,SYSTOLIC_DIM))
                for k_tile in range (math.ceil(layer1_kdim/SYSTOLIC_DIM)): # 3

                    #Tile Weights and activations along k dim
                    weight_tile = self.layer1_weights.T[k_tile*SYSTOLIC_DIM:(k_tile+1)*SYSTOLIC_DIM, C_col*SYSTOLIC_DIM:(C_col+1)*SYSTOLIC_DIM]
                    activation_tile = test_input_quantized[C_row*SYSTOLIC_DIM:(C_row+1)*SYSTOLIC_DIM, k_tile*SYSTOLIC_DIM:(k_tile+1)*SYSTOLIC_DIM]

                    res = np.matmul(activation_tile, weight_tile)
                    accum = accum + res
                #In our pipeline, this would be shifted out one col at a time
                bias = self.layer1_bias[n_tile*SYSTOLIC_DIM:(n_tile+1)*SYSTOLIC_DIM]
                #add bias
                accum = accum + bias
                #do relu
                accum = np.maximum(0,accum)
                #quantize
                accum = (accum - self.layer1_zero_point) * self.layer1_qsf[n_tile*SYSTOLIC_DIM:(n_tile+1)*SYSTOLIC_DIM]
                accum = accum.astype(np.int8)
                #now this is int8 technically
                C[m_tile*SYSTOLIC_DIM:(m_tile+1)*SYSTOLIC_DIM, n_tile*SYSTOLIC_DIM:(n_tile+1)*SYSTOLIC_DIM] = accum

        # ISA/Architecture challenges
        # Signal whether or not to reuse partial sum
        # Shadowbuffer control 
        # Pipelined data flow - we are modeling everything like a square, but really its a rhombus


        print("="*100)
        print(C)
        print(np.allclose(self.check.astype(np.int8), C))

    # size is implicit here
    def gmem2smem(self, off_chip_logical, on_chip_addr):
        self.on_chip[on_chip_addr] = off_chip_logical
    
    def smem2gmem(self, off_chip_addr, on_chip_addr):
        self.off_chip_additional[off_chip_addr] = self.on_chip[on_chip_addr]

    def load_bias(self, bias_addr_logical):
        self.biases=bias_addr_logical

    def load_qsf(self, qsf_addr_logical):
        self.qsf = qsf_addr_logical

    def load_zp(self, zp_logical):
        self.zp = zp_logical
    
    def load_weights(self, weights):
        self.fifo.append(weights)

    def do_matmul(self, activation_addr, bool_feedback, store_addr):
        USE_SYSTOLIC = True
        A = self.on_chip[activation_addr]
        W = self.fifo.pop(0)
        accum = 0
        if self.res is not None:
            accum = self.res
        print("before accum\n", self.res)
        if USE_SYSTOLIC == False:
            self.res = np.matmul(A, W) + accum
        else:
            _, out = run_systolic_array(A, W)
            
            print("expected\n", np.matmul(A, W))
            self.res = np.array([[out["c00"], out["c01"]], [out["c10"], out["c11"]]])
            print("got\n", self.res) 
            self.res = self.res + accum

        print("after\n", self.res)
        #if this is partial output, we gotta wait for the next tile
        if bool_feedback:
            return
    
        after_bias = self.res + self.biases
        print("after bias\n", after_bias)
        relu = np.maximum(0, after_bias)
        post_zp = relu - self.zp
        print("after zp\n", post_zp)
        final = post_zp * self.qsf
        print("final\n", final)
        assert(store_addr != None)
        self.on_chip[store_addr] = final
        self.res = 0

    def sim(self):
        activations = np.array([[1,2,1,2], 
                                [3,4,1,2], 
                                [2,1,1,1], 
                                [3,3,1,1]])
        
        weights = np.array([[4,3,1,1], 
                            [2,1,1,1], 
                            [2,3,1,2], 
                            [2,3,2,1]])
        bias = np.array([1,1,1,1])
        zp = np.array([-1,-1,-1,-1])
        qsf = np.array([2,2,2,2])
        
        instructions = [

            (self.load_bias, (np.array([[1],[1]]),)),        
            (self.load_zp, (np.array([[-1],[-1]]),)), 
            (self.load_qsf, (np.array([[2],[2]]),)),   

            # Compute Out tile 1,1
            (self.gmem2smem, (np.array([[1,2],[3,4]]), 0)), # A tile 1,1
            (self.gmem2smem, (np.array([[1,2],[1,2]]), 1)), # A tile 1,2
            (self.load_weights, (np.array([[4,3],[2,1]]),)), # W tile 1,1
            (self.do_matmul, (0, True, None)),
            (self.load_weights, (np.array([[2,3],[2,3]]),)), # W tile 2,1
            (self.do_matmul, (1, False, 11)) ,

            # Compute Out tile 1,2
            # (self.gmem2smem, (np.array([[1,2],[3,4]]), 0)), # A tile 1,1
            # (self.gmem2smem, (np.array([[1,2],[1,2]]), 1)), # A tile 1,2
            (self.load_weights, (np.array([[1,1],[1,1]]),)), # W tile 1,2
            (self.do_matmul, (0, True, None)),
            (self.load_weights, (np.array([[1,2],[2,1]]),)), # W tile 2,2
            (self.do_matmul, (1, False, 12)) ,

            (self.load_bias, (np.array([[1],[1]]),)),        
            (self.load_zp, (np.array([[-1],[-1]]),)), 
            (self.load_qsf, (np.array([[2],[2]]),)), 

            # Compute Out tile 2,1
            (self.gmem2smem, (np.array([[2,1],[3,3]]), 2)), # A tile 2,1
            (self.gmem2smem, (np.array([[1,1],[1,1]]), 3)), # A tile 2,2
            (self.load_weights, (np.array([[4,3],[2,1]]),)), # W tile 1,1
            (self.do_matmul, (2, True, None)),
            (self.load_weights, (np.array([[2,3],[2,3]]),)), # W tile 2,1
            (self.do_matmul, (3, False, 21)) ,
          
            # Compute Out tile 2,2
            # (self.gmem2smem, (np.array([[2,1],[3,3]]), 2)), # A tile 2,1
            # (self.gmem2smem, (np.array([[1,1],[1,1]]), 3)), # A tile 2,2
            (self.load_weights, (np.array([[1,1],[1,1]]),)), # W tile 1,2
            (self.do_matmul, (2, True, None)),
            (self.load_weights, (np.array([[1,2],[2,1]]),)), # W tile 2,2
            (self.do_matmul, (3, False, 22))  ,               
        ]

        for (func, args) in instructions:
            func(*args)

        print(self.on_chip)

        # print("Expected Output")

        res = (np.matmul(activations, weights) + bias)
        relu = np.maximum(0, res)
        
        final = (relu - zp) * qsf
        
        tile_11 = self.on_chip[11]
        tile_12 = self.on_chip[12]
        tile_21 = self.on_chip[21]
        tile_22 = self.on_chip[22]
        assert(np.allclose(tile_11, final[0:2, 0:2]))
        assert(np.allclose(tile_12, final[0:2, 2:4]))
        assert(np.allclose(tile_21, final[2:4, 0:2]))
        assert(np.allclose(tile_22, final[2:4, 2:4]))

        print("\n\n\n\nSimulation Matches Expected")
        print("Simulation Passed!")


t = TPU_Compute_Unit()
#t.sim()
t.basic_correctness_test()