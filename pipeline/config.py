from __future__ import annotations

from pathlib import Path

from chromadb import PersistentClient
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv

load_dotenv()

CHROMA_DB_PATH = Path("./chroma_db")
CHROMA_COLLECTION_NAME = "medical_docs"

_client_cache: ClientAPI | None = None
_collection_cache: Collection | None = None


def get_chroma_client(path: str | Path = CHROMA_DB_PATH) -> ClientAPI:
    global _client_cache
    if _client_cache is None:
        db_path = Path(path)
        db_path.mkdir(parents=True, exist_ok=True)
        _client_cache = PersistentClient(path=str(db_path))
    return _client_cache


def get_chroma_collection(name: str = CHROMA_COLLECTION_NAME) -> Collection:
    global _collection_cache
    if _collection_cache is None:
        client = get_chroma_client()
        _collection_cache = client.get_or_create_collection(name=name)
    return _collection_cache


def validate_pdf_path(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.suffix or '<no extension>'}")
    return path
