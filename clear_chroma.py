#!/usr/bin/env python3
"""
Delete ALL collections from ChromaDB Cloud.
Run this before re-ingesting from a clean state.
"""
from pipeline.config import get_chroma_client

client = get_chroma_client()

collections = client.list_collections()
names = [c.name if hasattr(c, "name") else c for c in collections]

if not names:
    print("No collections found — already clean.")
else:
    print(f"Found {len(names)} collection(s): {names}")
    for name in names:
        client.delete_collection(name)
        print(f"  ✓ Deleted: {name}")
    print("Done. ChromaDB Cloud is now empty.")
