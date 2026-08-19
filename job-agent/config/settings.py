"""Runtime settings for JobPilot."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM configuration
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    planner_model: str = Field(default="gpt-4o", alias="PLANNER_MODEL")
    extraction_model: str = Field(default="gpt-4o-mini", alias="EXTRACTION_MODEL")
    rag_model: str = Field(default="gpt-4o-mini", alias="RAG_MODEL")
    frontier_model: str = Field(default="gpt-4o", alias="FRONTIER_MODEL")
    fast_model: str = Field(default="gpt-4o-mini", alias="FAST_MODEL")
    embedding_provider: str = Field(default="openai", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")

    # Browser
    proxy_url: str | None = Field(default=None, alias="PROXY_URL")
    stealth_mode: bool = Field(default=True, alias="STEALTH_MODE")
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")

    # Safety gates
    require_approval: bool = Field(default=True, alias="REQUIRE_APPROVAL")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    stop_on_captcha: bool = Field(default=True, alias="STOP_ON_CAPTCHA")
    stop_on_ambiguous: bool = Field(default=True, alias="STOP_ON_AMBIGUOUS")
    max_applies_per_day: int = Field(default=10, alias="MAX_APPLIES_PER_DAY")
    max_iterations_per_run: int = Field(default=25, alias="MAX_ITERATIONS_PER_RUN")

    # Storage
    database_path: Path = Field(default=Path("data/jobpilot.sqlite3"), alias="DATABASE_PATH")
    qa_cache_path: Path = Field(default=Path("data/qa_cache.json"), alias="QA_CACHE_PATH")
    resume_expanded_path: Path = Field(
        default=Path("data/resume_expanded.txt"), alias="RESUME_EXPANDED_PATH"
    )
    resume_pdf_path: Path | None = Field(default=None, alias="RESUME_PDF_PATH")
    vector_db_path: Path = Field(default=Path("data/vector_db"), alias="VECTOR_DB_PATH")
    audit_log_path: Path = Field(default=Path("logs/audit.log"), alias="AUDIT_LOG_PATH")

    # Scoring weights (see scoring/matcher.py)
    score_title_weight: float = Field(default=0.30, alias="SCORE_TITLE_WEIGHT")
    score_location_weight: float = Field(default=0.15, alias="SCORE_LOCATION_WEIGHT")
    score_skills_weight: float = Field(default=0.40, alias="SCORE_SKILLS_WEIGHT")
    score_resume_weight: float = Field(default=0.15, alias="SCORE_RESUME_WEIGHT")
    score_min_accept: float = Field(default=0.50, alias="SCORE_MIN_ACCEPT")

    # API
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_format: str = Field(default="json", alias="LOG_FORMAT")  # "json" or "console"
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ---------- Discovery ----------
    discovery_http_timeout: float = Field(default=15.0, alias="DISCOVERY_HTTP_TIMEOUT")
    discovery_adapter_timeout: float = Field(default=25.0, alias="DISCOVERY_ADAPTER_TIMEOUT")
    discovery_max_workers: int = Field(default=8, alias="DISCOVERY_MAX_WORKERS")

    # Per-company ATS boards (comma-separated slugs).
    greenhouse_companies: str = Field(default="", alias="GREENHOUSE_COMPANIES")
    lever_companies: str = Field(default="", alias="LEVER_COMPANIES")
    ashby_companies: str = Field(default="", alias="ASHBY_COMPANIES")
    workable_companies: str = Field(default="", alias="WORKABLE_COMPANIES")

    # Aggregator API keys.
    adzuna_app_id: str | None = Field(default=None, alias="ADZUNA_APP_ID")
    adzuna_app_key: str | None = Field(default=None, alias="ADZUNA_APP_KEY")
    jooble_api_key: str | None = Field(default=None, alias="JOOBLE_API_KEY")

    # USAJobs.gov — free but requires an email UA + API key.
    usajobs_user_agent: str | None = Field(default=None, alias="USAJOBS_USER_AGENT")
    usajobs_api_key: str | None = Field(default=None, alias="USAJOBS_API_KEY")

    @property
    def greenhouse_company_list(self) -> list[str]:
        return _csv(self.greenhouse_companies)

    @property
    def lever_company_list(self) -> list[str]:
        return _csv(self.lever_companies)

    @property
    def ashby_company_list(self) -> list[str]:
        return _csv(self.ashby_companies)

    @property
    def workable_company_list(self) -> list[str]:
        return _csv(self.workable_companies)


def _csv(raw: str) -> list[str]:
    return [c.strip() for c in raw.split(",") if c.strip()]


settings = Settings()
