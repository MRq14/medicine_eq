# medicine_eq

RAG system for searching medical equipment service documentation (PDFs).
Hybrid search (vector + BM25) over ChromaDB Cloud. Answers synthesized by `gpt-4o-mini` in Russian.

## Requirements

- Python 3.11+
- OpenAI API key
- ChromaDB Cloud account

## Setup

```bash
git clone <repo>
cd medicine_eq

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in .env:
#   OPENAI_API_KEY=...
#   CHROMA_CLOUD_API_KEY=...
#   CHROMA_CLOUD_TENANT=...
#   CHROMA_CLOUD_DATABASE=...
```

## Ingest documents

Drop PDFs into `data/uploads/<Brand Name>/`, then run:

```bash
python ingest_uploads.py
```

Already-ingested documents are skipped automatically.

## Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

## Open the frontend

```bash
python -m http.server 8080 --directory frontend
```

Then open [http://localhost:8080](http://localhost:8080).

## Project layout

```
api/          FastAPI app
pipeline/     PDF parsing, chunking, embedding, ingestion
retrieval/    Vector search, BM25, hybrid RRF fusion
frontend/     Single-file HTML/CSS/JS UI
data/uploads/ Drop PDFs here, organised by brand subfolder
```
