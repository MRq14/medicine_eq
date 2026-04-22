from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from chromadb import CloudClient, PersistentClient
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from dotenv import load_dotenv

load_dotenv()

CHROMA_DB_PATH = Path("./chroma_db")
LEGACY_COLLECTION_NAME = "medical_docs"
COLLECTION_PREFIX = "medical_docs_"
COLLECTION_GENERAL = "medical_docs_general"
DOCS_ROOT = Path("docs")
UPLOADS_ROOT = Path("data/uploads")
CHROMA_CLOUD_TENANT = os.getenv("CHROMA_CLOUD_TENANT", "default")
CHROMA_CLOUD_DATABASE = os.getenv("CHROMA_CLOUD_DATABASE", "MedEq")

_client_cache: ClientAPI | None = None
_collection_cache: dict[str, Collection] = {}

DEFAULT_COLLECTION_NAMES = [COLLECTION_GENERAL]


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
                database=CHROMA_CLOUD_DATABASE
            )
        else:
            db_path = Path(path)
            db_path.mkdir(parents=True, exist_ok=True)
            _client_cache = PersistentClient(path=str(db_path))
    return _client_cache


def slugify(value: str | None, default: str = "general") -> str:
    if not value:
        return default
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or default


def collection_name_from_group(doc_group: str | None) -> str:
    group_slug = slugify(doc_group, default="general")
    return f"{COLLECTION_PREFIX}{group_slug}"


def resolve_collection_name_for_file(file_path: Path, metadata: dict[str, Any] | None = None) -> str:
    group = infer_doc_group(file_path, metadata=metadata)
    return collection_name_from_group(group)


def get_chroma_collection(name: str = COLLECTION_GENERAL) -> Collection:
    if name not in _collection_cache:
        client = get_chroma_client()
        _collection_cache[name] = client.get_or_create_collection(name=name)
    return _collection_cache[name]


def list_collection_names(include_legacy: bool = True, include_existing: bool = True) -> list[str]:
    names: set[str] = set(DEFAULT_COLLECTION_NAMES)
    if include_legacy:
        names.add(LEGACY_COLLECTION_NAME)

    if DOCS_ROOT.exists() and DOCS_ROOT.is_dir():
        for subdir in DOCS_ROOT.iterdir():
            if subdir.is_dir():
                names.add(collection_name_from_group(subdir.name))

    if UPLOADS_ROOT.exists() and UPLOADS_ROOT.is_dir():
        names.add(collection_name_from_group("uploads"))

    if include_existing:
        try:
            client = get_chroma_client()
            existing = client.list_collections()
            for item in existing:
                if isinstance(item, str):
                    names.add(item)
                else:
                    maybe_name = getattr(item, "name", None)
                    if isinstance(maybe_name, str):
                        names.add(maybe_name)
        except Exception:
            # Ignore discovery failures and fall back to known collection names.
            pass

    return sorted(names)


def infer_doc_group(file_path: Path, metadata: dict[str, Any] | None = None) -> str:
    file_path = Path(file_path)
    try:
        rel = file_path.resolve().relative_to(DOCS_ROOT.resolve())
        if rel.parts:
            return slugify(rel.parts[0], default="general")
    except Exception:
        pass

    try:
        file_path.resolve().relative_to(UPLOADS_ROOT.resolve())
        return "uploads"
    except Exception:
        pass

    parent_slug = slugify(file_path.parent.name, default="")
    if parent_slug and parent_slug not in {"docs", "data", "uploads"}:
        return parent_slug

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
