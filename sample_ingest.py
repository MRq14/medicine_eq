#!/usr/bin/env python3
"""
Sample ingestion script: parse, chunk, embed, and ingest a medical equipment PDF.
Usage: python sample_ingest.py <path/to/file.pdf>
"""
import sys
from pathlib import Path

from pipeline.parser import parse_pdf
from pipeline.chunker import chunk_document
from pipeline.ingestion import ingest_pdf

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sample_ingest.py <path/to/file.pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    print(f"Ingesting {pdf_path.name}...")
    chunk_count = ingest_pdf(str(pdf_path))
    print(f"✓ Ingested {chunk_count} chunks")
