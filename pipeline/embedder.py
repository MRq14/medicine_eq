from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

if TYPE_CHECKING:
    from pipeline.chunker import DocumentChunk

# Using multilingual model for better coverage across medical equipment docs
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_model_cache: SentenceTransformer | None = None



def _get_model():
    global _model_cache
    if _model_cache is None:
        _model_cache = SentenceTransformer(MODEL_NAME)
    return _model_cache


def embed_chunks(chunks: list["DocumentChunk"], batch_size: int = 100) -> list[list[float]]:
    """
    Embed a list of chunks using sentence-transformers.
    Returns list of float vectors (one per chunk, in same order).
    Processes in batches of `batch_size` to control memory usage.
    """
    if not chunks:
        return []

    model = _get_model()
    texts = [chunk.text for chunk in chunks]

    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        all_embeddings.extend(v.tolist() for v in vectors)

    return all_embeddings


if __name__ == "__main__":
    import sys
    from pipeline.chunker import chunk_document
    from pipeline.parser import parse_pdf

    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.embedder <path/to/file.pdf>")
        sys.exit(1)

    parsed_doc = parse_pdf(sys.argv[1])
    chunks = chunk_document(parsed_doc)
    print(f"Embedding {len(chunks)} chunks...")

    embeddings = embed_chunks(chunks)
    print(f"✓ Generated {len(embeddings)} embeddings")
    if embeddings:
        print(f"  Embedding vector size: {len(embeddings[0])}")
