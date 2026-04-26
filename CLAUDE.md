# medicine_eq — Medical Equipment RAG

## What this is
RAG system for searching medical equipment service documentation (PDFs).
Hybrid retrieval (vector + BM25) with LLM answer synthesis via OpenAI `gpt-4o-mini`.
Embeddings via OpenAI API, vector store via ChromaDB Cloud.

## Stack
- Python 3.11+
- **PyMuPDF (fitz)** — PDF → text parsing
- **chromadb** — Cloud-hosted vector store (PersistentClient also supported for local)
- **openai** — embeddings via `text-embedding-3-small`, answers via `gpt-4o-mini`
- **rank_bm25** — sparse BM25 retrieval, persisted to `data/bm25_index.pkl`
- **fastapi + uvicorn** — REST API on port 8000
- **plain HTML/CSS/JS** — single-file frontend (`frontend/index.html`)

## Project layout
```
pipeline/          parser → chunker → embedder → ingestion
retrieval/         vector_search, bm25_search, hybrid (RRF)
api/               FastAPI app (main.py)
frontend/          index.html (single file, no frameworks)
data/uploads/      drop PDFs here (subfolders = collections)
data/bm25_index.pkl  persisted BM25 index (rebuilt on new ingest)
ingest_uploads.py  scan data/uploads and ingest new PDFs
.env               OpenAI + Chroma Cloud credentials
```

## Environment
`.env` must have:
- `OPENAI_API_KEY`
- `CHROMA_CLOUD_API_KEY`
- `CHROMA_CLOUD_TENANT`
- `CHROMA_CLOUD_DATABASE`

Load with `python-dotenv` at every entry point.

## API endpoints
- `POST /ask` — hybrid search + gpt-4o-mini answer synthesis (Russian)
- `POST /search` — hybrid search, returns raw chunks
- `POST /ingest` — upload a PDF via multipart form
- `GET /documents` — list all ingested documents
- `GET /collections` — list all collections
- `GET /health`

## Key conventions
- Collection name derived from subfolder: `data/uploads/Fuji Amulet/` → `Fuji_Amulet`
- Chunk ID format: `{doc_name}_chunk_{chunk_index}`
- Skip chunks under 50 characters
- Chunk size: ~1500 chars, ~150 char overlap
- BM25 index persisted to `data/bm25_index.pkl` — loaded on startup, rebuilt after ingest
- Hybrid search uses Reciprocal Rank Fusion (RRF, k=60), returns top-5
- `ingest_pdf()` accepts `original_filename` param to preserve real filename when using temp paths
- `gpt-4o-mini` used for answer synthesis at temperature 0.2, answers in Russian

## Running
```bash
pip install -r requirements.txt
cp .env.example .env  # set OpenAI + Chroma credentials
uvicorn api.main:app --reload --port 8000

# Ingest PDFs from data/uploads:
python ingest_uploads.py --dry-run  # preview
python ingest_uploads.py            # ingest
```

## Serving frontend
```bash
python -m http.server 8080 --directory frontend
# open http://localhost:8080
```
