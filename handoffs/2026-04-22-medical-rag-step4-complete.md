# Handoff: Medical Equipment RAG System — Steps 1-4 Complete

**Date:** 2026-04-22  
**Project:** medicine_eq (RAG system for medical equipment service documentation)  
**Branch:** main  
**Session Progress:** Steps 1-4 of 10-step build order complete  
**Status:** Ready for retrieval layer (Steps 5-7)

---

## Current State Summary

**Pipeline infrastructure is fully functional:**
- ✅ **Parser (Step 1):** PDF → Markdown + metadata extraction with validated keywords
- ✅ **Chunker (Step 2):** Hierarchical chunking with metadata (tested)
- ✅ **Embedder (Step 3):** OpenAI text-embedding-3-small with batching & caching
- ✅ **Ingestion (Step 4):** Full orchestration with deduplication **before** expensive operations
- ✅ **Config (shared utilities):** Centralized ChromaDB client, path validation, env loading

**Critical fixes applied during simplify review:**
1. Fixed embedding model from sentence-transformers → OpenAI (per CLAUDE.md spec)
2. Moved duplicate check in ingestion to BEFORE parsing (saves embedding API costs)
3. Consolidated ChromaDB client creation into `pipeline/config.py`
4. Unified file validation across modules

**Tested & validated:**
- Metadata extraction on real FDR-1000AWS manual (FUJIFILM X-ray)
- Equipment type detection: "x_ray" ✓
- Document type detection: "service_manual" ✓
- Keyword lists cover 17 equipment types + 5 document types

---

## Important Context

### Architecture Decisions
- **Embeddings:** OpenAI text-embedding-3-small (not local transformers)
  - Reason: Aligns with CLAUDE.md, better quality, cost-effective at $0.02/1M tokens
  - Requires: `OPENAI_API_KEY` in `.env`
  
- **Chunking:** Hierarchical with ~512 token target, ~50 token overlap
  - Skip chunks under 50 chars
  - Preserve section titles and chapter structure

- **Storage:** ChromaDB PersistentClient at `./chroma_db`
  - Collection: `"medical_docs"`
  - Chunk ID format: `{doc_name}_chunk_{chunk_index}`

- **Deduplication:** Check ChromaDB **before** parsing
  - Prevents wasted embedding API calls on duplicate docs
  - Checks by `doc_name` (derived from filename stem)

### File Structure
```
pipeline/
  ├── __init__.py
  ├── config.py          [NEW] Shared utilities (ChromaDB, path validation, env)
  ├── parser.py          PDF → Markdown + DocMetadata
  ├── chunker.py         Markdown → chunks with full metadata
  ├── embedder.py        Chunks → OpenAI embeddings (batched)
  └── ingestion.py       Orchestrates full pipeline → ChromaDB
retrieval/               [NEXT: Steps 5-7]
api/                     [NEXT: Step 8]
frontend/                [NEXT: Step 9]
```

### Key Patterns Discovered
1. **Module-level client caching:** `_get_client()` pattern used in both embedder and config
2. **Single-pass data preparation:** Zip chunks + embeddings when inserting to ChromaDB
3. **Early-return deduplication:** Check before expensive ops to save cost
4. **Shared config imports:** Always import `pipeline.config` to ensure `load_dotenv()` runs once

---

## Immediate Next Steps

### Step 5: `retrieval/vector_search.py`
Query ChromaDB collection with embedded query vector.
- Input: query string + optional metadata filters (manufacturer, model, equipment_type)
- Output: top-10 results with text, metadata, distance score
- Use: `get_chroma_collection()` from config
- Embed query with same `embed_chunks()` function used in pipeline

### Step 6: `retrieval/bm25_search.py`
Build & query BM25 sparse index from ChromaDB.
- On startup: load all doc texts from ChromaDB into BM25Okapi index
- On query: return top-10 BM25-scored results, chunk_ids aligned with vector results
- Note: Index rebuilds on API startup (acceptable for prototype)

### Step 7: `retrieval/hybrid.py`
Combine vector + BM25 results using Reciprocal Rank Fusion (RRF).
- Formula: `score(d) = sum(1 / (k + rank(d)))` where k=60
- Deduplicate by chunk_id, return top-5 fused results

### Step 8: `api/main.py`
FastAPI endpoints:
- `POST /ingest` — calls `ingest_pdf(file_path)` from pipeline
- `POST /search` — calls hybrid search from retrieval layer
- `GET /documents` — list ingested docs with metadata

### Step 9: `frontend/index.html`
Single-file vanilla JS UI (no frameworks).

### Step 10: `sample_ingest.py` + update `requirements.txt`
End-to-end test script.

---

## Critical Files

| File | Purpose | Status |
|------|---------|--------|
| `pipeline/config.py` | Shared ChromaDB client, env loading, path validation | ✅ Complete |
| `pipeline/parser.py` | PDF parsing + metadata extraction | ✅ Complete, tested |
| `pipeline/chunker.py` | Hierarchical chunking | ✅ Complete |
| `pipeline/embedder.py` | OpenAI embedding with batching | ✅ Complete, fixed |
| `pipeline/ingestion.py` | Full pipeline orchestration | ✅ Complete, optimized |
| `requirements.txt` | Dependencies | ✅ Updated (openai instead of sentence-transformers) |
| `CLAUDE.md` | Project spec & conventions | ✅ Complete |

---

## Known Issues & Gotchas

1. **Missing `.env` file:** Code expects `OPENAI_API_KEY` in `.env`
   - Workaround: Create `.env` with `OPENAI_API_KEY=sk-...`
   - None of the pipeline code will work without this

2. **docling model downloads:** First parse on a system downloads OCR models (~30MB)
   - Expected on first run, subsequent runs use cache

3. **ChromaDB path:** Hardcoded to `./chroma_db` relative to cwd
   - Make sure the API/ingestion runs from project root

4. **Duplicate check by filename stem:** If two PDFs have same name, only first is ingested
   - Workaround: Rename files uniquely before ingesting

---

## Decisions Made & Rationale

**Why OpenAI embeddings instead of sentence-transformers?**
- CLAUDE.md specifies OpenAI as the stack choice
- Better quality for technical medical terminology
- Cost-effective at scale ($0.02 per 1M tokens)
- Simplifies dependency tree (no heavy transformer model)

**Why check duplicates before parsing?**
- Parsing + chunking + embedding is expensive (especially OpenAI API calls)
- If doc already exists, we waste ~90% of the work
- Moving the check forward saves cost on repeated ingestions
- Trade-off: Requires one ChromaDB query upfront (negligible cost)

**Why single-pass data prep in ingestion?**
- Original code iterated chunks 3 times (IDs, documents, metadatas)
- Now does it once with dict comprehension
- Slight optimization for large documents

**Why consolidate ChromaDB client in config?**
- Prevents recreating PersistentClient in each module
- Ensures consistent configuration across pipeline, retrieval, and API
- PersistentClient has startup overhead (index loading), worth caching

---

## Pending Work

- [ ] Step 5: `retrieval/vector_search.py` — vector similarity queries
- [ ] Step 6: `retrieval/bm25_search.py` — sparse BM25 search
- [ ] Step 7: `retrieval/hybrid.py` — Reciprocal Rank Fusion combining
- [ ] Step 8: `api/main.py` — FastAPI backend
- [ ] Step 9: `frontend/index.html` — vanilla JS UI
- [ ] Step 10: `sample_ingest.py` + test with real PDF
- [ ] Create `.env` with `OPENAI_API_KEY` before testing

---

## Testing Notes

**To test the pipeline so far:**
```bash
# Ensure venv is active and requirements installed
source venv/bin/activate
pip install -r requirements.txt

# Create .env with your OpenAI key
cp .env.example .env  # or manually create with OPENAI_API_KEY

# Test parser on a real PDF
python -m pipeline.parser /path/to/pdf.pdf

# Test full ingestion pipeline
python -m pipeline.ingestion /path/to/pdf.pdf
```

**Files known to work:**
- `/home/kara/Downloads/FDR-1000AWS_07E.pdf` — FUJIFILM X-ray service manual
  - Correctly extracts: manufacturer=FUJIFILM, model=FDR-1000/2000, equipment_type=x_ray, document_type=service_manual

---

## Environment

- **Python:** 3.11+ (tested on 3.12)
- **venv:** `/home/kara/medicine_eq/venv/` (already created with dependencies)
- **Project path:** `/home/kara/medicine_eq/`
- **Git branch:** main
- **Recent commits:** chunking, parser enhancements, initial project setup

---

## Next Session Checklist

- [ ] Verify `.env` has `OPENAI_API_KEY`
- [ ] Check venv is activated: `source venv/bin/activate`
- [ ] Review "Immediate Next Steps" section above
- [ ] Start with Step 5: `retrieval/vector_search.py`
- [ ] Reference "Key Patterns Discovered" when writing retrieval modules
