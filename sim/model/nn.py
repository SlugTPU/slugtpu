import numpy as np
from tensorflow import keras
from tensorflow.keras import layers
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import tensorflow as tf

# Generate synthetic dataset
X, y = make_classification(
    n_samples=1000,
    n_features=20,
    n_informative=15,
    n_redundant=5,
    random_state=42
)

# Split and normalize data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

scaler = StandardScaler()
X_train = scaler.fit_transform(X_train)
X_test = scaler.transform(X_test)
X_test = X_test[0:32]
y_test = y_test[0:32]

# Build 2-layer feedforward network
model = keras.Sequential([
    layers.Input(shape=(20,)),
    layers.Dense(16, activation="relu"),  # Hidden layer with small dimension
    layers.Dense(1, activation='sigmoid')  # Output layer
])

# Compile model
model.compile(
    optimizer='adam',
    loss='binary_crossentropy',
    metrics=['accuracy']
)

# Display model architecture
model.summary()

# Train model
history = model.fit(
    X_train, y_train,
    epochs=50,
    batch_size=32,
    validation_split=0.2,
    verbose=1
)

# Evaluate on test set
test_loss, test_acc = model.evaluate(X_test, y_test)


# Convert to TensorFlow Lite with INT8 quantization
def representative_dataset():
    for i in range(min(200, len(X_train))):
        yield [X_train[i:i+1].astype(np.float32)]

converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset

# Enable full integer quantization
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8

# Add experimental quantization settings for better calibration
converter._experimental_lower_tensor_list_ops = False

tflite_model = converter.convert()

# Save the quantized model
with open('quantized_model.tflite', 'wb') as f:
    f.write(tflite_model)

print(f'\nOriginal model size: ~{model.count_params() * 4 / 1024:.2f} KB (float32)')
print(f'Quantized model size: {len(tflite_model) / 1024:.2f} KB')

# Test the quantized model
interpreter = tf.lite.Interpreter(model_content=tflite_model)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Run inference on test set
correct = 0
output_vals = np.empty(32)
for i in range(len(X_test)):
    # Quantize input - FIXED
    input_scale, input_zero_point = input_details[0]['quantization']
    test_input = X_test[i:i+1].astype(np.float32)
    test_input_quantized = np.clip(
        np.round(test_input / input_scale + input_zero_point),
        -128, 127
    ).astype(np.int8)
    
    interpreter.set_tensor(input_details[0]['index'], test_input_quantized)
    interpreter.invoke()
    
    # Get quantized output (don't dequantize for expected_output)
    output_data = interpreter.get_tensor(output_details[0]['index'])
    output_vals[i] = output_data[0][0]  # Save int8 value
    
    # Dequantize for accuracy calculation
    output_scale, output_zero_point = output_details[0]['quantization']
    output_dequantized = (output_data.astype(np.float32) - output_zero_point) * output_scale
    
    prediction = 1 if output_dequantized[0][0] > 0.5 else 0
    if prediction == y_test[i]:
        correct += 1

np.savez("expected_output.npz", output_vals)
np.savez("input_quantized.npz", X_test)

print(output_vals)

quantized_acc = correct / len(X_test)
print(f'Quantized model accuracy: {quantized_acc:.4f}')
print(f'\nOriginal test accuracy: {test_acc:.4f}')
print(f'Test loss: {test_loss:.4f}')