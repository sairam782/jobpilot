"""CLI entry point for JobPilot.

Subcommands
-----------
- ``targets`` — print the loaded target config and safety flags.
- ``discover`` — run discovery adapters and enqueue matches.
- ``search`` — search across every enabled adapter (no queue writes).
- ``sources`` — list registered + enabled adapters.
- ``queue`` — list queue rows filtered by status.
- ``run-next`` — pick the next queued job and drive the agent against it.
- ``serve`` — start the FastAPI service (REST + dashboard).
- ``resume`` — ingest and inspect a resume:
    * ``resume expand PATH`` — read a .pdf or .txt, expand it (LLM if
      OPENAI_API_KEY is set, plain copy otherwise), write to
      RESUME_EXPANDED_PATH, and print a short summary.
    * ``resume show`` — print stats about the currently loaded resume.
- ``run-url`` — one-shot: drive the agent against a specific URL. Kept
  for backwards compatibility with the original entry point.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console

from config.settings import settings
from services.logging_config import configure_logging

console = Console()


async def _run_url(target_url: str, goal: str, dry_run: bool) -> object:
    from agent.graph import build_graph
    from agent.schemas import AgentState
    from db.sqlite_memory import init_db
    from services.browser_controller import BrowserController

    init_db(settings.database_path)
    async with BrowserController(headless=settings.browser_headless) as browser:
        await browser.navigate(target_url)
        graph = build_graph(browser)
        initial = AgentState(goal=goal, target_url=target_url, metadata={"dry_run": dry_run})
        return await graph.ainvoke(initial)


def _list_targets() -> None:
    target_config_path = Path(__file__).resolve().parent / "config" / "target_config.json"
    config = json.loads(target_config_path.read_text(encoding="utf-8"))
    planned = {
        "dry_run": settings.dry_run,
        "require_approval": settings.require_approval,
        "stop_on_captcha": settings.stop_on_captcha,
        "max_applies_per_day": settings.max_applies_per_day,
        "resume_path": config.get("resume_path"),
        "target_titles": config.get("target_titles", []),
        "locations": config.get("locations", []),
        "direct_urls": config.get("direct_urls", []),
        "planned_actions": [
            "load configured targets",
            "score each role against resume/preferences",
            "enqueue matches above SCORE_MIN_ACCEPT",
            "stop before submit unless DRY_RUN=false and approval is explicit",
        ],
    }
    console.print_json(data=planned)


async def _cmd_discover(args: argparse.Namespace) -> None:
    from discovery.base import SearchQuery
    from orchestrator.service import discover_and_enqueue, load_target_config, query_from_target

    target = load_target_config()
    base = query_from_target(target)
    q = SearchQuery(
        roles=list(args.role) if args.role else base.roles,
        locations=list(args.location) if args.location else base.locations,
        remote_preference=args.remote_preference or base.remote_preference,
        keywords=base.keywords,
        exclusion_keywords=base.exclusion_keywords,
        country=args.country,
        employment_types=list(args.employment_type) if args.employment_type else base.employment_types,
    )
    report = await discover_and_enqueue(
        query=q,
        sources=[s.strip() for s in args.source] if args.source else None,
        limit_per_source=args.limit_per_source,
        min_score=args.min_score,
    )
    console.print_json(
        data={
            "scanned": report.scanned,
            "matched": report.matched,
            "enqueued": report.enqueued,
            "per_source": report.per_source,
            "top": report.top,
        }
    )


async def _cmd_search(args: argparse.Namespace) -> None:
    from discovery.base import SearchQuery
    from orchestrator.service import load_target_config, query_from_target, search_jobs

    target = load_target_config()
    base = query_from_target(target)
    q = SearchQuery(
        roles=list(args.role) if args.role else base.roles,
        locations=list(args.location) if args.location else base.locations,
        remote_preference=args.remote_preference or base.remote_preference,
        keywords=base.keywords,
        exclusion_keywords=base.exclusion_keywords,
        country=args.country,
        employment_types=list(args.employment_type) if args.employment_type else base.employment_types,
    )
    report = await search_jobs(
        query=q,
        sources=[s.strip() for s in args.source] if args.source else None,
        per_source_limit=args.limit_per_source,
        min_score=args.min_score,
        top_n=args.top_n,
    )
    console.print_json(
        data={
            "query": report.query,
            "total_before_dedup": report.total_before_dedup,
            "total_after_dedup": report.total_after_dedup,
            "per_source": report.per_source,
            "results": report.results,
        }
    )


async def _cmd_queue(args: argparse.Namespace) -> None:
    from orchestrator import queue as queue_mod

    rows = queue_mod.list_jobs(
        settings.database_path,
        status=[s.strip() for s in args.status.split(",")] if args.status else None,
        limit=args.limit,
    )
    console.print_json(
        data={
            "counts": queue_mod.count_by_status(settings.database_path),
            "jobs": [row.to_public() for row in rows],
        }
    )


async def _cmd_run_next(args: argparse.Namespace) -> None:
    from orchestrator.service import process_next

    report = await process_next(dry_run=args.dry_run, require_approval=args.require_approval)
    if report is None:
        console.print("[yellow]Queue empty.[/yellow]")
        return
    console.print_json(
        data={
            "job_id": report.job_id,
            "status": report.status,
            "message": report.message,
            "filled_fields": report.filled_fields,
            "answer_previews": report.answer_previews,
            "audit_entries": report.audit_entries,
        }
    )


async def _cmd_resume(args: argparse.Namespace) -> None:
    from services.resume_processor import expand_resume, extract_pdf_text

    if args.action == "expand":
        input_path = Path(args.path).expanduser().resolve()
        if not input_path.exists():
            # Plain print (not rich): keeps the message on one line even
            # when redirected/captured, and stays out of the JSON payload
            # emitted on the happy path.
            print(f"{input_path} does not exist.", flush=True)
            raise SystemExit(2)

        output_path = Path(args.output).expanduser() if args.output else settings.resume_expanded_path
        result_path = await expand_resume(input_path, output_path=output_path)
        text = result_path.read_text(encoding="utf-8")
        _print_resume_summary(text, result_path, source=str(input_path))
        return

    if args.action == "show":
        path = settings.resume_expanded_path
        if args.path:
            path = Path(args.path).expanduser().resolve()
        if not path.exists():
            print(f"{path} does not exist.", flush=True)
            raise SystemExit(2)
        if path.suffix.lower() == ".pdf":
            text = extract_pdf_text(path)
        else:
            text = path.read_text(encoding="utf-8")
        _print_resume_summary(text, path)
        return

    # Should be unreachable because argparse enforces the choice.
    raise SystemExit(f"unknown resume action: {args.action}")


def _print_resume_summary(text: str, path: Path, source: str | None = None) -> None:
    """Show token/char/skill stats plus a short head/tail preview."""

    from scoring.skills import detect_seniority, extract_skills

    words = text.split()
    skills = extract_skills(text)
    seniority = detect_seniority(text)
    preview = text[:400].replace("\n", " ").strip()
    if len(text) > 400:
        preview += "…"

    data = {
        "source": source,
        "path": str(path),
        "chars": len(text),
        "words": len(words),
        "seniority_signal": seniority,
        "detected_skills": skills.ordered[:20],
        "preview": preview,
    }
    console.print_json(data={k: v for k, v in data.items() if v is not None})


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "services.api:app",
        host=args.host,
        port=args.port,
        log_config=None,
    )


def main() -> None:
    """Parse CLI args and dispatch to a subcommand."""

    configure_logging()

    parser = argparse.ArgumentParser(description="Run JobPilot safely.")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("targets", help="Print target config and safety flags.")

    p_discover = sub.add_parser("discover", help="Run discovery adapters and enqueue matches.")
    p_discover.add_argument("--role", action="append", default=None, help="Target job title (repeatable).")
    p_discover.add_argument("--location", action="append", default=None, help="Preferred location (repeatable).")
    p_discover.add_argument("--remote-preference", default=None,
                            choices=["remote_only", "remote_or_hybrid", "onsite_only"])
    p_discover.add_argument("--country", default="us")
    p_discover.add_argument("--employment-type", action="append", default=None,
                            choices=["full_time", "part_time", "contract", "internship", "temporary"],
                            help="Restrict to these commitments (repeatable).")
    p_discover.add_argument("--source", action="append", default=None, help="Adapter name (repeatable).")
    p_discover.add_argument("--limit-per-source", type=int, default=50)
    p_discover.add_argument("--min-score", type=float, default=None)

    p_search = sub.add_parser("search", help="Search across every enabled adapter (no queue writes).")
    p_search.add_argument("--role", action="append", default=None, help="Target job title (repeatable).")
    p_search.add_argument("--location", action="append", default=None, help="Preferred location (repeatable).")
    p_search.add_argument("--remote-preference", default=None,
                          choices=["remote_only", "remote_or_hybrid", "onsite_only"])
    p_search.add_argument("--country", default="us")
    p_search.add_argument("--employment-type", action="append", default=None,
                          choices=["full_time", "part_time", "contract", "internship", "temporary"],
                          help="Restrict to these commitments (repeatable).")
    p_search.add_argument("--source", action="append", default=None, help="Adapter name (repeatable).")
    p_search.add_argument("--limit-per-source", type=int, default=50)
    p_search.add_argument("--min-score", type=float, default=None)
    p_search.add_argument("--top-n", type=int, default=25)

    sub.add_parser("sources", help="List registered + enabled discovery adapters.")

    p_queue = sub.add_parser("queue", help="List queue rows.")
    p_queue.add_argument("--status", default=None, help="Comma-separated status filter.")
    p_queue.add_argument("--limit", type=int, default=50)

    p_run = sub.add_parser("run-next", help="Process the next queued job.")
    p_run.add_argument("--dry-run", action="store_true", default=None)
    p_run.add_argument("--require-approval", action="store_true", default=None)

    p_serve = sub.add_parser("serve", help="Start the FastAPI service.")
    p_serve.add_argument("--host", default=settings.api_host)
    p_serve.add_argument("--port", type=int, default=settings.api_port)

    p_resume = sub.add_parser("resume", help="Ingest and inspect a resume.")
    resume_actions = p_resume.add_subparsers(dest="action", required=True)
    p_expand = resume_actions.add_parser("expand", help="Extract text from a PDF or TXT, expand it, and save.")
    p_expand.add_argument("path", help="Path to .pdf or .txt resume.")
    p_expand.add_argument("--output", default=None, help="Override RESUME_EXPANDED_PATH for this run.")
    p_show = resume_actions.add_parser("show", help="Print stats about the currently-loaded resume.")
    p_show.add_argument("path", nargs="?", default=None,
                        help="Optional path override; defaults to RESUME_EXPANDED_PATH.")

    p_url = sub.add_parser("run-url", help="Drive the agent against a specific URL (one-shot).")
    p_url.add_argument("--target-url", required=True)
    p_url.add_argument("--goal", default="Fill this job application using my profile.")
    p_url.add_argument("--dry-run", action="store_true", default=settings.dry_run)

    # Legacy flags: keep the original invocation working.
    parser.add_argument("--target-url", help=argparse.SUPPRESS)
    parser.add_argument("--goal", default="Fill this job application using my profile.", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", default=settings.dry_run, help=argparse.SUPPRESS)
    parser.add_argument("--list-targets", action="store_true", help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.list_targets or args.cmd == "targets":
        _list_targets()
        return

    if args.cmd == "discover":
        asyncio.run(_cmd_discover(args))
        return
    if args.cmd == "search":
        asyncio.run(_cmd_search(args))
        return
    if args.cmd == "sources":
        from discovery import registry as reg
        console.print_json(
            data={
                "registered": reg.registered_sources(),
                "enabled": reg.enabled_sources(),
            }
        )
        return
    if args.cmd == "queue":
        asyncio.run(_cmd_queue(args))
        return
    if args.cmd == "run-next":
        asyncio.run(_cmd_run_next(args))
        return
    if args.cmd == "resume":
        asyncio.run(_cmd_resume(args))
        return
    if args.cmd == "serve":
        _cmd_serve(args)
        return

    # Legacy path: `python main.py --target-url ...`
    url = getattr(args, "target_url", None)
    if args.cmd == "run-url":
        url = args.target_url
    if not url:
        parser.error("no command given; try `python main.py serve` or `--help`.")
    goal = args.goal
    dry_run = args.dry_run if args.dry_run is not None else settings.dry_run
    final_state = asyncio.run(_run_url(url, goal, dry_run))
    console.print("[bold]Run complete[/bold]")
    console.print(final_state.model_dump_json(indent=2) if hasattr(final_state, "model_dump_json") else str(final_state))


if __name__ == "__main__":
    main()
