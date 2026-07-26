from agent.graph import build_graph
from config.settings import settings
from services.browser_controller import BrowserController


def test_build_graph_compiles() -> None:
    settings.planner_model = "test"
    settings.extraction_model = "test"
    settings.rag_model = "test"

    graph = build_graph(BrowserController())

    assert graph is not None
