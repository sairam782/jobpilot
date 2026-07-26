"""Planner node that emits exactly one structured action."""

import json
from pathlib import Path

from pydantic_ai import Agent

from agent.router import TaskType, select_model
from agent.schemas import ActionType, AgentState, PlannerAction

PLANNER_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "planner.md"
).read_text(encoding="utf-8")


class PlannerAgent:
    """Plans the next browser action using structured output."""

    def __init__(self) -> None:
        self.agent = Agent(
            model=select_model(TaskType.PLAN),
            output_type=PlannerAction,
            system_prompt=PLANNER_PROMPT,
        )

    async def __call__(self, state: AgentState) -> AgentState:
        """Return one JSON-compatible PlannerAction for the current PageState."""

        if not state.page_state:
            state.action = PlannerAction(action=ActionType.DONE, reason="No page state available.")
            return state

        if state.page_state.captcha_detected:
            state.action = PlannerAction(action=ActionType.DONE, reason="CAPTCHA detected; stop.")
            return state

        prompt = json.dumps(
            {
                "goal": state.goal,
                "page_state": state.page_state.model_dump(),
                "filled_fields": state.filled_fields,
                "last_validation": state.validation.model_dump() if state.validation else None,
            },
            ensure_ascii=True,
        )
        result = await self.agent.run(prompt)
        state.action = result.output
        state.last_action = state.action
        return state
