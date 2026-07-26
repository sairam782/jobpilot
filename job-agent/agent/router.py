"""Model router for JobPilot LLM tasks."""

from enum import StrEnum

from config.settings import settings


class TaskType(StrEnum):
    """Supported LLM task classes."""

    PLAN = "plan"
    RECOVER = "recover"
    EXTRACT = "extract"
    CLASSIFY = "classify"
    ROUTE = "route"
    RAG = "rag"


def select_model(task_type: TaskType | str, *, pydantic_ai: bool = True) -> str:
    """Select the configured model for a task type.

    Planning and recovery use the stronger planner model by default. Extraction,
    classification, routing, and RAG use faster models unless overridden.
    """

    task = TaskType(task_type)
    if task in {TaskType.PLAN, TaskType.RECOVER}:
        model = settings.planner_model or settings.frontier_model
    elif task == TaskType.RAG:
        model = settings.rag_model or settings.fast_model
    else:
        model = settings.extraction_model or settings.fast_model
    return normalize_model_name(model) if pydantic_ai else strip_provider_prefix(model)


def normalize_model_name(model: str) -> str:
    """Return a provider-qualified model name for Pydantic-AI."""

    if model == "test" or ":" in model:
        return model
    if model.startswith(("gpt-", "o")):
        return f"openai:{model}"
    return model


def strip_provider_prefix(model: str) -> str:
    """Return the raw provider model name for SDKs such as openai-python."""

    if model.startswith("openai:"):
        return model.split(":", 1)[1]
    return model
