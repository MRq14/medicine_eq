from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from pipeline.config import get_chroma_collection


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def _make_filter(
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    extra_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    return where


def _metadata_matches(metadata: dict[str, Any], where: dict[str, Any]) -> bool:
    if not where:
        return True
    for key, value in where.items():
        if metadata.get(key) != value:
            return False
    return True


@dataclass
class _BM25State:
    bm25: BM25Okapi | None = None
    ids: list[str] | None = None
    docs: list[str] | None = None
    metadatas: list[dict[str, Any]] | None = None


_STATE = _BM25State()


def rebuild_bm25_index() -> int:
    """
    Rebuild BM25 index from all chunks stored in ChromaDB.
    Returns number of indexed chunks.
    """
    collection = get_chroma_collection()
    raw = collection.get(include=["documents", "metadatas"])

    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []

    tokenized_corpus = [_tokenize(doc or "") for doc in docs]
    if tokenized_corpus:
        _STATE.bm25 = BM25Okapi(tokenized_corpus)
    else:
        _STATE.bm25 = None

    _STATE.ids = ids
    _STATE.docs = docs
    _STATE.metadatas = [m or {} for m in metadatas]
    return len(ids)


def bm25_search(
    query: str,
    top_k: int = 10,
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Sparse BM25 search over the in-memory index sourced from ChromaDB.
    """
    query = query.strip()
    if not query:
        return []
    if top_k <= 0:
        return []

    if _STATE.bm25 is None:
        rebuild_bm25_index()
    if _STATE.bm25 is None or not _STATE.ids:
        return []

    where = _make_filter(
        manufacturer=manufacturer,
        model=model,
        equipment_type=equipment_type,
        document_type=document_type,
        extra_filters=filters,
    )

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scores = _STATE.bm25.get_scores(query_tokens)  # type: ignore[union-attr]
    ranked_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    results: list[dict[str, Any]] = []
    for idx in ranked_idx:
        metadata = _STATE.metadatas[idx] if _STATE.metadatas else {}
        if not _metadata_matches(metadata, where):
            continue
        score = float(scores[idx])
        if score <= 0:
            continue

        results.append(
            {
                "chunk_id": _STATE.ids[idx],  # type: ignore[index]
                "text": _STATE.docs[idx],  # type: ignore[index]
                "metadata": metadata,
                "bm25_score": score,
                "rank": len(results) + 1,
            }
        )
        if len(results) >= top_k:
            break

    return results


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m retrieval.bm25_search \"query text\"")
        sys.exit(1)

    indexed = rebuild_bm25_index()
    print(f"Indexed chunks: {indexed}")
    output = bm25_search(sys.argv[1])
    print(json.dumps(output[:3], indent=2, ensure_ascii=False))
