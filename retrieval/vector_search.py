from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pipeline.config import get_chroma_collection
from pipeline.embedder import embed_chunks


def _make_where_filter(
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    extra_filters: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    where: dict[str, Any] = {}
    if manufacturer:
        where["manufacturer"] = manufacturer
    if model:
        where["model"] = model
    if equipment_type:
        where["equipment_type"] = equipment_type
    if document_type:
        where["document_type"] = document_type
    if extra_filters:
        where.update({k: v for k, v in extra_filters.items() if v is not None})
    return where or None


def _embed_query(query: str) -> list[float]:
    query_chunk = SimpleNamespace(text=query)
    vectors = embed_chunks([query_chunk], batch_size=1)
    if not vectors:
        raise RuntimeError("Failed to generate query embedding")
    return vectors[0]


def vector_search(
    query: str,
    top_k: int = 10,
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Dense vector search in ChromaDB.
    Returns top_k entries with chunk text, metadata and distance score.
    """
    query = query.strip()
    if not query:
        return []
    if top_k <= 0:
        return []

    where = _make_where_filter(
        manufacturer=manufacturer,
        model=model,
        equipment_type=equipment_type,
        document_type=document_type,
        extra_filters=filters,
    )

    query_embedding = _embed_query(query)
    collection = get_chroma_collection()
    raw = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    results: list[dict[str, Any]] = []
    for rank, chunk_id in enumerate(ids, start=1):
        results.append(
            {
                "chunk_id": chunk_id,
                "text": documents[rank - 1] if rank - 1 < len(documents) else "",
                "metadata": metadatas[rank - 1] if rank - 1 < len(metadatas) else {},
                "distance": distances[rank - 1] if rank - 1 < len(distances) else None,
                "rank": rank,
            }
        )
    return results


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m retrieval.vector_search \"query text\"")
        sys.exit(1)

    query_text = sys.argv[1]
    output = vector_search(query_text)
    print(json.dumps(output[:3], indent=2, ensure_ascii=False))
