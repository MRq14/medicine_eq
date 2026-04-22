from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Any, Optional
import tempfile
import os

from pipeline.ingestion import ingest_pdf
from retrieval import hybrid_search
from pipeline.config import get_chroma_collection, list_collection_names

app = FastAPI(title="Medical Equipment RAG", version="1.0")


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    collection_name: Optional[str] = None
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    chunk_id: str
    collection_name: Optional[str] = None
    text: str
    metadata: dict
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
    collection_name: Optional[str] = None
    doc_group: Optional[str] = None


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
        collection_name=request.collection_name,
        filters=request.filters or {}
    )

    formatted_results = [
        SearchResult(
            chunk_id=r["chunk_id"],
            collection_name=r.get("collection_name"),
            text=r["text"],
            metadata=r["metadata"],
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
async def ingest(file: UploadFile = File(...), brand: Optional[str] = None):
    """
    Upload and ingest a medical equipment PDF.
    brand: brand name, e.g. 'fuji', 'ge', 'philips' — determines which collection to store in.
    If omitted, falls back to 'general'.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp.flush()

            result = ingest_pdf(tmp.name, brand=brand)
            os.unlink(tmp.name)

            return IngestResponse(
                filename=file.filename,
                chunks_ingested=result.get("chunks_added", 0),
                status=result.get("status", "unknown"),
                collection_name=result.get("collection_name"),
                doc_group=result.get("doc_group"),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@app.get("/documents")
async def list_documents():
    """
    List all ingested documents with metadata.
    """
    try:
        docs: dict[str, dict[str, Any]] = {}
        total_chunks = 0
        total_documents = 0

        for collection_name in list_collection_names(include_existing=True):
            collection = get_chroma_collection(collection_name)
            results = collection.get(include=["metadatas"])
            ids = results.get("ids") or []
            metadatas = results.get("metadatas") or []
            total_chunks += len(ids)

            for idx, chunk_id in enumerate(ids):
                metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
                doc_name = metadata.get("doc_name", "unknown")
                doc_group = metadata.get("doc_group", "general")
                key = f"{collection_name}::{doc_group}::{doc_name}"

                if key not in docs:
                    total_documents += 1
                    docs[key] = {
                        "doc_name": doc_name,
                        "doc_group": doc_group,
                        "collection_name": collection_name,
                        "chunk_count": 0,
                        "metadata": metadata,
                    }
                docs[key]["chunk_count"] += 1

        return {
            "documents": sorted(
                docs.values(),
                key=lambda item: (item["collection_name"], item["doc_group"], item["doc_name"]),
            ),
            "total_chunks": total_chunks,
            "total_documents": total_documents,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch documents: {str(e)}")


@app.get("/collections")
async def list_collections():
    """
    List all available collections (brands).
    """
    try:
        collection_names = list_collection_names(include_existing=True)
        return {
            "collections": collection_names,
            "count": len(collection_names)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list collections: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
