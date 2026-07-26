"""Recovery node that revises one failed action."""

import json
from pathlib import Path

from pydantic_ai import Agent

from agent.router import TaskType, select_model
from agent.schemas import ActionType, AgentState, PlannerAction, ValidationResult
from config.settings import settings
from db.sqlite_memory import log_iteration

RECOVERY_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "recovery.md"
).read_text(encoding="utf-8")


class RecoveryEngine:
    """Uses a small model to produce one revised action after failure."""

    def __init__(self) -> None:
        self.agent: Agent | None = None

    async def __call__(self, state: AgentState) -> AgentState:
        """Generate a revised action once, or stop after repeated failure."""

        if state.recovery_attempts >= 2:
            reason = "Recovery limit reached; blocking instead of retrying."
            state.action = PlannerAction(action=ActionType.DONE, reason=reason)
            state.validation = ValidationResult(status="blocked", message=reason)
            state.audit_entries.append(reason)
            state.errors.append(reason)
            state.done = True
            self._log_stop(state, reason)
            return state

        state.recovery_attempts += 1
        prompt = json.dumps(
            {
                "goal": state.goal,
                "page_state": state.page_state.model_dump() if state.page_state else None,
                "failed_action": state.action.model_dump() if state.action else None,
                "error": state.errors[-1] if state.errors else None,
            },
            ensure_ascii=True,
        )
        result = await self._agent().run(prompt)
        state.action = result.output
        state.last_action = state.action
        return state

    def _agent(self) -> Agent:
        if self.agent is None:
            self.agent = Agent(
                model=select_model(TaskType.RECOVER),
                output_type=PlannerAction,
                system_prompt=RECOVERY_PROMPT,
            )
        return self.agent

    @staticmethod
    def _log_stop(state: AgentState, reason: str) -> None:
        url = state.current_url or (state.page_state.url if state.page_state else state.target_url) or ""
        log_iteration(
            db_path=settings.database_path,
            url=url,
            action=state.action.model_dump_json() if state.action else "{}",
            llm_prompt="[recovery hard stop]",
            llm_output=reason,
            result="blocked",
            error_text="\n".join(state.errors[-3:]),
        )
        settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with settings.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"url={url}\nrecovery_stop={reason}\n---\n")
