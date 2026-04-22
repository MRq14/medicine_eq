from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel

if TYPE_CHECKING:
    from pipeline.parser import ParsedDocument


class ChunkMetadata(BaseModel):
    doc_name: str
    manufacturer: str | None = None
    model: str | None = None
    equipment_type: str | None = None
    document_type: str | None = None
    chapter: str | None = None
    chunk_index: int
    token_count_estimate: int


class DocumentChunk(BaseModel):
    chunk_id: str
    text: str
    metadata: ChunkMetadata


def _estimate_tokens(text: str) -> int:
    # Rough proxy for token count without external tokenizer dependency.
    return len(re.findall(r"\S+", text))


def _split_markdown_sections(markdown: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                section_text = "\n".join(current_lines).strip()
                if section_text:
                    sections.append((current_heading, section_text))
            current_heading = stripped.lstrip("#").strip() or current_heading
            current_lines = [line]
            continue
        current_lines.append(line)

    if current_lines:
        section_text = "\n".join(current_lines).strip()
        if section_text:
            sections.append((current_heading, section_text))

    return sections


def _token_windows(text: str, target_tokens: int, overlap_tokens: int) -> Iterable[str]:
    words = re.findall(r"\S+", text)
    if not words:
        return

    step = max(target_tokens - overlap_tokens, 1)
    for start in range(0, len(words), step):
        end = min(start + target_tokens, len(words))
        if start >= end:
            break
        yield " ".join(words[start:end]).strip()
        if end == len(words):
            break


def _load_hierarchical_chunker() -> Any | None:
    candidates = (
        ("docling.chunking", "HierarchicalChunker"),
        ("docling.chunker", "HierarchicalChunker"),
        ("docling_core.transforms.chunker.hierarchical_chunker", "HierarchicalChunker"),
    )
    for module_name, class_name in candidates:
        try:
            module = __import__(module_name, fromlist=[class_name])
            return getattr(module, class_name, None)
        except Exception:
            continue
    return None


def _text_from_docling_chunk(chunk: Any) -> str:
    for attr_name in ("text", "chunk_text", "content"):
        value = getattr(chunk, attr_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(chunk).strip()


def _chapter_from_docling_chunk(chunk: Any) -> str | None:
    for attr_name in ("heading", "chapter", "section_title", "title"):
        value = getattr(chunk, attr_name, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _chunk_with_docling(parsed: "ParsedDocument") -> list[tuple[str | None, str]] | None:
    if parsed.docling_doc is None:
        return None

    chunker_cls = _load_hierarchical_chunker()
    if chunker_cls is None:
        return None

    try:
        chunker = chunker_cls()
        raw_chunks = chunker.chunk(parsed.docling_doc)
    except Exception:
        return None

    chunks: list[tuple[str | None, str]] = []
    try:
        for raw_chunk in raw_chunks:
            text = _text_from_docling_chunk(raw_chunk)
            if text:
                chunks.append((_chapter_from_docling_chunk(raw_chunk), text))
    except Exception:
        return None

    return chunks or None


def chunk_document(
    parsed: "ParsedDocument",
    target_tokens: int = 512,
    overlap_tokens: int = 50,
    min_chars: int = 50,
) -> list[DocumentChunk]:
    if target_tokens <= 0:
        raise ValueError("target_tokens must be > 0")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be >= 0")
    if overlap_tokens >= target_tokens:
        raise ValueError("overlap_tokens must be < target_tokens")

    section_texts = _chunk_with_docling(parsed)
    if section_texts is None:
        section_texts = _split_markdown_sections(parsed.markdown)

    chunks: list[DocumentChunk] = []
    chunk_index = 0

    for chapter, section_text in section_texts:
        for chunk_text in _token_windows(section_text, target_tokens, overlap_tokens):
            if len(chunk_text) < min_chars:
                continue

            metadata = ChunkMetadata(
                doc_name=parsed.metadata.doc_name,
                manufacturer=parsed.metadata.manufacturer,
                model=parsed.metadata.model,
                equipment_type=parsed.metadata.equipment_type,
                document_type=parsed.metadata.document_type,
                chapter=chapter,
                chunk_index=chunk_index,
                token_count_estimate=_estimate_tokens(chunk_text),
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{parsed.metadata.doc_name}_chunk_{chunk_index}",
                    text=chunk_text,
                    metadata=metadata,
                )
            )
            chunk_index += 1

    return chunks


if __name__ == "__main__":
    import sys
    from pipeline.parser import parse_pdf

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.chunker <path/to/file.pdf>")
        sys.exit(1)

    parsed_doc = parse_pdf(sys.argv[1])
    document_chunks = chunk_document(parsed_doc)

    print(f"Chunks: {len(document_chunks)}")
    if document_chunks:
        print("\n=== First chunk metadata ===")
        print(document_chunks[0].metadata.model_dump_json(indent=2))
        print("\n=== First chunk preview ===")
        print(document_chunks[0].text[:500])
