"""Playwright browser controller with safe DOM compression."""

import asyncio
import random
import re
from pathlib import Path
from typing import Self

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from agent.schemas import InteractiveElement, PageState, PlannerAction
from config.settings import settings

CAPTCHA_PATTERNS = re.compile(
    r"captcha|recaptcha|hcaptcha|verify you are human", re.IGNORECASE
)
USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
]
VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900},
]
GEOLOCATIONS = [
    {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 50},
    {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 50},
    {"latitude": 41.8781, "longitude": -87.6298, "accuracy": 50},
]


class BrowserController:
    """Async Playwright wrapper for observing and acting on application pages."""

    def __init__(self, screenshots_dir: Path = Path("logs/screenshots"), headless: bool = True) -> None:
        self.screenshots_dir = screenshots_dir
        self.headless = headless
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> Self:
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        launch_args = {
            "headless": self.headless,
            "args": ["--disable-blink-features=AutomationControlled"]
            if settings.stealth_mode
            else [],
        }
        if settings.proxy_url:
            launch_args["proxy"] = {"server": settings.proxy_url}
        self.browser = await self._playwright.chromium.launch(**launch_args)
        context_options = {
            "user_agent": random.choice(USER_AGENTS),
            "viewport": random.choice(VIEWPORTS),
            "geolocation": random.choice(GEOLOCATIONS),
            "permissions": ["geolocation"],
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        self.context = await self.browser.new_context(
            **context_options,
        )
        if settings.stealth_mode:
            await self.context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for the page to settle."""

        page = self._require_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_load_state("networkidle", timeout=15_000)

    async def observe(self) -> PageState:
        """Return compressed page state: summary, interactive controls, and screenshot."""

        page = self._require_page()
        html = await page.content()
        title = await page.title()
        url = page.url
        summary, interactive_elements, text = self.compress_dom(html)
        screenshot_path = self.screenshots_dir / f"page-{abs(hash(url))}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)

        return PageState(
            url=url,
            title=title,
            summary=summary,
            interactive_elements=interactive_elements,
            screenshot_path=str(screenshot_path),
            captcha_detected=bool(CAPTCHA_PATTERNS.search(text)),
            raw_text_sample=text[:1000],
        )

    def compress_dom(self, html: str) -> tuple[str, list[InteractiveElement], str]:
        """Compress raw HTML into a 150-word summary and interactive elements."""

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(" ", strip=True)
        return self._summarize_text(text), self._extract_interactive_elements(soup), text

    async def execute(self, action: PlannerAction) -> dict[str, str]:
        """Execute one planner action with deterministic Playwright commands."""

        page = self._require_page()
        await asyncio.sleep(random.uniform(2, 5))
        filled: dict[str, str] = {}

        if action.action == "navigate":
            if not action.value:
                raise ValueError("navigate action requires value")
            await self.navigate(action.value)
        elif action.action == "click":
            await page.locator(self._require_selector(action)).first.click(timeout=10_000)
        elif action.action == "type":
            selector = self._require_selector(action)
            value = action.value or ""
            await page.locator(selector).first.fill(value, timeout=10_000)
            filled[selector] = value
        elif action.action == "upload":
            selector = self._require_selector(action)
            if not action.value:
                raise ValueError("upload action requires file path value")
            await page.locator(selector).first.set_input_files(action.value, timeout=10_000)
            filled[selector] = action.value
        elif action.action == "extract" or action.action == "done":
            return filled
        else:
            raise ValueError(f"Unsupported action: {action.action}")

        return filled

    @staticmethod
    async def fill_text(page: Page, selector: str, value: str) -> None:
        """Fill a text input by selector."""

        await page.locator(selector).first.fill(value)

    @staticmethod
    async def fill_dropdown_by_text(page: Page, selector: str, value: str) -> None:
        """Select a dropdown option by visible label."""

        await page.locator(selector).first.select_option(label=value)

    @staticmethod
    async def fill_checkbox(page: Page, selector: str, checked: bool = True) -> None:
        """Set a checkbox state."""

        locator = page.locator(selector).first
        if checked:
            await locator.check()
        else:
            await locator.uncheck()

    @staticmethod
    async def upload_file(page: Page, selector: str, path: str) -> None:
        """Upload a file into an input[type=file]."""

        await page.locator(selector).first.set_input_files(path)

    def _require_page(self) -> Page:
        if not self.page:
            raise RuntimeError("BrowserController is not started")
        return self.page

    @staticmethod
    def _require_selector(action: PlannerAction) -> str:
        if not action.selector:
            raise ValueError(f"{action.action} action requires selector")
        return action.selector

    @staticmethod
    def _summarize_text(text: str, max_words: int = 150) -> str:
        words = text.split()
        return " ".join(words[:max_words])

    def _extract_interactive_elements(self, soup: BeautifulSoup) -> list[InteractiveElement]:
        elements: list[InteractiveElement] = []
        for tag in soup.select("input, button, select, textarea, a[href]")[:120]:
            selector = self._best_selector(tag)
            if not selector:
                continue
            options = [option.get_text(" ", strip=True) for option in tag.select("option")]
            label = self._find_label(soup, tag)
            elements.append(
                InteractiveElement(
                    tag=tag.name or "",
                    selector=selector,
                    text=tag.get_text(" ", strip=True)[:200],
                    input_type=tag.get("type"),
                    name=tag.get("name"),
                    label=label,
                    placeholder=tag.get("placeholder"),
                    required=tag.has_attr("required") or tag.get("aria-required") == "true",
                    options=[option for option in options if option],
                )
            )
        return elements

    @staticmethod
    def _best_selector(tag: object) -> str | None:
        get = getattr(tag, "get", None)
        if not get:
            return None
        tag_name = getattr(tag, "name", None)
        if element_id := get("id"):
            return f"#{element_id}"
        if name := get("name"):
            return f'{tag_name}[name="{name}"]'
        if aria := get("aria-label"):
            return f'{tag_name}[aria-label="{aria}"]'
        if placeholder := get("placeholder"):
            return f'{tag_name}[placeholder="{placeholder}"]'
        return tag_name

    @staticmethod
    def _find_label(soup: BeautifulSoup, tag: object) -> str | None:
        get = getattr(tag, "get", None)
        if not get:
            return None
        if element_id := get("id"):
            label = soup.select_one(f'label[for="{element_id}"]')
            if label:
                return label.get_text(" ", strip=True)
        parent = getattr(tag, "parent", None)
        if parent and getattr(parent, "name", None) == "label":
            return parent.get_text(" ", strip=True)
        return None
