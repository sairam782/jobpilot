"""Shared Pydantic schemas for the JobPilot graph."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class InteractiveElement(BaseModel):
    """Compressed representation of a fillable or clickable DOM element."""

    tag: str
    selector: str
    text: str = ""
    input_type: str | None = None
    name: str | None = None
    label: str | None = None
    placeholder: str | None = None
    required: bool = False
    options: list[str] = Field(default_factory=list)


class PageState(BaseModel):
    """Observed browser state sent to LLM nodes."""

    url: str
    title: str
    summary: str
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
    screenshot_path: str | None = None
    captcha_detected: bool = False
    raw_text_sample: str = ""


class ActionType(StrEnum):
    """Allowed actions emitted by the planner."""

    CLICK = "click"
    TYPE = "type"
    NAVIGATE = "navigate"
    UPLOAD = "upload"
    EXTRACT = "extract"
    DONE = "done"


class PlannerAction(BaseModel):
    """Single structured action produced by PlannerAgent."""

    action: ActionType
    selector: str | None = None
    value: str | None = None
    reason: str = ""


class ExecutionResult(BaseModel):
    """Deterministic result of running a planner action."""

    success: bool
    message: str
    filled_fields: dict[str, str] = Field(default_factory=dict)
    error_text: str | None = None


class ValidationResult(BaseModel):
    """Validation status after observation and execution."""

    status: Literal["ready", "blocked", "error", "continue"]
    message: str
    required_fields_remaining: list[str] = Field(default_factory=list)


class JobMatch(BaseModel):
    """Basic score for a candidate job."""

    url: HttpUrl | str
    title: str
    company: str | None = None
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class AgentState(BaseModel):
    """LangGraph state object carried through the application loop."""

    goal: str
    target_url: str | None = None
    page_state: PageState | None = None
    action: PlannerAction | None = None
    execution: ExecutionResult | None = None
    validation: ValidationResult | None = None
    filled_fields: dict[str, str] = Field(default_factory=dict)
    answer_previews: list[str] = Field(default_factory=list)
    iterations: int = 0
    errors: list[str] = Field(default_factory=list)
    done: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
