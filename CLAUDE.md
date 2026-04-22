# medicine_eq — Medical Equipment RAG

## What this is
RAG system for searching medical equipment service documentation (PDFs).
No LLM generation — pure retrieval only. Embeddings via OpenAI API, vector store via ChromaDB Cloud.

## Stack
- Python 3.11+
- **docling** — PDF → Markdown parsing
- **chromadb** — Cloud-hosted vector store
- **openai** — embeddings via `text-embedding-3-small`
- **rank_bm25** — sparse BM25 retrieval
- **fastapi + uvicorn** — REST API on port 8000
- **plain HTML/CSS/JS** — single-file frontend (`frontend/index.html`)

## Project layout
```
pipeline/     parser → chunker → embedder → ingestion
retrieval/    vector_search, bm25_search, hybrid (RRF)
api/          FastAPI app (main.py)
frontend/     index.html (single file, no frameworks)
data/uploads/ drop PDFs here
.env          Chroma Cloud credentials
```

## Environment
- `.env` must have:
  - `CHROMA_CLOUD_API_KEY`
  - `CHROMA_CLOUD_TENANT`
  - `CHROMA_CLOUD_DATABASE`
- Load with `python-dotenv` at every entry point
- ChromaDB is accessed via Cloud HTTP Client.
- ChromaDB collection: Multi-collection strategy based on directory structure (`medical_docs_<slug>`).

## Key conventions
- No S3, no e-infra LLM endpoints — local transformers for embeddings, and Chroma Cloud for vector storage
- No LLM calls for generation, retrieval only
- The system supports multi-collection routing. Documents are organized by folder, inferring collection names like `medical_docs_fuji_amulet`.
- Chunk ID format: `{doc_name}_chunk_{chunk_index}`
- Skip chunks under 50 characters
- BM25 index builds across all collections and rebuilds on every API startup (prototype trade-off)
- Target chunk size: ~512 tokens, ~50 token overlap
- Hybrid search uses Reciprocal Rank Fusion (RRF, k=60), returning top-5. Includes a collection-aware fusion key to stop ID collisions.

## Build order (confirm each step before proceeding)
1. `pipeline/parser.py` — PDF → Markdown + DocMetadata
2. `pipeline/chunker.py` — HierarchicalChunker + chunk metadata
3. `pipeline/embedder.py` — batch embed with `sentence-transformers`
4. `pipeline/ingestion.py` — orchestrate pipeline → ChromaDB Cloud (with multi-collection routing)
5. `retrieval/vector_search.py`
6. `retrieval/bm25_search.py`
7. `retrieval/hybrid.py`
8. `api/main.py`
9. `frontend/index.html`
10. `sample_ingest.py` + `requirements.txt`

## Running
```bash
pip install -r requirements.txt
cp .env.example .env  # set Chroma credentials
uvicorn api.main:app --reload --port 8000
# use the frontend / drop a PDF to ingest
```
