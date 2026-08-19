"""Resume ingestion, expansion, and lightweight chunking."""

from __future__ import annotations

import re
from pathlib import Path

from openai import AsyncOpenAI

from config.settings import settings
from services.logging_config import get_logger

log = get_logger(__name__)


async def expand_resume(input_path: Path, output_path: Path | None = None) -> Path:
    """Expand a resume text file into paragraph form for better downstream RAG.

    Falls back to a lossless copy when ``OPENAI_API_KEY`` is unset so the
    setup path still works offline.
    """

    output = output_path or settings.resume_expanded_path
    output.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".pdf":
        raw = extract_pdf_text(input_path)
    else:
        raw = input_path.read_text(encoding="utf-8")

    if not settings.openai_api_key:
        log.info("expand_resume without API key; writing normalized copy", extra={"path": str(output)})
        output.write_text(_normalize_whitespace(raw), encoding="utf-8")
        return output

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.fast_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Expand resume bullets into concise factual paragraphs. "
                    "Do not invent employers, dates, tools, or metrics."
                ),
            },
            {"role": "user", "content": raw},
        ],
        temperature=0.1,
    )
    output.write_text(response.choices[0].message.content or raw, encoding="utf-8")
    return output


def extract_pdf_text(path: Path) -> str:
    """Return the concatenated text of a PDF resume.

    Uses ``pypdf`` when available; raises a helpful error otherwise so the
    dependency is optional at install time.
    """

    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - clear runtime message
        raise RuntimeError(
            "PDF ingestion requires pypdf. Install with `pip install pypdf`."
        ) from exc

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - individual page failures shouldn't kill ingest
            text = ""
        if text:
            parts.append(text)
    return _normalize_whitespace("\n\n".join(parts))


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks suitable for embedding."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


_WS_RE = re.compile(r"[ \t]+")
_NL_RE = re.compile(r"\n{3,}")


def _normalize_whitespace(text: str) -> str:
    collapsed = _WS_RE.sub(" ", text)
    return _NL_RE.sub("\n\n", collapsed).strip()
