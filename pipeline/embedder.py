import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from openai import OpenAI

if TYPE_CHECKING:
    from pipeline.chunker import DocumentChunk

load_dotenv()

OPENAI_EMBED_MODEL = "text-embedding-3-small"
COST_PER_1M_TOKENS = 0.020  # USD, text-embedding-3-small
BUDGET_USD = 5.00
_BUDGET_FILE = Path(__file__).parent.parent / ".embedding_budget.json"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _load_budget() -> dict:
    if _BUDGET_FILE.exists():
        return json.loads(_BUDGET_FILE.read_text())
    return {"total_tokens": 0, "total_cost_usd": 0.0}


def _save_budget(state: dict) -> None:
    _BUDGET_FILE.write_text(json.dumps(state, indent=2))


def get_budget_status() -> dict:
    state = _load_budget()
    return {
        **state,
        "budget_usd": BUDGET_USD,
        "remaining_usd": round(BUDGET_USD - state["total_cost_usd"], 6),
    }


def embed_chunks(chunks: list["DocumentChunk"], batch_size: int = 100) -> list[list[float]]:
    if not chunks:
        return []

    state = _load_budget()
    remaining_usd = BUDGET_USD - state["total_cost_usd"]

    # Conservative pre-flight estimate: ~3 chars per token
    texts = [chunk.text for chunk in chunks]
    est_tokens = sum(max(len(t) // 3, 1) for t in texts)
    est_cost = est_tokens / 1_000_000 * COST_PER_1M_TOKENS

    if est_cost > remaining_usd:
        raise RuntimeError(
            f"Embedding budget would be exceeded: estimated ${est_cost:.4f} for this batch, "
            f"${remaining_usd:.4f} remaining of ${BUDGET_USD:.2f} total budget "
            f"(spent so far: ${state['total_cost_usd']:.4f})."
        )

    client = _get_client()
    all_embeddings: list[list[float]] = []
    batch_total_cost = 0.0

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=OPENAI_EMBED_MODEL, input=batch)

        actual_tokens = response.usage.total_tokens
        actual_cost = actual_tokens / 1_000_000 * COST_PER_1M_TOKENS

        state["total_tokens"] += actual_tokens
        state["total_cost_usd"] += actual_cost
        batch_total_cost += actual_cost
        _save_budget(state)

        all_embeddings.extend(item.embedding for item in response.data)

    print(
        f"  Embedding cost: ${batch_total_cost:.4f} | "
        f"Total spent: ${state['total_cost_usd']:.4f} / ${BUDGET_USD:.2f}"
    )
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
    print(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0]) if embeddings else 0})")
    status = get_budget_status()
    print(f"Budget: ${status['total_cost_usd']:.4f} spent / ${status['budget_usd']:.2f} limit")
