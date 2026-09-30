from rag import build_index


print("=" * 70)
print("TELECOMAI - RAG INDEX BUILDER")
print("=" * 70)

print()

index = build_index()

print(
    f"Indexed {len(index['chunks'])} chunks."
)

print()

print(
    "RAG index created successfully."
)

print("=" * 70)