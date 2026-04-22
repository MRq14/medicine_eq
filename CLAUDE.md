# medicine_eq — Medical Equipment RAG

## What this is
RAG system for searching medical equipment service documentation (PDFs).
No LLM generation — pure retrieval only. Embeddings via OpenAI, vector store via ChromaDB.

## Stack
- Python 3.11+
- **docling** — PDF → Markdown parsing
- **chromadb** — local persistent vector store (`./chroma_db`)
- **openai** — embeddings only (`text-embedding-3-small`)
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
chroma_db/    auto-created by ChromaDB
.env          OPENAI_API_KEY
```

## Environment
- `.env` must have `OPENAI_API_KEY`
- Load with `python-dotenv` at every entry point
- ChromaDB: `PersistentClient(path="./chroma_db")`
- ChromaDB collection: `"medical_docs"`

## Key conventions
- No S3, no e-infra LLM endpoints — OpenAI embeddings only
- No LLM calls for generation, retrieval only
- Chunk ID format: `{doc_name}_chunk_{chunk_index}`
- Skip chunks under 50 characters
- BM25 index rebuilds from ChromaDB on every API startup (prototype trade-off)
- Target chunk size: ~512 tokens, ~50 token overlap
- Hybrid search uses Reciprocal Rank Fusion (RRF, k=60), returns top-5

## Build order (confirm each step before proceeding)
1. `pipeline/parser.py` — PDF → Markdown + DocMetadata
2. `pipeline/chunker.py` — HierarchicalChunker + chunk metadata
3. `pipeline/embedder.py` — batch embed with OpenAI
4. `pipeline/ingestion.py` — orchestrate pipeline → ChromaDB
5. `retrieval/vector_search.py`
6. `retrieval/bm25_search.py`
7. `retrieval/hybrid.py`
8. `api/main.py`
9. `frontend/index.html`
10. `sample_ingest.py` + `requirements.txt`

## Running
```bash
pip install -r requirements.txt
cp .env.example .env  # add OPENAI_API_KEY
uvicorn api.main:app --reload --port 8000
# drop a PDF into data/uploads/ then POST /ingest
```
