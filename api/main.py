from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
import tempfile
import os

from pipeline.ingestion import ingest_pdf
from retrieval import hybrid_search
from pipeline.config import get_chroma_collection as get_collection

app = FastAPI(title="Medical Equipment RAG", version="1.0")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    metadata: dict
    vector_score: Optional[float] = None
    bm25_score: Optional[float] = None
    fusion_rank: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    count: int


class IngestResponse(BaseModel):
    filename: str
    chunks_ingested: int
    status: str


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Hybrid search across vector embeddings and BM25 sparse retrieval.
    Returns top-k results ranked by Reciprocal Rank Fusion.
    Optional filters: {manufacturer, model, equipment_type, document_type}
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    results = hybrid_search(
        query=request.query,
        top_k=request.top_k,
        filters=request.filters or {}
    )

    formatted_results = [
        SearchResult(
            chunk_id=r["chunk_id"],
            text=r["text"],
            metadata=r["metadata"],
            vector_score=r.get("vector_score"),
            bm25_score=r.get("bm25_score"),
            fusion_rank=i + 1
        )
        for i, r in enumerate(results)
    ]

    return SearchResponse(
        query=request.query,
        results=formatted_results,
        count=len(formatted_results)
    )


@app.post("/ingest", response_model=IngestResponse)
async def ingest(file: UploadFile = File(...)):
    """
    Upload and ingest a medical equipment PDF.
    Parses, chunks, embeds, and stores in ChromaDB.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp.flush()

            result = ingest_pdf(tmp.name)
            os.unlink(tmp.name)

            return IngestResponse(
                filename=file.filename,
                chunks_ingested=result.get("chunks_added", 0),
                status=result.get("status", "unknown")
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.get("/documents")
async def list_documents():
    """
    List all ingested documents with metadata.
    """
    try:
        collection = get_collection()
        results = collection.get()

        docs = {}
        for chunk_id, metadata in zip(results["ids"], results["metadatas"]):
            doc_name = metadata.get("document_name", "unknown")
            if doc_name not in docs:
                docs[doc_name] = {"metadata": metadata, "chunk_count": 0}
            docs[doc_name]["chunk_count"] += 1

        return {
            "documents": list(docs.values()),
            "total_chunks": len(results["ids"]),
            "total_documents": len(docs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
