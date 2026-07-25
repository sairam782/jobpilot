from bs4 import BeautifulSoup

from services.browser_controller import BrowserController


def test_extract_interactive_elements_prefers_stable_selectors() -> None:
    soup = BeautifulSoup(
        """
        <html>
          <body>
            <label for="email">Email address</label>
            <input id="email" type="email" required />
            <select name="location"><option>Remote</option></select>
            <button>Continue</button>
          </body>
        </html>
        """,
        "html.parser",
    )
    controller = BrowserController()

    elements = controller._extract_interactive_elements(soup)

    assert elements[0].selector == "#email"
    assert elements[0].label == "Email address"
    assert elements[0].required is True
    assert elements[1].selector == 'select[name="location"]'
    assert elements[1].options == ["Remote"]


def test_summarize_text_limits_words() -> None:
    text = " ".join(f"word{i}" for i in range(200))

    summary = BrowserController._summarize_text(text, max_words=10)

    assert len(summary.split()) == 10
