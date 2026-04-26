from pathlib import Path
import hashlib

from pipeline.chunker import chunk_document
from pipeline.config import (
    get_chroma_collection,
    infer_collection_name,
    list_collection_names,
    validate_pdf_path,
)
from pipeline.embedder import embed_chunks
from pipeline.parser import parse_pdf


def _compute_md5(file_path: str | Path) -> str:
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _find_existing_document(doc_name: str, target_collection_name: str | None = None) -> dict[str, str] | None:
    collections_to_check = (
        [target_collection_name] if target_collection_name 
        else list_collection_names(include_existing=True)
    )
    for collection_name in collections_to_check:
        try:
            collection = get_chroma_collection(collection_name)
            existing = collection.get(where={"doc_name": doc_name}, include=["metadatas"])
            if existing.get("ids"):
                metadatas = existing.get("metadatas")
                file_hash = metadatas[0].get("file_hash") if metadatas and metadatas[0] else None
                return {"collection_name": collection_name, "file_hash": file_hash}
        except Exception:
            pass
    return None


def ingest_pdf(file_path: str | Path, brand: str | None = None, original_filename: str | None = None, force: bool = False) -> dict:
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
    
    file_hash = _compute_md5(file_path)
    existing_doc = _find_existing_document(doc_name, target_collection_name)
    
    is_update = False
    if existing_doc:
        existing_collection = existing_doc["collection_name"]
        existing_hash = existing_doc.get("file_hash")
        
        if not force and existing_hash == file_hash:
            print(
                f"⚠ Document '{doc_name}' already exists in collection "
                f"'{existing_collection}' with identical hash. Skipping."
            )
            return {
                "status": "skipped",
                "doc_name": doc_name,
                "collection_name": existing_collection,
                "reason": "already_ingested_same_hash",
            }
        else:
            reason = "hash_mismatch" if existing_hash != file_hash else "forced_update"
            print(
                f"↻ Updating '{doc_name}' in collection '{existing_collection}' ({reason}). "
                "Deleting old chunks..."
            )
            collection = get_chroma_collection(existing_collection)
            collection.delete(where={"doc_name": doc_name})
            is_update = True

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
                "file_hash": file_hash,
            }
            for chunk in chunks
        ],
        "embeddings": embeddings,
    }

    collection.add(**insert_data)

    print(
        f"✓ {'Updated' if is_update else 'Ingested'} {len(chunks)} chunks for '{parsed_doc.metadata.doc_name}' "
        f"into '{target_collection_name}' (group: {target_collection_name})"
    )

    return {
        "status": "updated" if is_update else "ok",
        "doc_name": parsed_doc.metadata.doc_name,
        "chunks_added": len(chunks),
        "collection_name": target_collection_name,
        "target_collection_name": target_collection_name,
        "metadata": parsed_doc.metadata.model_dump(),
        "file_hash": file_hash,
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
