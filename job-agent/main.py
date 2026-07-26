"""CLI entry point for JobPilot."""

import argparse
import asyncio
import json
from pathlib import Path

from rich.console import Console

from agent.graph import build_graph
from agent.schemas import AgentState
from config.settings import settings
from db.sqlite_memory import init_db
from services.browser_controller import BrowserController

console = Console()


async def run(target_url: str, goal: str, dry_run: bool) -> AgentState:
    """Run the application graph against a target URL."""

    init_db(settings.database_path)
    async with BrowserController(headless=True) as browser:
        await browser.navigate(target_url)
        graph = build_graph(browser)
        initial = AgentState(goal=goal, target_url=target_url, metadata={"dry_run": dry_run})
        return await graph.ainvoke(initial)


def main() -> None:
    """Parse CLI args and start the JobPilot graph."""

    parser = argparse.ArgumentParser(description="Run JobPilot in safety-first dry-run mode.")
    parser.add_argument("--target-url", help="Direct job application URL to inspect.")
    parser.add_argument("--goal", default="Fill this job application using my profile.")
    parser.add_argument("--dry-run", action="store_true", default=settings.dry_run)
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="Print configured targets and planned dry-run actions without launching Playwright.",
    )
    args = parser.parse_args()

    if args.list_targets:
        list_targets()
        return

    if not args.target_url:
        parser.error("--target-url is required unless --list-targets is used")

    final_state = asyncio.run(run(args.target_url, args.goal, args.dry_run))
    console.print("[bold]Run complete[/bold]")
    console.print(final_state.model_dump_json(indent=2))


def list_targets() -> None:
    """Print configured targets without running Playwright."""

    target_config_path = Path(__file__).resolve().parent / "config" / "target_config.json"
    config = json.loads(target_config_path.read_text(encoding="utf-8"))
    planned = {
        "dry_run": settings.dry_run,
        "require_approval": settings.require_approval,
        "max_applies_per_day": settings.max_applies_per_day,
        "resume_path": config.get("resume_path"),
        "target_titles": config.get("target_titles", []),
        "locations": config.get("locations", []),
        "direct_urls": config.get("direct_urls", []),
        "planned_actions": [
            "load configured targets",
            "score each role against resume/preferences",
            "run browser loop only when --target-url is supplied",
            "stop before submit unless DRY_RUN=false and approval is explicit",
        ],
    }
    console.print_json(data=planned)


if __name__ == "__main__":
    main()
