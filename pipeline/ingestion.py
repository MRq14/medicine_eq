from pathlib import Path

from pipeline.chunker import chunk_document
from pipeline.config import (
    get_chroma_collection,
    infer_collection_name,
    list_collection_names,
    validate_pdf_path,
)
from pipeline.embedder import embed_chunks
from pipeline.parser import parse_pdf


def _find_existing_document(doc_name: str, target_collection_name: str | None = None) -> str | None:
    collections_to_check = (
        [target_collection_name] if target_collection_name 
        else list_collection_names(include_existing=True)
    )
    for collection_name in collections_to_check:
        try:
            collection = get_chroma_collection(collection_name)
            existing = collection.get(where={"doc_name": doc_name})
            if existing.get("ids"):
                return collection_name
        except Exception:
            pass
    return None


def ingest_pdf(file_path: str | Path, brand: str | None = None, original_filename: str | None = None) -> dict:
    """
    Full pipeline: parse PDF → chunk → embed → store in ChromaDB.
    Returns dict with status, chunks_added, and metadata.
    original_filename: the real filename (needed when file_path is a temp path).
    """
    file_path = validate_pdf_path(file_path)

    # Check for duplicates BEFORE expensive operations
    # Extract doc_name from path to check early (without full parsing)
    doc_name = Path(original_filename).stem if original_filename else file_path.stem
    target_collection_name = brand if brand else infer_collection_name(file_path)
    existing_collection = _find_existing_document(doc_name, target_collection_name)
    if existing_collection:
        print(
            f"⚠ Document '{doc_name}' already exists in collection "
            f"'{existing_collection}'. Skipping."
        )
        return {
            "status": "skipped",
            "doc_name": doc_name,
            "collection_name": existing_collection,
            "reason": "already_ingested",
        }

    display_name = original_filename or file_path.name
    print(f"[1/4] Parsing {display_name}...")
    parsed_doc = parse_pdf(file_path, original_filename=original_filename)
    collection = get_chroma_collection(target_collection_name)

    print(f"[2/4] Chunking {parsed_doc.metadata.doc_name}...")
    chunks = chunk_document(parsed_doc, min_chars=20)
    print(f"      Generated {len(chunks)} chunks")

    if not chunks:
        print(f"⚠ No chunks generated for {file_path.name}. Skipping ingestion.")
        return {
            "status": "skipped",
            "doc_name": parsed_doc.metadata.doc_name,
            "reason": "no_chunks",
        }

    print(f"[3/4] Embedding {len(chunks)} chunks...")
    embeddings = embed_chunks(chunks)

    print(f"[4/4] Storing in ChromaDB...")
    # Prepare documents (single pass)
    # Exclude None values from metadata for cloud compatibility
    insert_data = {
        "ids": [chunk.chunk_id for chunk in chunks],
        "documents": [chunk.text for chunk in chunks],
        "metadatas": [
            {
                **chunk.metadata.model_dump(exclude_none=True),
                "target_collection_name": target_collection_name,
                "collection_name": target_collection_name,
                "source_filename": file_path.name,
            }
            for chunk in chunks
        ],
        "embeddings": embeddings,
    }

    collection.add(**insert_data)

    print(
        f"✓ Ingested {len(chunks)} chunks for '{parsed_doc.metadata.doc_name}' "
        f"into '{target_collection_name}' (group: {target_collection_name})"
    )

    return {
        "status": "ok",
        "doc_name": parsed_doc.metadata.doc_name,
        "chunks_added": len(chunks),
        "collection_name": target_collection_name,
        "target_collection_name": target_collection_name,
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
