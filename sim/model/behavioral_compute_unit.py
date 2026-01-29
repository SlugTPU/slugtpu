"""
Note: This file is almost 100% human generated (thats why it sucks)
"""

import numpy as np
import math

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

    def sigmoid(self, x):
        return 1 / (1 + np.exp(-x))

    def basic_correctness_test(self):
        # USE NETRON DON'T LISTEN TO AI
        expected_output = np.load('expected_output.npz')['arr_0']
        float_input = np.load('input_quantized.npz')['arr_0']

        test_input_quantized = float_input / self.input_scale + self.input_zero_point

        layer1_32 = np.matmul(test_input_quantized, self.layer1_weights.T) + (self.layer1_bias)
        # print(layer1_32)
        layer1_relu = np.maximum(0, layer1_32)
        
        layer1_q = (layer1_relu - self.layer1_zero_point) * self.layer1_qsf
        print(layer1_q)

        layer1_q = np.trunc(layer1_q)
        self.check = layer1_q
        print(layer1_q)

        layer2_32 = (np.matmul(layer1_q, self.layer2_weights.T) + (self.layer2_bias ))
        layer2_q = ((layer2_32 - self.layer2_zero_point ) * self.layer2_qsf )
        # print(layer2_q)

        # This is where we stop TPU and do sigmoid on host/cpu

        output = self.sigmoid((layer2_q + self.layer2_zero_point) * self.layer2_scale)
        output = output / self.output_scale + self.output_zero_point
        print(np.round(output.flatten()).astype(np.int8))
        print(expected_output)

    def sim(self, instuctions):
        expected_output = np.load('expected_output.npz')['arr_0']
        float_input = np.load('input_quantized.npz')['arr_0']

        test_input_quantized = float_input / self.input_scale + self.input_zero_point

        SYSTOLIC_DIM = 8
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
        # Yeah that didnt make much sense but hopefully u know what i mean


        print("="*100)
        print(C)
        print(np.allclose(self.check.astype(np.int8), C))



t = TPU_Compute_Unit()
t.basic_correctness_test()
t.sim(None)


        # expected_output = np.load('expected_output.npz')['arr_0']
        # float_input = np.load('input_quantized.npz')['arr_0']

        # test_input_quantized = float_input / self.input_scale + self.input_zero_point

        # layer1_32 = np.matmul(test_input_quantized, self.layer1_weights.T) + (self.layer1_bias)
        # # print(layer1_32)
        # layer1_relu = np.maximum(0, layer1_32)
        
        # layer1_q = (layer1_relu - self.layer1_zero_point) * self.layer1_qsf
        # self.check = layer1_q
        # print(layer1_q)

        # layer2_32 = (np.matmul(layer1_q, self.layer2_weights.T) + (self.layer2_bias ))
        # layer2_q = ((layer2_32 - self.layer2_zero_point ) * self.layer2_qsf )
        # # print(layer2_q)

        # # This is where we stop TPU and do sigmoid on host/cpu

        # output = self.sigmoid((layer2_q + self.layer2_zero_point) * self.layer2_scale)
        # output = output / self.output_scale + self.output_zero_point
        # print(np.round(output.flatten()).astype(np.int8))
        # print(expected_output)