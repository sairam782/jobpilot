import pytest

from agent.nodes.validator import ValidatorAgent
from agent.schemas import AgentState, PageState
from services.browser_controller import CAPTCHA_PATTERNS


@pytest.mark.asyncio
async def test_validator_blocks_captcha_text() -> None:
    html_text = "Please complete this CAPTCHA to verify you are human."
    state = AgentState(
        goal="test",
        page_state=PageState(
            url="https://example.test",
            title="Captcha",
            summary=html_text,
            captcha_detected=bool(CAPTCHA_PATTERNS.search(html_text)),
            raw_text_sample=html_text,
        ),
    )

    result = await ValidatorAgent()(state)

    assert result.validation is not None
    assert result.validation.status == "blocked"
    assert result.done is True
