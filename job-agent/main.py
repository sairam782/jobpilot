"""CLI entry point for JobPilot."""

import argparse
import asyncio

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
    parser.add_argument("--target-url", required=True, help="Direct job application URL to inspect.")
    parser.add_argument("--goal", default="Fill this job application using my profile.")
    parser.add_argument("--dry-run", action="store_true", default=settings.dry_run)
    args = parser.parse_args()

    final_state = asyncio.run(run(args.target_url, args.goal, args.dry_run))
    console.print("[bold]Run complete[/bold]")
    console.print(final_state.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
