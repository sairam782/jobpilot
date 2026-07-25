import sqlite3

from db.sqlite_memory import init_db, log_iteration


def test_log_iteration_writes_audit_row(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    init_db(db_path)

    log_iteration(
        db_path=db_path,
        url="https://example.test",
        action='{"action":"done"}',
        llm_prompt="prompt",
        llm_output="output",
        result="result",
        error_text=None,
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT url, action, result FROM action_log").fetchone()

    assert row == ("https://example.test", '{"action":"done"}', "result")
