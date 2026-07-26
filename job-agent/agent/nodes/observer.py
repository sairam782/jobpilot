"""Observer node for the LangGraph loop."""

from agent.schemas import AgentState
from services.browser_controller import BrowserController


class ObserverAgent:
    """Reads the current browser page and returns compressed PageState."""

    def __init__(self, browser: BrowserController) -> None:
        self.browser = browser

    async def __call__(self, state: AgentState) -> AgentState:
        """Observe page state via Playwright and BeautifulSoup compression."""

        state.page_state = await self.browser.observe()
        state.current_url = state.page_state.url
        state.iterations += 1
        return state
