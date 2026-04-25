from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Optional
import tempfile
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)


from openai import AsyncOpenAI
from pipeline.ingestion import ingest_pdf
from retrieval import hybrid_search
from retrieval.bm25_search import load_bm25_index, rebuild_bm25_index
from pipeline.config import get_chroma_collection, list_collection_names

_openai = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

app = FastAPI(title="Medical Equipment RAG", version="1.0")


@app.on_event("startup")
def _startup():
    if not load_bm25_index():
        rebuild_bm25_index()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    collection_name: Optional[str] = None
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    chunk_id: str
    collection_name: Optional[str] = None
    text: str
    original_text: Optional[str] = None
    metadata: dict
    bm25_score: Optional[float] = None
    fusion_rank: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    count: int


class AskRequest(BaseModel):
    query: str
    top_k: int = 5
    collection_name: Optional[str] = None


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[SearchResult]


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
    Supports Russian queries - automatically translates to English for search,
    then translates results back to Russian.
    Returns top-k results ranked by Reciprocal Rank Fusion.
    Optional filters: {manufacturer, model, equipment_type, document_type}
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            _executor, lambda: hybrid_search(
                query=request.query,
                top_k=request.top_k,
                collection_name=request.collection_name,
                filters=request.filters or {}
            )
        )
    except KeyError as e:
        if str(e).strip("'\"") == "OPENAI_API_KEY":
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY is not configured. Add it to .env before running search.",
            )
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    formatted_results = [
        SearchResult(
            chunk_id=r["chunk_id"],
            collection_name=r.get("collection_name"),
            text=r["text"],
            original_text=None,
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


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Retrieve relevant chunks then synthesize a Russian answer with gpt-4o-mini.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(
            _executor, lambda: hybrid_search(
                query=request.query,
                top_k=request.top_k,
                collection_name=request.collection_name,
                filters={},
            )
        )
    except KeyError as e:
        if str(e).strip("'\"") == "OPENAI_API_KEY":
            raise HTTPException(
                status_code=500,
                detail="OPENAI_API_KEY is not configured. Add it to .env before running Ask AI.",
            )
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ask failed during retrieval: {str(e)}")

    if not results:
        return AskResponse(query=request.query, answer="Информация не найдена в загруженных документах.", sources=[])

    context = "\n\n---\n\n".join(
        f"[Источник {i+1}: {r['metadata'].get('doc_name','?')}, стр.{r['metadata'].get('chunk_index','?')}]\n{r['text']}"
        for i, r in enumerate(results)
    )

    completion = await _openai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты — технический ассистент по сервисному обслуживанию медицинского оборудования. "
                    "Отвечай ТОЛЬКО на основе предоставленных фрагментов документации. "
                    "Отвечай на русском языке. Будь конкретным и точным. "
                    "Если в документации нет ответа — так и скажи. "
                    "Не придумывай информацию."
                ),
            },
            {
                "role": "user",
                "content": f"Вопрос: {request.query}\n\nФрагменты документации:\n{context}",
            },
        ],
    )

    answer = completion.choices[0].message.content.strip()

    sources = [
        SearchResult(
            chunk_id=r["chunk_id"],
            collection_name=r.get("collection_name"),
            text=r["text"],
            original_text=None,
            metadata=r["metadata"],
            bm25_score=r.get("bm25_score"),
            fusion_rank=i + 1,
        )
        for i, r in enumerate(results)
    ]

    return AskResponse(query=request.query, answer=answer, sources=sources)


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

            result = ingest_pdf(tmp.name, brand=brand, original_filename=file.filename)
            os.unlink(tmp.name)

            if result.get("status") == "ok":
                await asyncio.get_event_loop().run_in_executor(_executor, rebuild_bm25_index)

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
            try:
                collection = get_chroma_collection(collection_name)
                results = collection.get(include=["metadatas"])
            except Exception:
                continue
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
