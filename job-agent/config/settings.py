"""Runtime settings for JobPilot."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    frontier_model: str = Field(default="openai:gpt-4o", alias="FRONTIER_MODEL")
    fast_model: str = Field(default="openai:gpt-4o-mini", alias="FAST_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")

    require_approval: bool = Field(default=True, alias="REQUIRE_APPROVAL")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    stop_on_captcha: bool = Field(default=True, alias="STOP_ON_CAPTCHA")
    stop_on_ambiguous: bool = Field(default=True, alias="STOP_ON_AMBIGUOUS")
    max_applies_per_day: int = Field(default=10, alias="MAX_APPLIES_PER_DAY")

    database_path: Path = Field(default=Path("data/jobpilot.sqlite3"), alias="DATABASE_PATH")
    qa_cache_path: Path = Field(default=Path("data/qa_cache.json"), alias="QA_CACHE_PATH")
    resume_expanded_path: Path = Field(
        default=Path("data/resume_expanded.txt"), alias="RESUME_EXPANDED_PATH"
    )
    vector_db_path: Path = Field(default=Path("data/vector_db"), alias="VECTOR_DB_PATH")
    audit_log_path: Path = Field(default=Path("logs/audit.log"), alias="AUDIT_LOG_PATH")


settings = Settings()
