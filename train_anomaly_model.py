from anomaly_detection import train_anomaly_model


print("=" * 70)
print("TELECOMAI - NETWORK ANOMALY MODEL")
print("=" * 70)

print()

print("Training Isolation Forest...")

train_anomaly_model()

print()

print(
    "Model saved successfully."
)

print()

print("=" * 70)
print("ANOMALY MODEL TRAINING COMPLETED")
print("=" * 70)