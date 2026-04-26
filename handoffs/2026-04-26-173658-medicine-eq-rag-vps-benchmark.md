# Handoff: Medical Equipment RAG — VPS Benchmark & Infra Planning

## Session Metadata
- Created: 2026-04-26 17:36:58
- Project: /home/kara/medicine_eq
- Branch: main
- Session duration: ~3 hours

### Recent Commits (for context)
  - ffe2f4f feat: BM25 disk persistence and original filename fix
  - e1e0dc8 docs: add README
  - 43ebcf8 feat: transform RAG interface into a modern chat UI and add API error handling for missing OpenAI keys
  - 115cb3c feat: budget tracking with token monitoring, add CORS middleware, and enable multilingual search support
  - f458aed feat: replace docling with PyMuPDF for parsing and integrate OpenAI embedding cost tracking with budget management.

## Handoff Chain

- **Continues from**: None (fresh start)
- **Supersedes**: None

## Current State Summary

Session focused on two tracks: (1) fixing real bugs (ingestion filename bug, BM25 scaling), and (2) benchmarking the full PDF archive to produce precise VPS hardware recommendations for the client. A full ingest benchmark was run against `archive/Новая папка.zip` (1519 entries, 844 real PDFs) using OpenAI `text-embedding-3-small`. Results are in `data/benchmark_report.json` and `data/benchmark_monitor.csv`. The client is deciding on VPS specs and whether to add docling + PPTX/image support. `requirements.txt` needs updating and `benchmark_local_ingest.py` needs a final syntax check before next use.

## Codebase Understanding

### Architecture Overview

- **Ingestion**: `ingest_uploads.py` scans `data/uploads/` recursively, calls `pipeline/ingestion.py`, routes to ChromaDB Cloud collection named after subfolder (`Fuji Amulet` → `Fuji_Amulet`)
- **Retrieval**: hybrid RRF combining vector search (ChromaDB) + BM25 (in-memory, persisted to `data/bm25_index.pkl`)
- **API**: FastAPI on port 8000. Two key endpoints: `/search` (raw chunks) and `/ask` (chunks + gpt-4o-mini synthesis in Russian)
- **Frontend**: single HTML file at `frontend/index.html`, served separately via `python -m http.server 8080 --directory frontend`

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `pipeline/ingestion.py` | Full pipeline orchestration | Takes `original_filename` param — important for temp file uploads |
| `pipeline/parser.py` | PyMuPDF text extraction | Takes `original_filename` param to preserve real doc_name |
| `retrieval/bm25_search.py` | BM25 index with disk persistence | `save_bm25_index()` / `load_bm25_index()` using `data/bm25_index.pkl` |
| `api/main.py` | FastAPI app | Startup loads BM25 from disk; after ingest triggers rebuild |
| `ingest_uploads.py` | Batch ingest from uploads folder | Filters macOS `._` files, skips already-ingested |
| `benchmark_local_ingest.py` | Benchmark script | Uses OpenAI embeddings + local ChromaDB PersistentClient, monitors RAM/CPU |
| `data/benchmark_report.json` | Benchmark results | Key reference for VPS sizing |
| `data/benchmark_monitor.csv` | RAM/CPU samples every 2s | 699 samples from full ingest run |

### Key Patterns Discovered

- macOS `._` files appear alongside real PDFs in the zip — always filter with `not name.startswith("._")`
- `infer_collection_name()` in `pipeline/config.py` derives collection from subfolder path automatically
- BM25 is rebuilt (and saved) after every successful ingest — startup loads from disk, skips ChromaDB fetch if pickle exists
- `validate_pdf_path()` rejects non-.pdf extensions — the benchmark uses `.PDF` (uppercase) which works because it checks `suffix.lower()`

## Work Completed

### Tasks Finished

- [x] Fixed ingestion filename bug — temp file path was used as `doc_name` instead of original filename
- [x] Fixed BM25 scaling — persisted index to `data/bm25_index.pkl`, load on startup instead of rebuilding from ChromaDB
- [x] Moved `.bm25_index.pkl` from project root to `data/bm25_index.pkl`, added to `.gitignore`
- [x] Created `ingest_uploads.py` — batch ingest with dry-run, skips already-ingested, rebuilds BM25 once at end
- [x] Deleted empty `Aquilion_Prime_SP_TSX_303B` collection from ChromaDB Cloud (scanned PDF, 0 chunks)
- [x] Updated `CLAUDE.md` — removed outdated docling/no-LLM references, added current stack
- [x] Created `benchmark_local_ingest.py` — full benchmark with background RAM/CPU monitor, OpenAI embeddings, local ChromaDB
- [x] Ran full benchmark: 844 PDFs, 680 extracted, 56,443 chunks, $0.54 embedding cost, 24 min

### Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
| `pipeline/ingestion.py` | Added `original_filename` param | Fix doc_name bug when using temp paths |
| `pipeline/parser.py` | Added `original_filename` param to `parse_pdf()` | Same fix, uses real name for metadata |
| `api/main.py` | Startup BM25 load, rebuild after ingest, pass `original_filename` | Persistence + filename fix |
| `retrieval/bm25_search.py` | Added `save_bm25_index()`, `load_bm25_index()`, auto-save after rebuild | BM25 disk persistence |
| `.gitignore` | Added `data/bm25_index.pkl` | Don't commit binary index |
| `CLAUDE.md` | Full rewrite | Was severely outdated |
| `ingest_uploads.py` | New file | Batch ingest tool |
| `benchmark_local_ingest.py` | New file | Benchmark tool |

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| BM25 persistence via pickle | Elasticsearch, disk pickle, accept trade-off | Simplest, zero infra, fine for <500k chunks |
| Keep PyMuPDF over docling | Docling (better quality), PyMuPDF (fast, lightweight) | Client hasn't confirmed docling requirement yet |
| gpt-4o-mini for synthesis | gpt-4o, gpt-4o-mini | Token-efficient, strong enough for doc QA |
| Local ChromaDB for benchmark | Cloud, local | Benchmark needs isolated DB, not production data |

## Pending Work

## Immediate Next Steps

1. **Update `requirements.txt`** — add `psutil`, `sentence-transformers` (used in benchmark), verify all deps pinned
2. **Verify `benchmark_local_ingest.py`** — had a syntax check interrupted, confirm it runs cleanly end-to-end
3. **Decide on docling** — client mentioned PPTX + images; if yes, add docling back and retest RAM requirements (peaks at ~3 GB with docling models loaded)
4. **VPS decision** — share final specs with client (see below)
5. **Implement document update strategy** — discussed option 1 (delete + re-ingest with hash check), not yet implemented

### Blockers/Open Questions

- [ ] Does the client want docling for PPTX/image support? This changes RAM from 4 GB to 8 GB
- [ ] Will the VPS be self-hosted (local ChromaDB) or keep ChromaDB Cloud?
- [ ] `Aquilion Prime SP TSX-303B` PDF is scanned — client needs OCR or a text-layer version

### Deferred Items

- Document update strategy (hash-based delete + re-ingest) — discussed but not implemented
- OCR fallback in parser.py for scanned PDFs — discussed pytesseract option, client didn't confirm
- `sample_ingest.py` cleanup — superseded by `ingest_uploads.py` but not deleted yet

## Important Context

**Benchmark results (real measured data):**
- 844 real PDFs in zip (after filtering macOS junk), 680 yielded text, 115 scanned (no text), 49 errors (39 encrypted)
- 56,443 total chunks, avg 83 chunks/doc
- RAM peak during ingest: **909 MB**
- DB size on disk: **762 MB** (local ChromaDB, OpenAI 1536-dim embeddings)
- Embedding cost: **$0.54** one-time
- Per-query cost: ~$0.001 (embed + gpt-4o-mini)

**VPS recommendation based on real data:**
- Without docling: 2 vCPU, 4 GB RAM, 50 GB SSD
- With docling + PPTX/images: 4 vCPU, 8 GB RAM, 100 GB SSD

**Production ChromaDB is Cloud** (`data/benchmark_chroma/` is only for the benchmark test, separate from production).

### Assumptions Made

- Client uses ChromaDB Cloud for production (credentials in `.env`)
- Russian is the primary language for answers (system prompt hardcoded in Russian)
- All PDF ingestion happens via `ingest_uploads.py` or `/ingest` API endpoint

### Potential Gotchas

- `benchmark_local_ingest.py` writes to `data/benchmark_chroma/` — separate from production ChromaDB Cloud
- BM25 index at `data/bm25_index.pkl` is for production; benchmark has no BM25 persistence
- macOS `._` files in zips look like PDFs but are 4KB metadata stubs — always filter them
- `validate_pdf_path()` only accepts `.pdf` extension (case-insensitive) — `.PDF` works fine
- ChromaDB Cloud collection names use underscores: `Fuji_Amulet` not `Fuji Amulet`

## Environment State

### Tools/Services Used

- ChromaDB Cloud (production vector store)
- OpenAI API (`text-embedding-3-small` + `gpt-4o-mini`)
- Local ChromaDB PersistentClient (benchmark only, at `data/benchmark_chroma/`)

### Active Processes

- None (API not running at handoff time)

### Environment Variables

- `OPENAI_API_KEY`
- `CHROMA_CLOUD_API_KEY`
- `CHROMA_CLOUD_TENANT`
- `CHROMA_CLOUD_DATABASE`
- `BM25_INDEX_PATH` (optional override, defaults to `data/bm25_index.pkl`)

## Related Resources

- `data/benchmark_report.json` — full benchmark report with per-file results
- `data/benchmark_monitor.csv` — RAM/CPU samples every 2s during ingest
- `data/benchmark_log.csv` — per-PDF status (ok/no_text/error), chunks, timing
