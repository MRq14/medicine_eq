# Handoff: Medical Equipment RAG — Russian UI + Ask AI mode

## Session Metadata
- Created: 2026-04-24 14:31:02
- Project: /home/kara/medicine_eq
- Branch: main
- Session duration: ~4 hours

### Recent Commits (for context)
  - fff7826 feat: budget tracking with token monitoring, add CORS middleware, and enable multilingual search support
  - f458aed feat: replace docling with PyMuPDF for parsing and integrate OpenAI embedding cost tracking with budget management.
  - 206ab7d refactor: migrate to ChromaDB Cloud with multi-collection brand routing and optimized local PDF parsing

## Handoff Chain

- **Continues from**: [2026-04-24-101037-rag-system-analysis-pymupdf.md](./2026-04-24-101037-rag-system-analysis-pymupdf.md)
- **Supersedes**: None

## Current State Summary

Built a full bilingual RAG UI for Russian-speaking medical equipment technicians. PDFs are in English, users type questions in Russian. The system uses `text-embedding-3-small` multilingual embeddings — Russian queries match English chunks directly, no query translation needed. Added a `/ask` endpoint that synthesizes a structured Russian answer via gpt-4o-mini from retrieved chunks. Frontend has Search (raw chunks) and Ask AI (synthesized answer) modes. Both PDFs from `data/uploads/Fuji Amulet/` are ingested into local ChromaDB (`chroma_db/`). Server confirmed working at ~1s for search, ~7s for ask.

## Codebase Understanding

### Architecture Overview

- **Embeddings**: `text-embedding-3-small` (OpenAI) — multilingual, handles Russian↔English semantic matching natively. No translation needed for search.
- **Vector store**: ChromaDB — configured to use local `PersistentClient` when `CHROMA_CLOUD_API_KEY` is absent (commented out in `.env`), cloud when present.
- **Search**: Hybrid — vector (ChromaDB) + BM25 (rank_bm25), fused with RRF (k=60), top-5 results.
- **LLM synthesis**: gpt-4o-mini via AsyncOpenAI, Russian system prompt, answers only from retrieved context.
- **Translation module** (`pipeline/translation.py`): exists but is NOT used in the search path anymore. Only `AsyncOpenAI` client remains there if needed.
- **API**: FastAPI on port 8000, CORS open (`*`), all blocking I/O runs in `ThreadPoolExecutor` via `run_in_executor`.
- **Frontend**: Single HTML file (`frontend/index.html`), no framework, no build step. Sidebar layout with doc list + upload, main area with search/ask.

### Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `api/main.py` | FastAPI app — `/search`, `/ask`, `/ingest`, `/documents`, `/collections` | Central entry point |
| `frontend/index.html` | Full UI — sidebar + search/ask — single file, no build needed | Open directly in browser |
| `pipeline/config.py` | ChromaDB client factory (local vs cloud), collection naming, `infer_collection_name` | Controls where data goes |
| `pipeline/ingestion.py` | Full pipeline: parse → chunk → embed → store | Called by `/ingest` endpoint |
| `pipeline/translation.py` | AsyncOpenAI client — currently unused in search path, available for future use | Keep for LLM calls |
| `retrieval/hybrid.py` | RRF fusion of vector + BM25 results | Core search logic |
| `chroma_db/` | Local ChromaDB data directory | Contains all ingested vectors |
| `.env` | API keys — `OPENAI_API_KEY` set, `CHROMA_CLOUD_API_KEY` commented out | Must have OPENAI_API_KEY |

### Key Patterns Discovered

- Collection names come from folder structure: `data/uploads/Fuji Amulet/` → `Fuji_Amulet`. Slugification done in `config.py:slugify()`.
- BM25 index is rebuilt on every API startup (in-memory, prototype trade-off). After new ingestion via API, BM25 auto-rebuilds on next startup; for immediate effect call `rebuild_bm25_index()` manually.
- ChromaDB `get_or_create_collection` is used throughout — safe to call repeatedly.
- The `._*.pdf` files in `data/uploads/` are macOS metadata artifacts — skip them, only real PDFs matter.
- Embedding budget tracked in `.embedding_budget.json` — currently $0.026 spent of $5.00 limit.

## Work Completed

### Tasks Finished

- [x] Rewrote frontend from scratch — sidebar layout, doc list always visible, upload zone, brand tabs
- [x] Fixed collections endpoint — removed `medical_docs_` prefix assumption, use raw collection names
- [x] Fixed documents endpoint — per-collection try/except so phantom collections don't crash the whole response
- [x] Removed all translation from search path — multilingual embeddings handle Russian queries natively
- [x] Added `/ask` endpoint with gpt-4o-mini synthesis in Russian
- [x] Added Search / Ask AI mode toggle in UI
- [x] All blocking I/O (hybrid_search) moved to ThreadPoolExecutor to avoid blocking asyncio event loop
- [x] Ingested both real PDFs: `FDR-1000AWS_07E.pdf` (488 chunks) and `FPD-010R008-0E.PDF` (5 chunks)
- [x] Restarted server, confirmed ~1s search / ~7s ask

### Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
| `api/main.py` | Added `/ask` endpoint, AsyncOpenAI, ThreadPoolExecutor, removed translation imports | LLM synthesis + async perf |
| `frontend/index.html` | Full rewrite — sidebar layout, mode toggle, answer card styles | Old version had broken collection logic |
| `pipeline/translation.py` | Switched to AsyncOpenAI, added `translate_batch_to_russian` | Prepared for future batch use |

### Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| No query translation | Translate RU→EN before search vs use multilingual embeddings directly | `text-embedding-3-small` is multilingual — translation adds 1s+ latency with no accuracy gain |
| No result translation | Translate EN chunks to RU vs show raw English | Adds 7-25s latency, distorts technical content (part numbers, error codes), user confirmed preference for English results |
| Keep both Search + Ask modes | Search only / Ask only / toggle | Different needs: Search for exact verification, Ask for procedural guidance |
| Local ChromaDB | Cloud was default | `CHROMA_CLOUD_API_KEY` commented out in `.env` — user explicitly asked for local |
| gpt-4o-mini for synthesis | gpt-4o / gpt-4o-mini | Cost efficiency, fast enough (~6s), sufficient quality for technical Q&A |

## Pending Work

## Immediate Next Steps

1. Evaluate Ask AI quality on the 3 test questions and compare vs raw Search
2. Consider adding page number display in result cards (chunk_index is stored in metadata)
3. The FPD-010R008-0E doc (5 chunks) gets buried by FDR (488 chunks) in search — consider per-doc score normalization or dedicated collection

### Blockers/Open Questions

- [ ] BM25 doesn't benefit from Russian queries (lexical mismatch) — vector search carries all the weight. Could add query expansion or just accept this.
- [ ] Server process is not daemonized — it will die on terminal close. Consider `nohup` or systemd unit for persistent use.

### Deferred Items

- Framework migration (Svelte/React) — decided against for now, single HTML file is sufficient at this complexity level
- Result translation to Russian — explicitly decided against (latency + distortion tradeoff)

## Context for Resuming Agent

## Important Context

The server must be started manually before the frontend works:
```bash
cd /home/kara/medicine_eq
source venv/bin/activate  # if venv exists
python -m uvicorn api.main:app --port 8000
```

Frontend is a plain HTML file — open `frontend/index.html` directly in browser (no dev server needed). It calls `http://localhost:8000` hardcoded.

ChromaDB is LOCAL — data lives in `chroma_db/` directory. Do NOT delete this directory or you lose all ingested vectors and must re-ingest (costs ~$0.009 in embeddings per run).

Both documents are in the same collection `Fuji_Amulet`. The `FPD-010R008-0E.PDF` is a component datasheet (optical transceiver module), NOT medical imaging equipment — it ended up in the same collection by folder structure.

The `/ask` endpoint is genuinely beneficial for procedural questions ("how to do X") — confirmed in testing. It synthesizes a numbered Russian step-by-step from English manual chunks.

### Assumptions Made

- User is running everything locally (no deployment)
- OPENAI_API_KEY is valid and has sufficient quota
- User wants English results with Russian UI (not translated results)
- Single collection per brand folder is the right granularity

### Potential Gotchas

- Port 8000 may already be in use from a previous session: run `fuser -k 8000/tcp` before starting
- `._FDR-1000AWS_07E.pdf` and `._FPD-010R008-0E.PDF` are macOS hidden files — `validate_pdf_path()` will reject them (correct behavior)
- If you add new PDFs and search doesn't find them immediately, BM25 index needs rebuild: restart server or call `rebuild_bm25_index()` from `retrieval.bm25_search`
- The `translate_to_english` and `translate_to_russian` functions in `pipeline/translation.py` are now `async` — don't call them synchronously

## Environment State

### Tools/Services Used

- FastAPI + uvicorn (port 8000)
- OpenAI API (`text-embedding-3-small` for embeddings, `gpt-4o-mini` for synthesis)
- ChromaDB local PersistentClient (`chroma_db/`)
- rank_bm25 for sparse retrieval

### Active Processes

- `uvicorn api.main:app --port 8000` — needs to be started each session

### Environment Variables

- `OPENAI_API_KEY` — required, set in `.env`
- `CHROMA_CLOUD_API_KEY` — commented out in `.env` (local mode active)
- `CHROMA_CLOUD_TENANT`, `CHROMA_CLOUD_DATABASE` — in `.env` but unused while cloud key is absent

## Related Resources

- `sample_ingest.py` — CLI script to ingest a single PDF and optionally run a search query
- `data/uploads/Fuji Amulet/` — drop new PDFs here, collection name auto-derived from folder path
- `.embedding_budget.json` — tracks OpenAI embedding spend ($0.026 / $5.00 used)
