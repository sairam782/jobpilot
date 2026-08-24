"""Planner node that emits exactly one structured action.

The planner uses Pydantic-AI's structured output to force the LLM into
the ``PlannerAction`` schema. Most of the time that works, but LLMs
occasionally return prose that doesn't validate. Two hardening rules:

- One quiet retry with a stricter reminder appended.
- If the retry also fails, degrade to a ``done`` action with a blocked
  reason so the graph exits cleanly instead of raising and losing state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from pydantic_ai import Agent

from agent.router import TaskType, select_model
from agent.schemas import ActionType, AgentState, PlannerAction
from services.logging_config import get_logger

PLANNER_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "planner.md"
).read_text(encoding="utf-8")

_RETRY_SUFFIX = (
    "\n\nReminder: reply with EXACTLY one JSON object matching the "
    "PlannerAction schema. No prose, no code fences, no keys outside the "
    "schema. If you cannot pick a safe action, return "
    '{"action":"done","selector":null,"value":null,"reason":"<short reason>"}.'
)

log = get_logger(__name__)


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

        prompt = _build_prompt(state)
        state.action = await self._run_with_fallback(prompt)
        state.last_action = state.action
        return state

    async def _run_with_fallback(self, prompt: str) -> PlannerAction:
        """Call the LLM; retry once on invalid output, then degrade to `done`."""

        try:
            result = await self.agent.run(prompt)
            return result.output
        except (ValidationError, ValueError) as exc:
            log.warning("planner returned invalid output; retrying once", extra={"error": str(exc)})

        try:
            result = await self.agent.run(prompt + _RETRY_SUFFIX)
            return result.output
        except (ValidationError, ValueError) as exc:
            log.warning(
                "planner still invalid after retry; degrading to done/blocked",
                extra={"error": str(exc)},
            )
            return PlannerAction(
                action=ActionType.DONE,
                reason="planner produced invalid output after retry; stopping to avoid unsafe action.",
            )


def _build_prompt(state: AgentState) -> str:
    payload: dict[str, Any] = {
        "goal": state.goal,
        "page_state": state.page_state.model_dump() if state.page_state else None,
        "filled_fields": state.filled_fields,
        "last_validation": state.validation.model_dump() if state.validation else None,
    }
    return json.dumps(payload, ensure_ascii=True)
