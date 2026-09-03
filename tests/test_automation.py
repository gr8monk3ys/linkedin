"""Browser config and pacing. Budgets are in test_budget.py, the session in test_session.py."""

import time

from linkedin.automation.config import AutomationConfig
from linkedin.automation.rate_limiter import MAX_DELAY_SECONDS, MIN_DELAY_SECONDS, RateLimiter


class TestAutomationConfig:
    def test_defaults(self):
        config = AutomationConfig()
        assert config.headless is False
        assert config.browser_type == "chromium"
        assert config.cookies_path == ""
        assert config.page_timeout_ms == 30000

    def test_only_fields_something_reads(self):
        """Caps, delays and dry_run were declared here and read by nothing."""
        assert set(AutomationConfig.__dataclass_fields__) == {"headless", "browser_type", "cookies_path", "page_timeout_ms"}


class TestRateLimiter:
    def test_delays_are_declared_once(self):
        assert RateLimiter().min_delay == MIN_DELAY_SECONDS
        assert RateLimiter().max_delay == MAX_DELAY_SECONDS

    def test_random_delay_in_range(self):
        limiter = RateLimiter(min_delay=0.01, max_delay=0.02)
        for _ in range(10):
            limiter.reset()
            assert 0.01 <= limiter.wait() <= 0.02

    def test_wait_returns_delay(self):
        limiter = RateLimiter(min_delay=0.01, max_delay=0.02)
        delay = limiter.wait()
        assert 0.01 <= delay <= 0.02

    def test_reset(self):
        limiter = RateLimiter(min_delay=0.01, max_delay=0.02)
        limiter.wait()
        assert limiter._last_action_time > 0
        limiter.reset()
        assert limiter._last_action_time == 0

    def test_consecutive_waits(self):
        limiter = RateLimiter(min_delay=0.01, max_delay=0.02)
        start = time.time()
        limiter.wait()
        limiter.wait()
        elapsed = time.time() - start
        # Should have waited at least min_delay for the second call
        assert elapsed >= 0.01


