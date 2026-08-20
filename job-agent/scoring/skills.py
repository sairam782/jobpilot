"""Skill vocabulary + extraction.

Kept intentionally deterministic (a curated vocabulary + regex passes)
rather than LLM-driven. The vocabulary is broad but not exhaustive —
adding a term is a one-line change. Skill extraction is used both for
resume profiling and for job-description keyword hits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Curated skill vocabulary. Grouped by rough family for readability, but
# treated as one flat set at runtime.
_LANGUAGES = {
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++",
    "c#", "kotlin", "swift", "ruby", "php", "scala", "r", "matlab", "julia",
    "sql", "bash", "shell", "perl", "objective-c", "dart", "elixir",
}
_ML_AI = {
    "pytorch", "tensorflow", "jax", "keras", "scikit-learn", "sklearn",
    "xgboost", "lightgbm", "hugging face", "huggingface", "transformers",
    "diffusers", "openai", "anthropic", "langchain", "llamaindex", "llama-index",
    "rag", "retrieval augmented", "fine-tuning", "finetuning", "lora", "qlora",
    "peft", "vector database", "embeddings", "prompt engineering",
    "reinforcement learning", "rlhf", "computer vision", "cv", "nlp",
    "natural language processing", "llm", "large language model", "agents",
    "multi-agent", "recommendation", "ranking", "classification",
    "clustering", "time series", "forecasting", "onnx", "triton",
    "mlflow", "wandb", "weights & biases",
}
_DATA = {
    "spark", "hadoop", "kafka", "airflow", "dbt", "snowflake", "bigquery",
    "redshift", "databricks", "delta lake", "iceberg", "postgres",
    "postgresql", "mysql", "mongodb", "cassandra", "dynamodb", "elasticsearch",
    "opensearch", "redis", "clickhouse", "duckdb", "pandas", "numpy",
    "polars", "etl", "elt", "data pipeline", "data warehouse", "warehouse",
    "olap", "oltp", "s3", "gcs", "glue", "emr",
}
_INFRA = {
    "aws", "gcp", "azure", "kubernetes", "k8s", "docker", "terraform",
    "pulumi", "helm", "istio", "ansible", "linux", "systemd", "nginx",
    "envoy", "prometheus", "grafana", "opentelemetry", "otel", "datadog",
    "sentry", "pagerduty", "gitlab ci", "github actions", "circleci",
    "jenkins", "argo", "flux",
}
_BACKEND = {
    "fastapi", "flask", "django", "starlette", "grpc", "rest", "graphql",
    "protobuf", "openapi", "swagger", "asyncio", "asyncpg", "sqlalchemy",
    "alembic", "celery", "redis queue", "rabbitmq", "nats", "kubernetes operator",
}
_FRONTEND = {
    "react", "next.js", "nextjs", "vue", "svelte", "angular", "tailwind",
    "webpack", "vite", "esbuild", "storybook", "playwright", "cypress",
    "jest", "vitest",
}
_METHODS = {
    "agile", "scrum", "kanban", "tdd", "bdd", "unit testing", "integration testing",
    "code review", "system design", "microservices", "event-driven", "service oriented",
    "distributed systems", "observability", "sre", "on-call",
}

VOCAB: set[str] = {
    *_LANGUAGES, *_ML_AI, *_DATA, *_INFRA, *_BACKEND, *_FRONTEND, *_METHODS,
}

# Compile per-term matchers once. Word-boundary regex for single tokens,
# case-insensitive substring for multi-word terms so we don't need to guess
# where a space becomes a hyphen.
_SINGLE = {t for t in VOCAB if " " not in t and len(t) > 1}
_MULTI = sorted((t for t in VOCAB if " " in t), key=len, reverse=True)

_SPECIALS = "+#."  # allow c++, c#, next.js as tokens
_BOUNDARY = re.compile(
    r"(?<![A-Za-z0-9_" + re.escape(_SPECIALS) + r"])"
    r"({tokens})"
    r"(?![A-Za-z0-9_" + re.escape(_SPECIALS) + r"])",
    re.IGNORECASE,
)


@dataclass
class ExtractedSkills:
    """Skill hits and (for JD scoring) an ordered top list."""

    skills: set[str]
    ordered: list[str]


def extract_skills(text: str) -> ExtractedSkills:
    """Return the set of vocab skills present in ``text``.

    ``ordered`` preserves first-appearance order — useful for showing
    "top 5 matched skills" without a second pass.
    """

    if not text:
        return ExtractedSkills(set(), [])
    lowered = text.lower()
    found: set[str] = set()
    ordered: list[str] = []

    for term in _MULTI:
        if term in lowered and term not in found:
            found.add(term)
            ordered.append(term)

    if _SINGLE:
        pattern = _BOUNDARY.pattern.replace(
            "{tokens}", "|".join(re.escape(t) for t in _SINGLE)
        )
        for m in re.finditer(pattern, lowered):
            term = m.group(0).lower()
            if term in _SINGLE and term not in found:
                found.add(term)
                ordered.append(term)

    return ExtractedSkills(found, ordered)


# Seniority handling ---------------------------------------------------------

_SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("staff", re.compile(r"\b(staff|distinguished|principal)\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(senior|sr\.?|sr\b)\b", re.IGNORECASE)),
    ("mid", re.compile(r"\b(mid[- ]level|mid|intermediate|ii\b|iii\b)\b", re.IGNORECASE)),
    ("junior", re.compile(r"\b(junior|jr\.?|entry[- ]level|graduate|new grad|i\b)\b", re.IGNORECASE)),
    ("intern", re.compile(r"\b(intern|internship|co[- ]?op)\b", re.IGNORECASE)),
]


def detect_seniority(text: str) -> str | None:
    """Return the strongest seniority signal in ``text``, or None."""

    if not text:
        return None
    for label, pat in _SENIORITY_PATTERNS:
        if pat.search(text):
            return label
    return None
