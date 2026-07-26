import pytest

from agent.nodes.recovery import RecoveryEngine
from agent.schemas import AgentState


@pytest.mark.asyncio
async def test_recovery_stops_after_two_attempts(tmp_path, monkeypatch) -> None:
    from config.settings import settings

    monkeypatch.setattr(settings, "database_path", tmp_path / "memory.sqlite3")
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.log")
    state = AgentState(goal="test", recovery_attempts=2, errors=["first", "second"])

    result = await RecoveryEngine()(state)

    assert result.done is True
    assert result.validation is not None
    assert result.validation.status == "blocked"
    assert "Recovery limit" in result.validation.message
