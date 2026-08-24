import sqlite3
import time

from db.sqlite_memory import init_db, list_recent, log_iteration


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


def test_init_db_creates_expected_indexes(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='action_log'"
            )
        }
    assert "idx_action_log_timestamp" in names
    assert "idx_action_log_url_timestamp" in names


def test_list_recent_returns_newest_first(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    urls = ["https://a", "https://b", "https://a"]
    for i, url in enumerate(urls):
        log_iteration(
            db_path=db_path,
            url=url,
            action=f'{{"i":{i}}}',
            llm_prompt="p",
            llm_output="o",
            result="r",
        )
        time.sleep(0.001)  # ensure monotonic timestamps

    rows = list_recent(db_path, limit=10)
    assert [r.url for r in rows] == ["https://a", "https://b", "https://a"][::-1]
    # limit is honored
    assert len(list_recent(db_path, limit=1)) == 1


def test_list_recent_filters_by_url(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    for url in ["https://a", "https://b", "https://a"]:
        log_iteration(
            db_path=db_path, url=url, action="{}", llm_prompt="", llm_output="", result="",
        )

    only_a = list_recent(db_path, limit=10, url="https://a")
    assert len(only_a) == 2
    assert all(r.url == "https://a" for r in only_a)


def test_list_recent_clamps_absurd_limits(tmp_path) -> None:
    db_path = tmp_path / "memory.sqlite3"
    log_iteration(db_path=db_path, url="https://a", action="{}", llm_prompt="", llm_output="", result="")
    # Non-positive → clamped up; huge → clamped down to 500 (nothing crashes)
    assert list_recent(db_path, limit=0)
    assert list_recent(db_path, limit=10_000)
