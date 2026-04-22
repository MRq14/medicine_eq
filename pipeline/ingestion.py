from pathlib import Path

from pipeline.chunker import chunk_document
from pipeline.config import (
    get_chroma_collection,
    infer_doc_group,
    list_collection_names,
    resolve_collection_name_for_file,
    validate_pdf_path,
)
from pipeline.embedder import embed_chunks
from pipeline.parser import parse_pdf


def _find_existing_document(doc_name: str) -> str | None:
    for collection_name in list_collection_names(include_legacy=True, include_existing=True):
        collection = get_chroma_collection(collection_name)
        existing = collection.get(where={"doc_name": doc_name})
        if existing.get("ids"):
            return collection_name
    return None


def ingest_pdf(file_path: str | Path) -> dict:
    """
    Full pipeline: parse PDF → chunk → embed → store in ChromaDB.
    Returns dict with status, chunks_added, and metadata.
    """
    file_path = validate_pdf_path(file_path)

    # Check for duplicates BEFORE expensive operations
    # Extract doc_name from path to check early (without full parsing)
    doc_name = file_path.stem
    existing_collection = _find_existing_document(doc_name)
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

    print(f"[1/4] Parsing {file_path.name}...")
    parsed_doc = parse_pdf(file_path)
    target_collection_name = resolve_collection_name_for_file(
        file_path=file_path,
        metadata=parsed_doc.metadata.model_dump(),
    )
    doc_group = infer_doc_group(file_path=file_path, metadata=parsed_doc.metadata.model_dump())
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
                "doc_group": doc_group,
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
        f"into '{target_collection_name}' (group: {doc_group})"
    )

    return {
        "status": "ok",
        "doc_name": parsed_doc.metadata.doc_name,
        "chunks_added": len(chunks),
        "collection_name": target_collection_name,
        "doc_group": doc_group,
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
