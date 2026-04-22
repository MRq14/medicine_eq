# Handoff: Medical RAG Collection Routing + Chroma Cloud Cleanup

## Session Metadata
- Created: 2026-04-22 21:07:42
- Project: /home/nazar/Documents/Skeptio/medicine_eq
- Branch: main
- Session duration: ~1 hour

### Recent Commits (for context)
  - dd8c64a feat: implement FastAPI backend and frontend interface for medical equipment RAG search and ingestion
  - 5120191 feat: implement retrieval layer with BM25 and hybrid search capabilities
  - a1d96c4 feat: embedder using multilang transformers and ingest into chromadb
  - 7e1b1ac feat: add chunking functionality
  - 731f3a3 feat: enhance medical equipment parsing with expanded keyword lists and improved brand/model detection logic

## Handoff Chain

- **Continues from**: [2026-04-22-200413-medical-rag-steps8-9-complete.md](../../handoffs/2026-04-22-200413-medical-rag-steps8-9-complete.md)
  - Previous title: Handoff: Medical RAG API & Frontend (Steps 8-9) Complete
- **Supersedes**: None

> This handoff continues work after API/frontend delivery, focusing on collection strategy simplification and DB cleanup.

## Current State Summary

Collection routing is now path-based: ingestion maps PDFs to Chroma collections using folder names from `docs/` (slugified), with uploads routed to `medical_docs_uploads`. Retrieval and API were updated to work across multiple collections by default, with optional collection targeting. Chroma Cloud was cleaned and verified: current live state has `medical_docs_fuji_amulet` containing 52 chunks for `FPD-010R008-0E`; legacy and experimental collections were removed during cleanup. Work left off with code changes unstaged/uncommitted and handoff creation.

## Codebase Understanding

## Architecture Overview

The pipeline remains parse -> chunk -> embed -> store, but storage is now collection-aware:
- `pipeline/config.py` resolves collection names from file path/group and centralizes collection discovery.
- `pipeline/ingestion.py` performs duplicate checks across all known collections before parsing/embedding.
- Retrieval (`vector_search`, `bm25_search`, `hybrid`) queries multiple collections and carries `collection_name` through ranking/output.
- API `/documents` aggregates chunk metadata from every collection and returns grouped document stats.
- Frontend displays both collection and group to make routing visible to the user.

## Critical Files

| File | Purpose | Relevance |
|------|---------|-----------|
| `pipeline/config.py` | Chroma client setup + collection routing/discovery | Core for path-based collection strategy |
| `pipeline/ingestion.py` | Ingest orchestration, duplicate detection, metadata write | Controls where chunks are stored |
| `retrieval/vector_search.py` | Dense search across one/all collections | Multi-collection retrieval behavior |
| `retrieval/bm25_search.py` | BM25 index build/search across collections | Sparse retrieval layer |
| `retrieval/hybrid.py` | RRF fusion with collection-aware keys | Prevents chunk ID collisions across collections |
| `api/main.py` | `/search`, `/ingest`, `/documents` endpoints | Exposes collection-aware behavior to UI/API clients |
| `frontend/index.html` | UI for search/upload/document list | Shows collection and doc_group in results |
| `sample_ingest.py` | Local end-to-end ingest + optional search check | Quick smoke test entry point |
| `.env` | Chroma Cloud credentials and DB target | Required runtime config (do not commit) |
| `CLAUDE.md` | Project context/spec file | Currently partially outdated vs real implementation |

## Key Patterns Discovered

- Collection naming pattern: `medical_docs_<slug>` where slug comes from top-level `docs/<folder>/...`.
- Duplicate protection is filename-based (`doc_name`) and global across discovered collections.
- In Cloud mode, metadata must exclude `None` values (`model_dump(exclude_none=True)`).
- Retrieval defaults to "all collections"; optional `collection_name` narrows scope.
- Hybrid fusion key uses `collection_name::chunk_id` so identical chunk IDs from different collections do not collide.

## Work Completed

## Tasks Finished

- [x] Implemented folder-based collection routing in config/ingestion.
- [x] Updated ingestion result payload to include `collection_name` and `doc_group`.
- [x] Updated vector/BM25/hybrid retrieval to support multi-collection search.
- [x] Updated API request/response models and `/documents` aggregation for collection-aware output.
- [x] Updated frontend to display collection/group in search results and document list.
- [x] Updated `sample_ingest.py` for end-to-end ingest + optional query workflow.
- [x] Performed Chroma Cloud cleanup/migration and validated resulting collection state.

## Files Modified

| File | Changes | Rationale |
|------|---------|-----------|
| `sample_ingest.py` | Added CLI args (`--query`, `--top-k`, `--json`), optional search after ingest, BM25 rebuild hook | Fast manual smoke tests for full pipeline |
| `pipeline/ingestion.py` | Added cross-collection duplicate check, collection/group inference, metadata enrichment | Route docs to correct collection and avoid re-ingest |
| `pipeline/config.py` | Added collection slug helpers, file-path group inference, collection listing helpers | Centralized routing and discovery logic |
| `retrieval/hybrid.py` | Added `collection_name` and generic `filters` passthrough; fusion key includes collection | Correct hybrid ranking in multi-collection setup |
| `api/main.py` | Search accepts `collection_name`/`filters`; responses include collection/group; `/documents` aggregates all collections | Surface multi-collection behavior via API |
| `frontend/index.html` | Rendered collection/group tags in search results and document list | Visibility into where docs are stored |
| `retrieval/bm25_search.py` | Added per-collection index build/search and metadata propagation of source collection | BM25 parity with vector search behavior |
| `retrieval/vector_search.py` | Added multi-collection query loop and filter support | Dense search over full dataset |

## Decisions Made

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Use folder-derived collections (`docs/<folder>`) | (A) fixed equipment taxonomy collections, (B) path-based naming | User requested simplest mapping tied to repository structure |
| Keep one collection per group, not per document | (A) collection per document, (B) collection per folder/group | Better balance of simplicity and query performance |
| Search all collections by default | (A) force explicit collection selection, (B) aggregate all by default | Better UX and backward compatibility |
| Global duplicate check by `doc_name` | (A) allow same filename in different groups, (B) skip duplicates globally | Prevent accidental duplicate ingestion in current prototype |
| Keep legacy `medical_docs` discoverable | (A) hard cutover and ignore legacy name, (B) include legacy in discovery | Safer migration path while old data may still exist |

## Pending Work

## Immediate Next Steps

1. Commit current changes in 8 modified files plus this handoff (or split into logical commits: config/ingestion, retrieval/api/frontend, docs).
2. Run an end-to-end smoke test from a real `docs/<group>/<file>.pdf` path to confirm auto-routing after latest changes.
3. Update `CLAUDE.md` so it matches actual runtime architecture (Chroma Cloud + sentence-transformers + multi-collection).

## Blockers/Open Questions

- [ ] Network access is required to validate Cloud state; sandboxed runs may fail without escalation.
- [ ] Should duplicate detection remain global by `doc_name`, or become scoped by `(collection_name, doc_name)`?
- [ ] Should `.claude/handoffs/` be tracked in git or remain local-only session memory?

## Deferred Items

- Dynamic collection picker in frontend search form (currently backend supports `collection_name`, UI does not expose selector).
- Delete/reingest document endpoint (current API has ingest/list/search only).
- Automated tests for collection routing and duplicate detection.

## Context for Resuming Agent

## Important Context

Current DB reality as of 2026-04-22: Chroma Cloud contains only `medical_docs_fuji_amulet`, with 52 chunks for document `FPD-010R008-0E`. This was re-verified after cleanup by querying the cloud collection directly. Code now expects collection names to be inferred from path structure (especially under `docs/`), so document location in repo matters for routing. There are local unstaged modifications in core pipeline/retrieval/api/frontend files; do not assume committed baseline reflects this behavior yet. Also, a teammate is working on `pipeline/parser.py`, so avoid overlapping parser edits unless absolutely necessary.

## Assumptions Made

- Chroma Cloud tenant/database and API key remain valid in `.env`.
- Source documents are placed under meaningful `docs/<group>/...` folders.
- Embedding model remains `paraphrase-multilingual-MiniLM-L12-v2` for now.
- API consumers can tolerate cross-collection search as default behavior.

## Potential Gotchas

- `list_collection_names()` + `get_or_create_collection()` can create empty collections if used carelessly in loops.
- Duplicate detection by plain `doc_name` can block ingestion of different files with same filename in different groups.
- Cloud DNS/network failures in sandbox can appear as `Could not connect to a Chroma server`.
- `.env` contains real secrets; never echo values into logs, commits, or handoff text.
- `CLAUDE.md` still describes older assumptions (OpenAI embeddings/local Chroma) and is not fully authoritative now.

## Environment State

## Tools/Services Used

- Python 3.13 virtualenv (`.venv`)
- FastAPI + Uvicorn (`api/main.py`)
- ChromaDB Cloud (`CHROMA_CLOUD_TENANT`, `CHROMA_CLOUD_DATABASE`)
- sentence-transformers embedder (`paraphrase-multilingual-MiniLM-L12-v2`)
- rank-bm25 for sparse retrieval
- local session-handoff skill scripts (`create_handoff.py`, `validate_handoff.py`)

## Active Processes

- No active `uvicorn` or `http.server` processes detected at handoff time.

## Environment Variables

- `CHROMA_CLOUD_API_KEY`
- `CHROMA_CLOUD_TENANT`
- `CHROMA_CLOUD_DATABASE`
- `OPENAI_API_KEY` (present but not required by current embedder path)

## Related Resources

- [Current Handoff](./2026-04-22-210742-medical-rag-db-folder-collections.md)
- [Previous Handoff: Steps 8-9](../../handoffs/2026-04-22-200413-medical-rag-steps8-9-complete.md)
- [Retrieval Handoff: Steps 5-7](../../handoffs/2026-04-22-194342-medical-rag-step7-retrieval.md)
- [Project Context](../../CLAUDE.md)
- [Ingestion Pipeline](../../pipeline/ingestion.py)
- [Collection Config](../../pipeline/config.py)

---

**Security Reminder**: Before finalizing, run `validate_handoff.py` to check for accidental secret exposure.
