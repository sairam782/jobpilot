"""Validation node for safety checks before submission."""

from agent.schemas import AgentState, ValidationResult
from config.settings import settings


class ValidatorAgent:
    """Checks required fields, CAPTCHA, errors, and approval gates."""

    async def __call__(self, state: AgentState) -> AgentState:
        """Validate the current form state and decide whether to continue or stop."""

        if state.page_state and state.page_state.captcha_detected and settings.stop_on_captcha:
            state.validation = ValidationResult(status="blocked", message="CAPTCHA detected.")
            state.done = True
            return state

        if state.execution and not state.execution.success:
            state.validation = ValidationResult(
                status="error",
                message=state.execution.error_text or state.execution.message,
            )
            state.done = True
            return state

        if state.action and state.action.action == "done":
            state.validation = ValidationResult(status="ready", message=state.action.reason)
            state.done = True
            return state

        required_remaining = []
        if state.page_state:
            for element in state.page_state.interactive_elements:
                if element.required and element.selector not in state.filled_fields:
                    required_remaining.append(element.selector)

        if required_remaining:
            state.validation = ValidationResult(
                status="continue",
                message="Required fields remain.",
                required_fields_remaining=required_remaining,
            )
        elif settings.dry_run or settings.require_approval:
            state.validation = ValidationResult(
                status="ready",
                message="Form appears ready; dry-run or approval gate prevents submission.",
            )
            state.done = True
        else:
            state.validation = ValidationResult(status="ready", message="Ready for submit.")
            state.done = True
        return state
