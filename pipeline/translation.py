import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def detect_language(text: str) -> str:
    russian_chars = sum(1 for c in text if 0x0400 <= ord(c) <= 0x04FF)
    total_chars = sum(1 for c in text if c.isalpha())
    if total_chars == 0:
        return "en"
    return "ru" if russian_chars / total_chars > 0.5 else "en"


async def translate_to_english(text: str) -> str:
    if detect_language(text) == "en":
        return text
    client = _get_client()
    r = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Translate from Russian to English. Return only the translated text."},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
    )
    return r.choices[0].message.content.strip()


async def translate_batch_to_russian(texts: list[str]) -> list[str]:
    """Translate multiple English texts to Russian in a single API call."""
    if not texts:
        return []

    # Build a numbered JSON list so we can parse back reliably
    numbered = "\n".join(f'{i+1}. {t.replace(chr(10), " ")}' for i, t in enumerate(texts))

    client = _get_client()
    r = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical translator for medical equipment service manuals. "
                    "Translate each numbered English passage to Russian. "
                    "Return a JSON array of translated strings in the same order, nothing else. "
                    "Example: [\"перевод 1\", \"перевод 2\"]"
                ),
            },
            {"role": "user", "content": numbered},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    content = r.choices[0].message.content.strip()
    try:
        parsed = json.loads(content)
        # model may return {"translations": [...]} or just [...]
        if isinstance(parsed, dict):
            arr = next(iter(parsed.values()))
        else:
            arr = parsed
        if isinstance(arr, list) and len(arr) == len(texts):
            return [str(s) for s in arr]
    except Exception:
        pass

    # Fallback: return originals untranslated rather than crash
    return texts
