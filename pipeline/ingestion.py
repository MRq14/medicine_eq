from pathlib import Path

from pipeline.chunker import chunk_document
from pipeline.config import get_chroma_collection, validate_pdf_path
from pipeline.embedder import embed_chunks
from pipeline.parser import parse_pdf


def ingest_pdf(file_path: str | Path) -> dict:
    """
    Full pipeline: parse PDF → chunk → embed → store in ChromaDB.
    Returns dict with status, chunks_added, and metadata.
    """
    file_path = validate_pdf_path(file_path)

    # Check for duplicates BEFORE expensive operations
    collection = get_chroma_collection()
    # Extract doc_name from path to check early (without full parsing)
    doc_name = file_path.stem
    existing = collection.get(where={"doc_name": doc_name})
    if existing.get("ids"):
        print(f"⚠ Document '{doc_name}' already exists. Skipping.")
        return {
            "status": "skipped",
            "doc_name": doc_name,
            "reason": "already_ingested",
        }

    print(f"[1/4] Parsing {file_path.name}...")
    parsed_doc = parse_pdf(file_path)

    print(f"[2/4] Chunking {parsed_doc.metadata.doc_name}...")
    chunks = chunk_document(parsed_doc)
    print(f"      Generated {len(chunks)} chunks")

    print(f"[3/4] Embedding {len(chunks)} chunks...")
    embeddings = embed_chunks(chunks)

    print(f"[4/4] Storing in ChromaDB...")
    # Prepare documents (single pass)
    insert_data = {
        "ids": [chunk.chunk_id for chunk in chunks],
        "documents": [chunk.text for chunk in chunks],
        "metadatas": [chunk.metadata.model_dump() for chunk in chunks],
        "embeddings": embeddings,
    }

    collection.add(**insert_data)

    print(f"✓ Ingested {len(chunks)} chunks for '{parsed_doc.metadata.doc_name}'")

    return {
        "status": "ok",
        "doc_name": parsed_doc.metadata.doc_name,
        "chunks_added": len(chunks),
        "metadata": parsed_doc.metadata.model_dump(),
    }


if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.ingestion <path/to/file.pdf>")
        sys.exit(1)

    result = ingest_pdf(sys.argv[1])
    print("\n=== RESULT ===")
    print(json.dumps(result, indent=2))
