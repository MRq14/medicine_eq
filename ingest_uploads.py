#!/usr/bin/env python3
"""
Scan data/uploads recursively and ingest any PDFs not yet in ChromaDB.
Usage:
  python ingest_uploads.py
  python ingest_uploads.py --dry-run
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pipeline.config import UPLOADS_ROOT
from pipeline.ingestion import ingest_pdf
from retrieval.bm25_search import rebuild_bm25_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest all PDFs from data/uploads")
    parser.add_argument("--dry-run", action="store_true", help="List PDFs without ingesting")
    parser.add_argument("--force", action="store_true", help="Force re-ingest even if file hash hasn't changed")
    args = parser.parse_args()

    pdfs = [
        p for p in UPLOADS_ROOT.rglob("*")
        if p.suffix.lower() == ".pdf" and not p.name.startswith("._")
    ]

    if not pdfs:
        print("No PDFs found in data/uploads.")
        return

    print(f"Found {len(pdfs)} PDF(s):\n")
    for p in pdfs:
        print(f"  {p.relative_to(UPLOADS_ROOT)}")

    if args.dry_run:
        return

    print()
    ingested = skipped = failed = updated = 0

    for pdf in pdfs:
        try:
            result = ingest_pdf(pdf, original_filename=pdf.name, force=args.force)
            status = result.get("status")
            collection = result.get("collection_name", "?")
            if status == "ok":
                print(f"✓ {pdf.name}  →  {collection}  ({result.get('chunks_added', 0)} chunks)")
                ingested += 1
            elif status == "updated":
                print(f"↻ {pdf.name}  →  {collection}  (updated: {result.get('chunks_added', 0)} chunks)")
                updated += 1
            elif status == "skipped":
                print(f"  {pdf.name}  already ingested, skipping")
                skipped += 1
            else:
                print(f"? {pdf.name}  status={status}")
        except Exception as e:
            print(f"✗ {pdf.name}  ERROR: {e}")
            failed += 1

    print(f"\nDone — {ingested} ingested, {updated} updated, {skipped} skipped, {failed} failed.")

    if ingested > 0 or updated > 0:
        print("Rebuilding BM25 index...")
        count = rebuild_bm25_index()
        print(f"BM25 index updated ({count} chunks).")


if __name__ == "__main__":
    main()
