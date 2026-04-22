#!/usr/bin/env python3
"""
Sample end-to-end script:
1) ingest one PDF into ChromaDB
2) optionally run a hybrid search query

Usage:
  python sample_ingest.py <path/to/file.pdf> --query "battery replacement"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.ingestion import ingest_pdf
from retrieval.bm25_search import rebuild_bm25_index
from retrieval.hybrid import hybrid_search


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest one PDF and optionally run a hybrid retrieval query."
    )
    parser.add_argument("pdf_path", help="Path to a PDF file")
    parser.add_argument(
        "--query",
        default=None,
        help="Optional search query to run after ingestion",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of hybrid search results (default: 5)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output",
    )
    return parser.parse_args()


def _print_human(ingest_result: dict, search_results: list[dict] | None) -> None:
    print("=== Ingestion ===")
    print(f"status: {ingest_result.get('status')}")
    print(f"doc_name: {ingest_result.get('doc_name')}")
    if "chunks_added" in ingest_result:
        print(f"chunks_added: {ingest_result.get('chunks_added')}")
    if ingest_result.get("reason"):
        print(f"reason: {ingest_result.get('reason')}")

    if search_results is None:
        return

    print("\n=== Hybrid Search ===")
    print(f"results: {len(search_results)}")
    for idx, item in enumerate(search_results, start=1):
        preview = (item.get("text") or "").replace("\n", " ")[:140]
        print(
            f"{idx}. chunk_id={item.get('chunk_id')} "
            f"rrf_score={item.get('rrf_score'):.6f} "
            f"preview={preview}"
        )


def main() -> int:
    args = parse_args()
    pdf_path = Path(args.pdf_path)

    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        return 1
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Expected .pdf file, got: {pdf_path.suffix or '<no extension>'}")
        return 1
    if args.top_k <= 0:
        print("--top-k must be > 0")
        return 1

    ingest_result = ingest_pdf(pdf_path)

    search_results: list[dict] | None = None
    if args.query:
        # Ensure BM25 view includes latest collection state before querying.
        rebuild_bm25_index()
        search_results = hybrid_search(query=args.query, top_k=args.top_k)

    if args.json:
        payload = {
            "ingest": ingest_result,
            "search_query": args.query,
            "search_results": search_results or [],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_human(ingest_result, search_results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
