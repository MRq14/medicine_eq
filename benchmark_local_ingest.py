#!/usr/bin/env python3
"""
Benchmark: extract all text-bearing PDFs from zip, ingest into local ChromaDB,
measure memory/CPU precisely with background monitor, produce a solid report.

Usage:
  python benchmark_local_ingest.py
  python benchmark_local_ingest.py --zip "archive/Новая папка.zip"
  python benchmark_local_ingest.py --dry-run
  python benchmark_local_ingest.py --limit 20
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import os

import fitz  # PyMuPDF
import psutil
import chromadb
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

ZIP_PATH        = Path("archive/Новая папка.zip")
LOCAL_DB_PATH   = Path("data/benchmark_chroma")
LOG_PATH        = Path("data/benchmark_log.csv")
REPORT_PATH     = Path("data/benchmark_report.json")
MONITOR_PATH    = Path("data/benchmark_monitor.csv")
OPENAI_MODEL    = "text-embedding-3-small"
OPENAI_DIM      = 1536
CHUNK_SIZE      = 1500
CHUNK_OVERLAP   = 150
MIN_CHARS       = 50
BATCH_SIZE      = 100   # OpenAI allows up to 2048 inputs per request
COLLECTION_NAME = "benchmark_all"
PRICE_PER_1M    = 0.02  # text-embedding-3-small USD per 1M tokens

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FileResult:
    filename: str
    folder: str
    size_mb: float
    status: str = "pending"
    pages: int = 0
    chars: int = 0
    chunks: int = 0
    parse_sec: float = 0.0
    embed_sec: float = 0.0
    ingest_sec: float = 0.0
    error: str = ""

@dataclass
class MonitorSample:
    elapsed_sec: float
    rss_mb: float
    vms_mb: float
    cpu_percent: float
    db_mb: float
    label: str = ""

# ── Background monitor ────────────────────────────────────────────────────────

class ResourceMonitor:
    def __init__(self, db_path: Path, interval: float = 2.0):
        self._db_path = db_path
        self._interval = interval
        self._proc = psutil.Process()
        self._proc.cpu_percent()  # prime the counter
        self._samples: list[MonitorSample] = []
        self._label = ""
        self._stop = threading.Event()
        self._start = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def set_label(self, label: str) -> None:
        self._label = label

    def _db_size_mb(self) -> float:
        if not self._db_path.exists():
            return 0.0
        return sum(f.stat().st_size for f in self._db_path.rglob("*") if f.is_file()) / 1024 / 1024

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            info = self._proc.memory_info()
            self._samples.append(MonitorSample(
                elapsed_sec=round(time.time() - self._start, 1),
                rss_mb=round(info.rss / 1024 / 1024, 1),
                vms_mb=round(info.vms / 1024 / 1024, 1),
                cpu_percent=round(self._proc.cpu_percent(), 1),
                db_mb=round(self._db_size_mb(), 1),
                label=self._label,
            ))

    def samples(self) -> list[MonitorSample]:
        return list(self._samples)

    def peak_rss(self) -> float:
        return max((s.rss_mb for s in self._samples), default=0.0)

    def peak_cpu(self) -> float:
        return max((s.cpu_percent for s in self._samples), default=0.0)

    def avg_cpu(self) -> float:
        if not self._samples:
            return 0.0
        return round(sum(s.cpu_percent for s in self._samples) / len(self._samples), 1)

# ── Helpers ───────────────────────────────────────────────────────────────────

def db_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024

def extract_text(pdf_bytes: bytes) -> tuple[int, int, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = len(doc)
    texts = [page.get_text("text").strip() for page in doc if page.get_text("text").strip()]
    doc.close()
    full_text = "\n\n".join(texts)
    return pages, len(full_text), full_text

def chunk_text(text: str, doc_name: str) -> list[dict]:
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        piece = text[start:start + CHUNK_SIZE].strip()
        if len(piece) >= MIN_CHARS:
            chunks.append({
                "id": f"{doc_name}_chunk_{idx}",
                "text": piece,
                "metadata": {"doc_name": doc_name, "chunk_index": idx},
            })
            idx += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", default=str(ZIP_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    zip_path = Path(args.zip)
    if not zip_path.exists():
        print(f"ZIP not found: {zip_path}")
        sys.exit(1)

    LOCAL_DB_PATH.mkdir(parents=True, exist_ok=True)
    start_time = time.time()
    results: list[FileResult] = []

    monitor = ResourceMonitor(LOCAL_DB_PATH, interval=2.0)
    monitor.start()

    # ── Init OpenAI + ChromaDB ──
    total_tokens_used = 0
    if not args.dry_run:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("ERROR: OPENAI_API_KEY not set in .env")
            sys.exit(1)
        oai = OpenAI(api_key=api_key)
        print(f"Using OpenAI model: {OPENAI_MODEL}")

        monitor.set_label("db_init")
        chroma_client = chromadb.PersistentClient(path=str(LOCAL_DB_PATH))
        collection = chroma_client.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"ChromaDB ready | RAM: {psutil.Process().memory_info().rss/1024/1024:.0f} MB\n")
    else:
        openai_client = None
        collection = None
        print("DRY RUN — scan only, no embedding/ingest.")

    # ── Scan zip ──
    monitor.set_label("scanning")
    print(f"\nScanning {zip_path} ...")
    with zipfile.ZipFile(zip_path) as zf:
        pdf_entries = [
            e for e in zf.infolist()
            if e.filename.lower().endswith(".pdf")
            and e.file_size > 0
            and not Path(e.filename).name.startswith("._")
        ]

    total = len(pdf_entries)
    print(f"Found {total} real PDFs (macOS junk filtered)\n")

    if args.limit:
        pdf_entries = pdf_entries[:args.limit]
        print(f"Limited to {args.limit} PDFs\n")
        total = len(pdf_entries)

    ok = no_text = errors = total_chunks = 0

    # ── Process ──
    with zipfile.ZipFile(zip_path) as zf:
        for i, entry in enumerate(pdf_entries, 1):
            p = Path(entry.filename)
            filename = p.name
            result = FileResult(
                filename=filename,
                folder=str(p.parent),
                size_mb=round(entry.file_size / 1024 / 1024, 3),
            )

            sys.stdout.write(f"\r[{i}/{total}] {filename[:65]:<65}")
            sys.stdout.flush()

            monitor.set_label(f"processing_{i}")

            try:
                t0 = time.time()
                pdf_bytes = zf.read(entry.filename)
                pages, chars, text = extract_text(pdf_bytes)
                result.parse_sec = round(time.time() - t0, 2)
                result.pages = pages
                result.chars = chars
            except Exception as e:
                result.status = "error"
                result.error = str(e)[:200]
                errors += 1
                results.append(result)
                continue

            if chars < MIN_CHARS:
                result.status = "no_text"
                no_text += 1
                results.append(result)
                continue

            chunks = chunk_text(text, p.stem)
            result.chunks = len(chunks)

            if args.dry_run or not chunks:
                result.status = "ok" if chunks else "no_text"
                (ok if chunks else no_text).__class__  # just increment below
                if chunks:
                    ok += 1
                    total_chunks += len(chunks)
                else:
                    no_text += 1
                results.append(result)
                continue

            # Embed
            try:
                monitor.set_label("embedding")
                t0 = time.time()
                texts = [c["text"] for c in chunks]
                response = oai.embeddings.create(model=OPENAI_MODEL, input=texts)
                embeddings = [e.embedding for e in response.data]
                total_tokens_used += response.usage.total_tokens
                result.embed_sec = round(time.time() - t0, 2)
            except Exception as e:
                result.status = "error"
                result.error = f"embed: {e}"[:200]
                errors += 1
                results.append(result)
                continue

            # Ingest
            try:
                monitor.set_label("ingesting")
                t0 = time.time()
                collection.add(
                    ids=[c["id"] for c in chunks],
                    documents=[c["text"] for c in chunks],
                    metadatas=[c["metadata"] for c in chunks],
                    embeddings=embeddings,
                )
                result.ingest_sec = round(time.time() - t0, 2)
                result.status = "ok"
                ok += 1
                total_chunks += len(chunks)
            except Exception as e:
                result.status = "error"
                result.error = f"ingest: {e}"[:200]
                errors += 1

            results.append(result)

    print()
    monitor.set_label("done")
    monitor.stop()

    elapsed = time.time() - start_time
    samples = monitor.samples()
    final_db_mb = db_size_mb(LOCAL_DB_PATH)

    # ── Write monitor CSV ──
    with open(MONITOR_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(samples[0]).keys()) if samples else [])
        writer.writeheader()
        writer.writerows(asdict(s) for s in samples)

    # ── Write log CSV ──
    with open(LOG_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()) if results else [])
        writer.writeheader()
        writer.writerows(asdict(r) for r in results)

    no_text_results = [r for r in results if r.status == "no_text"]
    error_results  = [r for r in results if r.status == "error"]

    report = {
        "run": {
            "timestamp": datetime.now().isoformat(),
            "zip": str(zip_path),
            "dry_run": args.dry_run,
            "model": OPENAI_MODEL if not args.dry_run else None,
            "elapsed_sec": round(elapsed, 1),
        },
        "files": {
            "total": total,
            "ok": ok,
            "no_text": no_text,
            "errors": errors,
            "total_size_mb": round(sum(r.size_mb for r in results), 1),
        },
        "chunks": {
            "total": total_chunks,
            "avg_per_doc": round(total_chunks / ok, 1) if ok else 0,
        },
        "openai_cost": {
            "model": OPENAI_MODEL,
            "tokens_used": total_tokens_used,
            "cost_usd": round(total_tokens_used / 1_000_000 * PRICE_PER_1M, 4),
        },
        "resource_peak": {
            "ram_rss_mb": monitor.peak_rss(),
            "cpu_peak_percent": monitor.peak_cpu(),
            "cpu_avg_percent": monitor.avg_cpu(),
        },
        "disk": {
            "db_final_mb": round(final_db_mb, 1),
            "db_per_chunk_kb": round(final_db_mb * 1024 / total_chunks, 2) if total_chunks else 0,
            "projected_844_pdfs_gb": round(final_db_mb / ok * 844 / 1024, 2) if ok else 0,
        },
        "monitor_samples": len(samples),
        "no_text_files": [
            {"file": r.filename, "folder": r.folder, "size_mb": r.size_mb, "pages": r.pages}
            for r in no_text_results
        ],
        "error_files": [
            {"file": r.filename, "folder": r.folder, "error": r.error}
            for r in error_results
        ],
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Log:     {LOG_PATH}")
    print(f"Monitor: {MONITOR_PATH}  ({len(samples)} samples @ 2s)")
    print(f"Report:  {REPORT_PATH}")

    print(f"""
╔════════════════════════════════════════════════════╗
║               BENCHMARK REPORT                     ║
╠════════════════════════════════════════════════════╣
║ PDFs scanned:       {total:<6}                         ║
║ ✓ text extracted:   {ok:<6}                         ║
║ ✗ no text (scans):  {no_text:<6}                         ║
║ ✗ errors:           {errors:<6}                         ║
╠════════════════════════════════════════════════════╣
║ Total chunks:       {total_chunks:<10}                     ║
║ Avg chunks/doc:     {round(total_chunks/ok,1) if ok else 0:<10}                     ║
╠════════════════════════════════════════════════════╣
║ RAM peak (RSS):     {monitor.peak_rss():.0f} MB                        ║
║ CPU peak:           {monitor.peak_cpu():.0f}%                          ║
║ CPU avg:            {monitor.avg_cpu():.0f}%                          ║
╠════════════════════════════════════════════════════╣
║ DB size on disk:    {final_db_mb:.1f} MB                       ║
║ Per chunk:          {round(final_db_mb*1024/total_chunks,2) if total_chunks else 0} KB                        ║
║ Projected (844 PDFs): {round(final_db_mb/ok*844/1024,2) if ok else 0} GB                     ║
╠════════════════════════════════════════════════════╣
╠════════════════════════════════════════════════════╣
║ OpenAI tokens used: {total_tokens_used:<10}                     ║
║ Embedding cost:     ${total_tokens_used/1_000_000*PRICE_PER_1M:.4f}                       ║
╠════════════════════════════════════════════════════╣
║ Time elapsed:       {elapsed:.0f}s ({elapsed/60:.1f} min)               ║
╚════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
