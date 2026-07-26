"""Cover letter node for custom cover-letter form fields."""

from pathlib import Path

from pydantic_ai import Agent

from agent.router import TaskType, select_model
from agent.schemas import AgentState
from config.settings import settings

COVER_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "cover_letter.md"
).read_text(encoding="utf-8")


class CoverLetterAgent:
    """Generates a tailored cover letter paragraph when a cover-letter field is detected."""

    def __init__(self) -> None:
        self.agent = Agent(
            model=select_model(TaskType.RAG),
            output_type=str,
            system_prompt=COVER_PROMPT,
        )

    async def __call__(self, state: AgentState) -> AgentState:
        """Generate and store a cover letter preview for form_type=cover_letter."""

        if state.metadata.get("form_type") != "cover_letter":
            return state

        resume_text = settings.resume_expanded_path.read_text(encoding="utf-8")
        job_description = state.page_state.summary if state.page_state else state.goal
        prompt = (
            f"Resume context:\n{resume_text[:12000]}\n\n"
            f"Job description:\n{job_description[:6000]}"
        )
        result = await self.agent.run(prompt)
        state.answer_previews.append(result.output)
        state.metadata["cover_letter"] = result.output
        return state
