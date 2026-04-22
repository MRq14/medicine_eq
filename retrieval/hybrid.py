from __future__ import annotations

from typing import Any

from retrieval.bm25_search import bm25_search
from retrieval.vector_search import vector_search


def _rrf(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)


def hybrid_search(
    query: str,
    top_k: int = 5,
    vector_top_k: int = 10,
    bm25_top_k: int = 10,
    rrf_k: int = 60,
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    collection_name: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Hybrid retrieval via Reciprocal Rank Fusion (RRF):
      score(d) = sum(1 / (k + rank_i(d)))
    """
    if not query.strip():
        return []
    if top_k <= 0:
        return []

    vector_results = vector_search(
        query=query,
        top_k=vector_top_k,
        manufacturer=manufacturer,
        model=model,
        equipment_type=equipment_type,
        document_type=document_type,
        collection_name=collection_name,
        filters=filters,
    )
    bm25_results = bm25_search(
        query=query,
        top_k=bm25_top_k,
        manufacturer=manufacturer,
        model=model,
        equipment_type=equipment_type,
        document_type=document_type,
        collection_name=collection_name,
        filters=filters,
    )

    fused: dict[str, dict[str, Any]] = {}

    for item in vector_results:
        chunk_id = item["chunk_id"]
        item_collection_name = item.get("collection_name")
        fusion_key = f"{item_collection_name}::{chunk_id}"
        entry = fused.setdefault(
            fusion_key,
            {
                "chunk_id": chunk_id,
                "collection_name": item_collection_name,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
                "rrf_score": 0.0,
                "vector_rank": None,
                "bm25_rank": None,
                "distance": None,
                "bm25_score": None,
            },
        )
        rank = int(item["rank"])
        entry["rrf_score"] += _rrf(rank=rank, k=rrf_k)
        entry["vector_rank"] = rank
        entry["distance"] = item.get("distance")

    for item in bm25_results:
        chunk_id = item["chunk_id"]
        item_collection_name = item.get("collection_name")
        fusion_key = f"{item_collection_name}::{chunk_id}"
        entry = fused.setdefault(
            fusion_key,
            {
                "chunk_id": chunk_id,
                "collection_name": item_collection_name,
                "text": item.get("text", ""),
                "metadata": item.get("metadata", {}),
                "rrf_score": 0.0,
                "vector_rank": None,
                "bm25_rank": None,
                "distance": None,
                "bm25_score": None,
            },
        )
        rank = int(item["rank"])
        entry["rrf_score"] += _rrf(rank=rank, k=rrf_k)
        entry["bm25_rank"] = rank
        entry["bm25_score"] = item.get("bm25_score")

    ranked = sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)
    return ranked[:top_k]


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m retrieval.hybrid \"query text\"")
        sys.exit(1)

    output = hybrid_search(sys.argv[1])
    print(json.dumps(output, indent=2, ensure_ascii=False))
