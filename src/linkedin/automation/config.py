"""Automation configuration."""

from dataclasses import dataclass, field


@dataclass
class AutomationConfig:
    """Configuration for LinkedIn automation."""

    # Browser settings
    headless: bool = False
    browser_type: str = "chromium"  # chromium, firefox, webkit
    user_data_dir: str = ""  # Path for persistent browser session

    # Rate limiting
    max_connections_per_day: int = 20
    max_messages_per_day: int = 25
    min_delay_seconds: float = 3.0
    max_delay_seconds: float = 8.0
    max_session_minutes: int = 30

    # Safety
    dry_run: bool = False  # Log actions without executing

    # Session persistence
    cookies_path: str = ""  # Path to save/load cookies

    # Page timeouts
    page_timeout_ms: int = 30000
    action_timeout_ms: int = 10000
