"""Memory node for audit trail and Q&A cache persistence."""

from agent.schemas import AgentState
from config.settings import settings
from db.sqlite_memory import log_iteration


class MemoryAgent:
    """Writes each loop iteration to SQLite and a human-readable audit log."""

    async def __call__(self, state: AgentState) -> AgentState:
        """Persist the current state snapshot for review and learning."""

        settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        action_json = state.action.model_dump_json() if state.action else "{}"
        output_json = state.execution.model_dump_json() if state.execution else "{}"
        error_text = "\n".join(state.errors[-2:])
        url = state.page_state.url if state.page_state else state.target_url or ""

        log_iteration(
            db_path=settings.database_path,
            url=url,
            action=action_json,
            llm_prompt="[stored as compressed page state; raw prompt omitted]",
            llm_output=output_json,
            result=state.validation.model_dump_json() if state.validation else output_json,
            error_text=error_text,
        )
        with settings.audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"url={url}\naction={action_json}\nresult={output_json}\nerror={error_text}\n---\n"
            )
        return state
