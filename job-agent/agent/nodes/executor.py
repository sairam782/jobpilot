"""Execution node for deterministic Playwright actions."""

from agent.schemas import AgentState, ExecutionResult
from services.browser_controller import BrowserController


class ExecutionAgent:
    """Maps planner actions to concrete browser controller calls."""

    def __init__(self, browser: BrowserController) -> None:
        self.browser = browser

    async def __call__(self, state: AgentState) -> AgentState:
        """Execute the current action and capture success or error text."""

        if not state.action:
            state.execution = ExecutionResult(success=False, message="No action to execute.")
            state.errors.append("No action to execute.")
            return state

        if state.action.action == "done":
            state.execution = ExecutionResult(success=True, message=state.action.reason)
            state.done = True
            return state

        try:
            filled = await self.browser.execute(state.action)
            state.filled_fields.update(filled)
            state.execution = ExecutionResult(
                success=True,
                message=f"Executed {state.action.action}.",
                filled_fields=filled,
            )
        except Exception as exc:  # noqa: BLE001 - Playwright raises several action-specific errors.
            error_text = f"{type(exc).__name__}: {exc}"
            state.errors.append(error_text)
            state.execution = ExecutionResult(
                success=False,
                message="Execution failed.",
                error_text=error_text,
            )
        return state
