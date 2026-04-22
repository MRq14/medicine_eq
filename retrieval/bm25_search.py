from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rank_bm25 import BM25Okapi

from pipeline.config import (
    get_chroma_collection,
    list_collection_names,
)


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


def _resolve_collection_names(
    collection_name: str | None = None,
) -> list[str]:
    if collection_name:
        return [collection_name]
    return list_collection_names(include_existing=True)


@dataclass
class _BM25State:
    bm25: BM25Okapi | None = None
    collection_names_key: tuple[str, ...] | None = None
    ids: list[str] | None = None
    docs: list[str] | None = None
    metadatas: list[dict[str, Any]] | None = None
    source_collections: list[str] | None = None


_STATE = _BM25State()


def rebuild_bm25_index(collection_names: list[str] | None = None) -> int:
    """
    Rebuild BM25 index from chunks stored in one or more ChromaDB collections.
    Returns number of indexed chunks.
    """
    if collection_names is None:
        collection_names = list_collection_names(include_existing=True)

    normalized = tuple(sorted(set(collection_names)))

    all_ids: list[str] = []
    all_docs: list[str] = []
    all_metadatas: list[dict[str, Any]] = []
    all_collections: list[str] = []

    for name in normalized:
        collection = get_chroma_collection(name)
        raw = collection.get(include=["documents", "metadatas"])

        ids = raw.get("ids") or []
        docs = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []

        for idx, chunk_id in enumerate(ids):
            text = docs[idx] if idx < len(docs) else ""
            metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
            metadata = dict(metadata)
            metadata.setdefault("collection_name", name)

            all_ids.append(chunk_id)
            all_docs.append(text)
            all_metadatas.append(metadata)
            all_collections.append(name)

    tokenized_corpus = [_tokenize(doc or "") for doc in all_docs]
    if all_docs:
        _STATE.bm25 = BM25Okapi(tokenized_corpus)
    else:
        _STATE.bm25 = None

    _STATE.collection_names_key = normalized
    _STATE.ids = all_ids
    _STATE.docs = all_docs
    _STATE.metadatas = all_metadatas
    _STATE.source_collections = all_collections
    return len(all_ids)


def bm25_search(
    query: str,
    top_k: int = 10,
    manufacturer: str | None = None,
    model: str | None = None,
    equipment_type: str | None = None,
    document_type: str | None = None,
    collection_name: str | None = None,
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

    target_collections = _resolve_collection_names(
        collection_name=collection_name,
    )
    target_key = tuple(sorted(set(target_collections)))

    if _STATE.bm25 is None or _STATE.collection_names_key != target_key:
        rebuild_bm25_index(target_collections)
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
                "collection_name": _STATE.source_collections[idx] if _STATE.source_collections else None,
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
