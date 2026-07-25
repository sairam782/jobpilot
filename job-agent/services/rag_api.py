"""FastAPI service for resume-grounded custom question answering."""

import json
from pathlib import Path

from fastapi import FastAPI
from openai import AsyncOpenAI
from pydantic import BaseModel
from rapidfuzz import fuzz

from config.settings import settings

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


@app.post("/resume_qa", response_model=ResumeQAResponse)
async def resume_qa(request: ResumeQARequest) -> ResumeQAResponse:
    """Answer a custom question using cached Q&A first, then resume text."""

    cached = _lookup_cache(request.question)
    if cached:
        return ResumeQAResponse(answer=cached, source="qa_cache")

    resume_text = settings.resume_expanded_path.read_text(encoding="utf-8")
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.fast_model,
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Resume context:\n{resume_text[:12000]}\n\nQuestion:\n{request.question}",
            },
        ],
        temperature=0.2,
    )
    answer = response.choices[0].message.content or ""
    _append_cache(request.question, answer)
    return ResumeQAResponse(answer=answer, source="resume")


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
