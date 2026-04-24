from __future__ import annotations

import os
import re
from pathlib import Path

from chromadb import CloudClient, PersistentClient
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv

load_dotenv()

CHROMA_DB_PATH = Path("./chroma_db")
DOCS_ROOT = Path("docs")
UPLOADS_ROOT = Path("data/uploads")
CHROMA_CLOUD_TENANT = os.getenv("CHROMA_CLOUD_TENANT", "default")
CHROMA_CLOUD_DATABASE = os.getenv("CHROMA_CLOUD_DATABASE", "MedEq")

_client_cache: ClientAPI | None = None
_collection_cache: dict[str, Collection] = {}


def _is_cloud_enabled() -> bool:
    return bool(os.getenv("CHROMA_CLOUD_API_KEY"))


def get_chroma_client(path: str | Path = CHROMA_DB_PATH) -> ClientAPI:
    global _client_cache
    if _client_cache is None:
        if _is_cloud_enabled():
            api_key = os.getenv("CHROMA_CLOUD_API_KEY")
            _client_cache = CloudClient(
                api_key=api_key,
                tenant=CHROMA_CLOUD_TENANT,
                database=CHROMA_CLOUD_DATABASE,
            )
        else:
            db_path = Path(path)
            db_path.mkdir(parents=True, exist_ok=True)
            _client_cache = PersistentClient(path=str(db_path))
    return _client_cache


def slugify(value: str | None, default: str = "general") -> str:
    """Convert folder name to a valid collection name. 'Fuji Amulet' → 'Fuji_Amulet'"""
    if not value:
        return default
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip()).strip("_")
    return slug or default


def get_chroma_collection(name: str) -> Collection:
    if name not in _collection_cache:
        client = get_chroma_client()
        _collection_cache[name] = client.get_or_create_collection(name=name)
    return _collection_cache[name]


def list_collection_names(include_existing: bool = True) -> list[str]:
    """
    List collection names from folder structure + existing cloud collections.
    Full subfolder path → collection name (e.g. 'Fuji/Amulet' → 'Fuji_Amulet').
    """
    names: set[str] = set()

    def _collect(root: Path) -> None:
        if not root.exists() or not root.is_dir():
            return
        for subdir in root.rglob("*"):
            if subdir.is_dir() and any(subdir.glob("*.pdf")):
                try:
                    rel = subdir.resolve().relative_to(root.resolve())
                    parts = rel.parts
                    if parts:
                        names.add("_".join(slugify(p) for p in parts))
                except Exception:
                    pass

    _collect(DOCS_ROOT)
    _collect(UPLOADS_ROOT)

    if include_existing:
        try:
            client = get_chroma_client()
            for item in client.list_collections():
                col_name = item if isinstance(item, str) else getattr(item, "name", None)
                if col_name:
                    names.add(col_name)
        except Exception:
            pass

    return sorted(names)


def infer_collection_name(file_path: Path) -> str:
    """
    Derive collection name from full subfolder path relative to the uploads/docs root.
    data/uploads/Fuji/Amulet/file.pdf → 'Fuji_Amulet'
    data/uploads/Fuji/file.pdf        → 'Fuji'
    docs/Siemens/CT/file.pdf          → 'Siemens_CT'
    """
    file_path = Path(file_path)

    for root in (UPLOADS_ROOT, DOCS_ROOT):
        try:
            rel = file_path.resolve().relative_to(root.resolve())
            # All parts except the filename itself
            dir_parts = rel.parts[:-1]
            if dir_parts:
                return "_".join(slugify(p) for p in dir_parts)
        except Exception:
            pass

    # Fallback: immediate parent folder name
    parent = slugify(file_path.parent.name, default="")
    if parent and parent not in {"docs", "data", "uploads"}:
        return parent

    return "general"


def validate_pdf_path(file_path: str | Path) -> Path:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.suffix or '<no extension>'}")
    return path
