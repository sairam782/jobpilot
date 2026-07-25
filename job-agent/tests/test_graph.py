from agent.graph import build_graph
from config.settings import settings
from services.browser_controller import BrowserController


def test_build_graph_compiles() -> None:
    settings.frontier_model = "test"
    settings.fast_model = "test"

    graph = build_graph(BrowserController())

    assert graph is not None
