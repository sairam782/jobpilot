"""FastAPI service for resume-grounded custom question answering."""

import json
from pathlib import Path

from fastapi import FastAPI
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from agent.router import TaskType, select_model
from config.settings import settings
from services.resume_processor import chunk_text

RAG_SYSTEM_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "rag.md").read_text(
    encoding="utf-8"
)

app = FastAPI(title="JobPilot RAG API")


class ResumeQARequest(BaseModel):
    """Request body for the /resume_qa endpoint."""

    question: str


class ResumeQAResponse(BaseModel):
    """Response body for generated resume answers."""

    answer: str
    source: str
    source_chunks: list[str] = Field(default_factory=list)


@app.post("/resume_qa", response_model=ResumeQAResponse)
async def resume_qa(request: ResumeQARequest) -> ResumeQAResponse:
    """Answer a custom question using cached Q&A first, then resume text."""

    cached = _lookup_cache(request.question)
    if cached:
        return ResumeQAResponse(answer=cached, source="qa_cache", source_chunks=[])

    resume_text = settings.resume_expanded_path.read_text(encoding="utf-8")
    chunks = chunk_text(resume_text)
    source_chunks = _select_source_chunks(request.question, chunks)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=select_model(TaskType.RAG, pydantic_ai=False),
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Resume context chunks:\n"
                    f"{json.dumps(source_chunks, ensure_ascii=True)}\n\n"
                    f"Question:\n{request.question}"
                ),
            },
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    _append_cache(request.question, answer)
    return ResumeQAResponse(answer=answer, source=settings.embedding_provider, source_chunks=source_chunks)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed text using OpenAI or BAAI/bge-small-en-v1.5 based on config."""

    provider = settings.embedding_provider.lower()
    if provider == "openai":
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(model=settings.embedding_model, input=texts)
        return [item.embedding for item in response.data]
    if provider in {"bge", "baai", "sentence-transformers"}:
        from sentence_transformers import SentenceTransformer

        model_name = settings.embedding_model
        if model_name == "text-embedding-3-small":
            model_name = "BAAI/bge-small-en-v1.5"
        model = SentenceTransformer(model_name)
        return model.encode(texts, normalize_embeddings=True).tolist()
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {settings.embedding_provider}")


def _lookup_cache(question: str) -> str | None:
    if not settings.qa_cache_path.exists():
        return None
    cache = json.loads(settings.qa_cache_path.read_text(encoding="utf-8") or "[]")
    for item in cache:
        if fuzz.token_set_ratio(question, item.get("question", "")) >= 92:
            return str(item.get("answer", ""))
    return None


def _append_cache(question: str, answer: str) -> None:
    settings.qa_cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = []
    if settings.qa_cache_path.exists():
        cache = json.loads(settings.qa_cache_path.read_text(encoding="utf-8") or "[]")
    cache.append({"question": question, "answer": answer})
    settings.qa_cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _select_source_chunks(question: str, chunks: list[str], limit: int = 4) -> list[str]:
    scored = sorted(
        ((fuzz.token_set_ratio(question, chunk), chunk) for chunk in chunks),
        key=lambda item: item[0],
        reverse=True,
    )
    return [chunk for _score, chunk in scored[:limit]]
