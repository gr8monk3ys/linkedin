"""Browser configuration. Only fields something reads; pacing lives in rate_limiter, caps in budget."""

from dataclasses import dataclass


@dataclass
class AutomationConfig:
    headless: bool = False
    browser_type: str = "chromium"  # chromium, firefox, webkit
    cookies_path: str = ""  # storage state file; empty means no session restore
    page_timeout_ms: int = 30000
