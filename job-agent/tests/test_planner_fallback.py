"""Planner LLM fallback: retry once, then degrade to done/blocked."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.nodes.planner import PlannerAgent
from agent.schemas import ActionType, AgentState, PageState


def _state_with_page() -> AgentState:
    return AgentState(
        goal="Fill it.",
        page_state=PageState(url="https://ex/a", title="X", summary="s", raw_text_sample=""),
    )


class _StubAgent:
    """Minimal replacement for the pydantic-ai Agent. Emits scripted outcomes."""

    def __init__(self, outcomes: list[object]):
        # Each outcome is either a PlannerAction (success) or an Exception to raise.
        self._outcomes = list(outcomes)
        self.calls: list[str] = []

    async def run(self, prompt: str):
        self.calls.append(prompt)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome

        class _Result:
            output = outcome

        return _Result()


@pytest.mark.asyncio
async def test_planner_returns_llm_action_when_valid() -> None:
    planner = PlannerAgent.__new__(PlannerAgent)  # bypass __init__ (no LLM key)
    from agent.schemas import PlannerAction

    valid = PlannerAction(action=ActionType.CLICK, selector="#next", reason="ok")
    planner.agent = _StubAgent([valid])

    state = _state_with_page()
    out = await planner(state)
    assert out.action == valid
    assert len(planner.agent.calls) == 1


@pytest.mark.asyncio
async def test_planner_retries_once_on_validation_error() -> None:
    planner = PlannerAgent.__new__(PlannerAgent)
    from agent.schemas import PlannerAction

    valid = PlannerAction(action=ActionType.CLICK, selector="#next", reason="ok")
    bad = ValidationError.from_exception_data("PlannerAction", [])
    planner.agent = _StubAgent([bad, valid])

    state = _state_with_page()
    out = await planner(state)
    assert out.action == valid
    assert len(planner.agent.calls) == 2
    assert "Reminder:" in planner.agent.calls[1]  # retry appended the strict suffix


@pytest.mark.asyncio
async def test_planner_degrades_to_done_after_two_failures() -> None:
    planner = PlannerAgent.__new__(PlannerAgent)
    bad_1 = ValidationError.from_exception_data("PlannerAction", [])
    bad_2 = ValueError("still garbage")
    planner.agent = _StubAgent([bad_1, bad_2])

    state = _state_with_page()
    out = await planner(state)
    assert out.action is not None
    assert out.action.action == ActionType.DONE
    assert "invalid output" in (out.action.reason or "")


@pytest.mark.asyncio
async def test_planner_stops_on_captcha_without_calling_llm() -> None:
    planner = PlannerAgent.__new__(PlannerAgent)
    planner.agent = _StubAgent([])  # would raise IndexError if invoked

    state = _state_with_page()
    state.page_state.captcha_detected = True
    out = await planner(state)
    assert out.action.action == ActionType.DONE
    assert "CAPTCHA" in out.action.reason
