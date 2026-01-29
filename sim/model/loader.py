import numpy as np
import tensorflow as tf
import json

# Load the TFLite model
interpreter = tf.lite.Interpreter(model_path='quantized_model.tflite')
interpreter.allocate_tensors()

# Get tensor details
tensor_details = interpreter.get_tensor_details()

print("=" * 80)
print("TFLite Model Tensor Details")
print("=" * 80)

weights = {}
biases = {}
scales = {}
zero_points = {}
all_tensor_info = {}

# Helper function to identify layer and assign meaningful names
def identify_layer(tensor_name, index):
    name_lower = tensor_name.lower()
    
    if 'keras_tensor' in name_lower or index == 0:
        return "INPUT", "input"
    elif 'dense_1/matmul' in name_lower and 'dense_1_2' not in name_lower:
        # Detect activation type from tensor name
        if 'relu6' in name_lower:
            act_type = "ReLU6"
        elif 'relu' in name_lower:
            act_type = "ReLU"
        elif 'leaky' in name_lower:
            act_type = "LeakyReLU"
        else:
            act_type = "Unknown_Activation"
        return f"LAYER_1_Dense16_{act_type}_FUSED", "layer1_output"
    elif 'dense_1_2' in name_lower or 'dense_2' in name_lower:
        return "LAYER_2_Dense1_Output", "layer2_output"
    elif 'stateful' in name_lower and 'output' not in name_lower:
        return "OUTPUT_Sigmoid", "final_output"
    elif index == 1:
        return "LAYER_2_Dense1_Output", "layer2_bias"
    elif index == 2:
        return "LAYER_2_Dense1_Output", "layer2_weights"
    elif index == 3:
        return "LAYER_1_Dense16_Activation", "layer1_bias"
    elif index == 4:
        return "LAYER_1_Dense16_Activation", "layer1_weights"
    else:
        return "UNKNOWN", f"tensor_{index}"

for tensor in tensor_details:
    tensor_name = tensor['name']
    tensor_index = tensor['index']
    tensor_shape = tensor['shape']
    tensor_dtype = tensor['dtype']
    
    # Identify which layer this belongs to
    layer_id, param_name = identify_layer(tensor_name, tensor_index)
    
    # Get quantization parameters
    quant_params = tensor['quantization_parameters']
    scale = quant_params['scales']
    zero_point = quant_params['zero_points']
    
    print(f"\n{'='*70}")
    print(f"LAYER: {layer_id}")
    print(f"{'='*70}")
    print(f"Tensor: {tensor_name}")
    print(f"  Index: {tensor_index}")
    print(f"  Shape: {tensor_shape}")
    print(f"  Dtype: {tensor_dtype}")
    print(f"  Scale: {scale}")
    print(f"  Zero point: {zero_point}")
    
    # Store quantization info for all tensors
    all_tensor_info[param_name] = {
        'original_name': tensor_name,
        'layer': layer_id,
        'index': tensor_index,
        'shape': tensor_shape,
        'dtype': str(tensor_dtype),
        'scale': scale,
        'zero_point': zero_point
    }
    
    # Try to get tensor data (only for constant tensors like weights/biases)
    try:
        tensor_data = interpreter.get_tensor(tensor_index)
        print(f"  Type: Constant (weights/biases)")
        print(f"  Saved as: {param_name}")
        
        # Categorize tensors with descriptive names
        if 'weight' in param_name or tensor_index in [2, 4]:
            weights[param_name] = tensor_data
            scales[f"{param_name}_scale"] = scale
            zero_points[f"{param_name}_zero_point"] = zero_point
            print(f"  Data shape: {tensor_data.shape}")
            
        elif 'bias' in param_name or tensor_index in [1, 3]:
            biases[param_name] = tensor_data
            scales[f"{param_name}_scale"] = scale
            zero_points[f"{param_name}_zero_point"] = zero_point
            print(f"  Data shape: {tensor_data.shape}")
            
    except ValueError:
        # These are intermediate activation tensors
        print(f"  Type: Intermediate activation (requantization point)")
        print(f"  Saved as: {param_name}")
        scales[f"{param_name}_scale"] = scale
        zero_points[f"{param_name}_zero_point"] = zero_point

# Get input/output details
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Helper to find tensors by pattern (define once at the top)
def find_tensor_by_name_pattern(pattern):
    for t in tensor_details:
        if pattern in t['name'].lower():
            return t
    return None

# COMPUTE REQUANTIZATION MULTIPLIERS (M values) FIRST
M_multipliers = {}

# Layer 1: Dense + ReLU6
input_tensor = tensor_details[0]
layer1_output = find_tensor_by_name_pattern('dense_1/matmul')
layer1_weights = tensor_details[4]

if layer1_output:
    S_input = input_tensor['quantization_parameters']['scales'][0]
    S_weights = layer1_weights['quantization_parameters']['scales']
    S_output = layer1_output['quantization_parameters']['scales'][0]
    
    M_values = []
    M_fixed_values = []
    for S_w in S_weights:
        M = (S_input * S_w) / S_output
        M_values.append(M)
        M_fixed_values.append(int(M * (2**31)))
    
    M_multipliers['layer1_M_float32'] = np.array(M_values, dtype=np.float32)
    M_multipliers['layer1_M_fixed_q31'] = np.array(M_fixed_values, dtype=np.int32)

# Layer 2: Dense output
layer2_input = layer1_output
layer2_output = find_tensor_by_name_pattern('dense_1_2/matmul')
layer2_weights = tensor_details[2]

if layer2_input and layer2_output:
    S_input = layer2_input['quantization_parameters']['scales'][0]
    S_weights = layer2_weights['quantization_parameters']['scales']
    S_output = layer2_output['quantization_parameters']['scales'][0]
    
    M_values = []
    M_fixed_values = []
    for S_w in S_weights:
        M = (S_input * S_w) / S_output
        M_values.append(M)
        M_fixed_values.append(int(M * (2**31)))
    
    M_multipliers['layer2_M_float32'] = np.array(M_values, dtype=np.float32)
    M_multipliers['layer2_M_fixed_q31'] = np.array(M_fixed_values, dtype=np.int32)

print("\n" + "=" * 80)
print("Input/Output Quantization Parameters")
print("=" * 80)

for inp in input_details:
    print(f"\nInput: {inp['name']}")
    print(f"  Shape: {inp['shape']}")
    print(f"  Scale: {inp['quantization'][0]}")
    print(f"  Zero point: {inp['quantization'][1]}")
    scales['input_scale'] = inp['quantization'][0]
    zero_points['input_zero_point'] = inp['quantization'][1]

for out in output_details:
    print(f"\nOutput: {out['name']}")
    print(f"  Shape: {out['shape']}")
    print(f"  Scale: {out['quantization'][0]}")
    print(f"  Zero point: {out['quantization'][1]}")
    scales['output_scale'] = out['quantization'][0]
    zero_points['output_zero_point'] = out['quantization'][1]

# Save all arrays
print("\n" + "=" * 80)
print("Saving arrays to disk...")
print("=" * 80)

np.savez('tflite_weights.npz', **weights)
np.savez('tflite_biases.npz', **biases)
np.savez('tflite_scales.npz', **scales)
np.savez('tflite_zero_points.npz', **zero_points)
np.savez('tflite_multipliers.npz', **M_multipliers)

# Save complete tensor info as JSON-compatible dict
import json
with open('tflite_tensor_info.json', 'w') as f:
    # Convert numpy arrays to lists for JSON serialization
    json_info = {}
    for name, info in all_tensor_info.items():
        json_info[name] = {
            'index': int(info['index']),
            'shape': [int(x) for x in info['shape']],
            'dtype': info['dtype'],
            'scale': [float(x) for x in info['scale']],
            'zero_point': [int(x) for x in info['zero_point']]
        }
    json.dump(json_info, f, indent=2)

print("\nSaved files:")
print("  - tflite_weights.npz")
print("  - tflite_biases.npz")
print("  - tflite_scales.npz (includes activation scales for requantization)")
print("  - tflite_zero_points.npz (includes activation zero points)")
print("  - tflite_multipliers.npz (M values in float32 and Q31 fixed-point)")
print("  - tflite_tensor_info.json (complete tensor graph with all quantization params)")

print("\nMultiplier arrays saved:")
for key in M_multipliers.keys():
    print(f"  - {key}: shape {M_multipliers[key].shape}, dtype {M_multipliers[key].dtype}")

# COMPUTE AND DISPLAY REQUANTIZATION MULTIPLIERS (M values)
print("\n" + "=" * 80)
print("REQUANTIZATION MULTIPLIERS (M values)")
print("=" * 80)

# Layer 1: Dense + Activation
print("\n--- LAYER 1: Dense(20→16) + Activation ---")
input_tensor = tensor_details[0]  # Input
layer1_output = find_tensor_by_name_pattern('dense_1/matmul')
layer1_weights = tensor_details[4]  # Weights

# Detect activation type
activation_type = "Unknown"
if layer1_output:
    name = layer1_output['name'].lower()
    if 'relu6' in name:
        activation_type = "ReLU6 (fused)"
    elif 'relu' in name:
        activation_type = "ReLU (fused)"
    elif 'leaky' in name:
        activation_type = "LeakyReLU"
    
print(f"Detected activation: {activation_type}")

if layer1_output:
    S_input = input_tensor['quantization_parameters']['scales'][0]
    S_weights = layer1_weights['quantization_parameters']['scales']  # Per-channel
    S_output = layer1_output['quantization_parameters']['scales'][0]
    
    print(f"Input scale (S_in): {S_input}")
    print(f"Output scale (S_out): {S_output}")
    print(f"\nPer-channel requantization multipliers M[i] = (S_in × S_weight[i]) / S_out:")
    
    M_float = M_multipliers['layer1_M_float32']
    M_fixed = M_multipliers['layer1_M_fixed_q31']
    
    for i, S_w in enumerate(S_weights):
        print(f"  Channel {i:2d}: M = ({S_input:.8f} × {S_w:.8f}) / {S_output:.8f} = {M_float[i]:.10f}")
    
    # Also show fixed-point representation (Q31 format)
    print(f"\nFixed-point representation (Q31 format, for hardware):")
    for i in range(len(M_fixed)):
        print(f"  Channel {i:2d}: M_fixed = {M_fixed[i]} (0x{M_fixed[i]:08X})")

# Layer 2: Dense output
print("\n--- LAYER 2: Dense(16→1) Output ---")
layer2_input = layer1_output  # Output from layer 1
layer2_output = find_tensor_by_name_pattern('dense_1_2/matmul')
layer2_weights = tensor_details[2]  # Weights

if layer2_input and layer2_output:
    S_input = layer2_input['quantization_parameters']['scales'][0]
    S_weights = layer2_weights['quantization_parameters']['scales']
    S_output = layer2_output['quantization_parameters']['scales'][0]
    
    print(f"Input scale (S_in): {S_input}")
    print(f"Output scale (S_out): {S_output}")
    print(f"\nRequantization multiplier M = (S_in × S_weight) / S_out:")
    
    M_float = M_multipliers['layer2_M_float32']
    M_fixed = M_multipliers['layer2_M_fixed_q31']
    
    for i, S_w in enumerate(S_weights):
        print(f"  M = ({S_input:.8f} × {S_w:.8f}) / {S_output:.8f} = {M_float[i]:.10f}")
        print(f"  M_fixed (Q31) = {M_fixed[i]} (0x{M_fixed[i]:08X})")

# Final sigmoid output
print("\n--- OUTPUT: Sigmoid Activation ---")
sigmoid_input = layer2_output
sigmoid_output = find_tensor_by_name_pattern('stateful')

if sigmoid_input and sigmoid_output:
    S_input = sigmoid_input['quantization_parameters']['scales'][0]
    S_output = sigmoid_output['quantization_parameters']['scales'][0]
    Z_input = sigmoid_input['quantization_parameters']['zero_points'][0]
    Z_output = sigmoid_output['quantization_parameters']['zero_points'][0]
    
    print(f"Sigmoid is a lookup table operation, not a linear requantization.")
    print(f"Input: scale={S_input}, zero_point={Z_input}")
    print(f"Output: scale={S_output}, zero_point={Z_output}")
    print(f"Maps int8 input → sigmoid(dequantized) → quantized int8 output")

# Show how to load them back
print("\n" + "=" * 80)
print("Example: Loading saved arrays")
print("=" * 80)
print("""
# Load the arrays:
weights = np.load('tflite_weights.npz')
biases = np.load('tflite_biases.npz')
scales = np.load('tflite_scales.npz')
zero_points = np.load('tflite_zero_points.npz')

# Access individual arrays:
for key in weights.files:
    print(f"{key}: {weights[key].shape}")
""")