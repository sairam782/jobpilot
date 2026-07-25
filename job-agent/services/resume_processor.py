"""Resume ingestion and lightweight index building."""

from pathlib import Path

from openai import AsyncOpenAI

from config.settings import settings


async def expand_resume(input_path: Path, output_path: Path | None = None) -> Path:
    """Expand a resume text file into paragraph form for better downstream RAG."""

    output = output_path or settings.resume_expanded_path
    raw = input_path.read_text(encoding="utf-8")
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(response.choices[0].message.content or raw, encoding="utf-8")
    return output


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 120) -> list[str]:
    """Split text into overlapping chunks suitable for embedding."""

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
