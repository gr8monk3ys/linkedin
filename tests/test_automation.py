"""Tests for automation module (rate limiter, safety, config)."""

import time

from linkedin.automation.config import AutomationConfig
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import (
    MAX_CONNECTIONS_PER_DAY,
    MAX_MESSAGES_PER_DAY,
    SafetyLimits,
)


class TestAutomationConfig:
    def test_defaults(self):
        config = AutomationConfig()
        assert config.headless is False
        assert config.browser_type == "chromium"
        assert config.max_connections_per_day == 20
        assert config.max_messages_per_day == 25
        assert config.min_delay_seconds == 3.0
        assert config.max_delay_seconds == 8.0
        assert config.max_session_minutes == 30
        assert config.dry_run is False

    def test_custom_config(self):
        config = AutomationConfig(
            headless=True,
            browser_type="firefox",
            max_connections_per_day=10,
            dry_run=True,
        )
        assert config.headless is True
        assert config.browser_type == "firefox"
        assert config.max_connections_per_day == 10
        assert config.dry_run is True


class TestRateLimiter:
    def test_random_delay_in_range(self):
        limiter = RateLimiter(min_delay=0.01, max_delay=0.02)
        for _ in range(10):
            delay = limiter._random_delay()
            assert 0.01 <= delay <= 0.02

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


class TestSafetyLimits:
    def test_initial_state(self):
        safety = SafetyLimits()
        assert safety.connections_sent == 0
        assert safety.messages_sent == 0
        assert safety.can_send_connection() is True
        assert safety.can_send_message() is True

    def test_connection_limit(self):
        safety = SafetyLimits()
        for _ in range(MAX_CONNECTIONS_PER_DAY):
            assert safety.can_send_connection() is True
            safety.record_connection()
        assert safety.can_send_connection() is False
        assert safety.remaining_connections() == 0

    def test_message_limit(self):
        safety = SafetyLimits()
        for _ in range(MAX_MESSAGES_PER_DAY):
            assert safety.can_send_message() is True
            safety.record_message()
        assert safety.can_send_message() is False
        assert safety.remaining_messages() == 0

    def test_summary(self):
        safety = SafetyLimits()
        safety.record_connection()
        safety.record_connection()
        safety.record_message()
        summary = safety.summary()
        assert summary["connections_sent"] == 2
        assert summary["connections_remaining"] == MAX_CONNECTIONS_PER_DAY - 2
        assert summary["messages_sent"] == 1
        assert summary["messages_remaining"] == MAX_MESSAGES_PER_DAY - 1

    def test_profile_view_limit(self):
        safety = SafetyLimits()
        assert safety.can_view_profile() is True
        for _ in range(50):
            safety.record_profile_view()
        assert safety.can_view_profile() is False

    def test_search_limit(self):
        safety = SafetyLimits()
        assert safety.can_search() is True
        for _ in range(30):
            safety.record_search()
        assert safety.can_search() is False
