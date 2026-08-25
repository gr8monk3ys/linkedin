"""Browser management with Playwright."""

import json
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from linkedin.automation.config import AutomationConfig


class BrowserManager:
    """Manages Playwright browser lifecycle and session persistence."""

    def __init__(self, config: AutomationConfig | None = None):
        self.config = config or AutomationConfig()
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def start(self) -> Page:
        """Launch browser and return the main page."""
        self._playwright = sync_playwright().start()

        launcher = getattr(self._playwright, self.config.browser_type)
        self._browser = launcher.launch(headless=self.config.headless)

        context_kwargs = {
            "viewport": {"width": 1280, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        if self.config.cookies_path:
            storage_state = self._load_storage_state()
            if storage_state:
                context_kwargs["storage_state"] = storage_state

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(self.config.page_timeout_ms)
        self._page = self._context.new_page()
        return self._page

    @property
    def page(self) -> Page | None:
        return self._page

    def save_session(self) -> None:
        """Save cookies and storage state for session persistence."""
        if not self._context or not self.config.cookies_path:
            return
        state = self._context.storage_state()
        path = Path(self.config.cookies_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def _load_storage_state(self) -> dict | None:
        """Load saved storage state if available."""
        if not self.config.cookies_path:
            return None
        path = Path(self.config.cookies_path)
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def close(self) -> None:
        """Close browser and clean up."""
        if self.config.cookies_path:
            self.save_session()
        if self._page:
            self._page.close()
            self._page = None
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()
