"""Recovery node that revises one failed action."""

import json
from pathlib import Path

from pydantic_ai import Agent

from agent.schemas import ActionType, AgentState, PlannerAction
from config.settings import settings


RECOVERY_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "recovery.md"
).read_text(encoding="utf-8")


class RecoveryEngine:
    """Uses a small model to produce one revised action after failure."""

    def __init__(self) -> None:
        self.agent = Agent(
            model=settings.fast_model,
            result_type=PlannerAction,
            system_prompt=RECOVERY_PROMPT,
        )

    async def __call__(self, state: AgentState) -> AgentState:
        """Generate a revised action once, or stop after repeated failure."""

        if len(state.errors) > 1:
            state.action = PlannerAction(action=ActionType.DONE, reason="Second failure; stop safely.")
            state.done = True
            return state

        prompt = json.dumps(
            {
                "goal": state.goal,
                "page_state": state.page_state.model_dump() if state.page_state else None,
                "failed_action": state.action.model_dump() if state.action else None,
                "error": state.errors[-1] if state.errors else None,
            },
            ensure_ascii=True,
        )
        result = await self.agent.run(prompt)
        state.action = result.data
        return state
