"""Tests for the connect / message / search actions.

These were at 0-33% coverage. They are the actions that consume the daily
safety budget, so the invariant worth pinning is that a refused or failed
action never spends budget — and a dry run never touches the browser.
"""

from unittest.mock import MagicMock

from linkedin.automation.actions.connect import batch_connect, send_connection
from linkedin.automation.actions.message import send_message
from linkedin.automation.actions.search import search_people
from linkedin.automation.safety import (
    MAX_CONNECTIONS_PER_DAY,
    MAX_MESSAGES_PER_DAY,
    MAX_SEARCHES_PER_DAY,
    SafetyLimits,
)


class TestSendConnection:
    def test_sends_and_records(self):
        page = MagicMock()
        page.send_connection_request.return_value = True
        safety = SafetyLimits()

        assert send_connection(page, "https://in/ada", note="hi", safety=safety) is True
        page.goto_profile.assert_called_once_with("https://in/ada")
        page.send_connection_request.assert_called_once_with(note="hi")
        assert safety.connections_sent == 1

    def test_failed_request_does_not_spend_budget(self):
        page = MagicMock()
        page.send_connection_request.return_value = False
        safety = SafetyLimits()

        assert send_connection(page, "https://in/ada", safety=safety) is False
        assert safety.connections_sent == 0

    def test_budget_exhaustion_short_circuits_before_navigating(self):
        page = MagicMock()
        safety = SafetyLimits(connections_sent=MAX_CONNECTIONS_PER_DAY)

        assert send_connection(page, "https://in/ada", safety=safety) is False
        page.goto_profile.assert_not_called()

    def test_dry_run_navigates_but_never_clicks(self):
        page = MagicMock()
        safety = SafetyLimits()

        assert send_connection(page, "https://in/ada", safety=safety, dry_run=True) is True
        page.send_connection_request.assert_not_called()
        assert safety.connections_sent == 1, "a dry run still consumes budget, to model the real run"

    def test_rate_limiter_waits_before_acting(self):
        limiter = MagicMock()
        page = MagicMock()
        page.send_connection_request.return_value = True

        send_connection(page, "https://in/ada", rate_limiter=limiter)
        limiter.wait.assert_called_once()


class TestBatchConnect:
    def _profiles(self, n):
        return [{"linkedin_url": f"https://in/{i}", "connection_note": f"note {i}"} for i in range(n)]

    def test_respects_the_limit(self):
        page = MagicMock()
        page.send_connection_request.return_value = True
        results = batch_connect(page, self._profiles(10), limit=3)
        assert len(results) == 3

    def test_profiles_without_a_url_are_reported_not_skipped_silently(self):
        page = MagicMock()
        page.send_connection_request.return_value = True
        results = batch_connect(page, [{"name": "Ada"}, *self._profiles(1)], limit=5)
        assert results[0] == {"profile": {"name": "Ada"}, "success": False, "reason": "no_url"}
        assert results[1]["success"] is True

    def test_stops_when_the_daily_budget_runs_out(self):
        page = MagicMock()
        page.send_connection_request.return_value = True
        safety = SafetyLimits(connections_sent=MAX_CONNECTIONS_PER_DAY - 2)

        results = batch_connect(page, self._profiles(10), safety=safety, limit=10)
        assert len(results) == 2
        assert safety.connections_sent == MAX_CONNECTIONS_PER_DAY

    def test_passes_the_per_profile_note_through(self):
        page = MagicMock()
        page.send_connection_request.return_value = True
        batch_connect(page, self._profiles(1))
        page.send_connection_request.assert_called_once_with(note="note 0")


class TestSendMessage:
    def test_sends_and_records(self):
        page = MagicMock()
        page.send_message.return_value = True
        safety = SafetyLimits()

        assert send_message(page, "https://in/ada", "hello", safety=safety) is True
        page.goto_profile.assert_called_once_with("https://in/ada")
        page.send_message.assert_called_once_with("hello")
        assert safety.messages_sent == 1

    def test_failed_send_does_not_spend_budget(self):
        page = MagicMock()
        page.send_message.return_value = False
        safety = SafetyLimits()

        assert send_message(page, "https://in/ada", "hello", safety=safety) is False
        assert safety.messages_sent == 0

    def test_budget_exhaustion_short_circuits(self):
        page = MagicMock()
        safety = SafetyLimits(messages_sent=MAX_MESSAGES_PER_DAY)

        assert send_message(page, "https://in/ada", "hello", safety=safety) is False
        page.goto_profile.assert_not_called()

    def test_dry_run_never_sends(self):
        page = MagicMock()
        assert send_message(page, "https://in/ada", "hello", dry_run=True) is True
        page.send_message.assert_not_called()


class TestSearchPeople:
    def test_returns_results_and_records_the_search(self):
        page = MagicMock()
        page.get_search_results.return_value = [{"name": "Ada"}]
        safety = SafetyLimits()

        assert search_people(page, "ml engineer", network="S", safety=safety) == [{"name": "Ada"}]
        page.goto_search.assert_called_once_with("ml engineer", network="S")
        assert safety.searches == 1

    def test_budget_exhaustion_returns_empty_without_searching(self):
        page = MagicMock()
        safety = SafetyLimits(searches=MAX_SEARCHES_PER_DAY)

        assert search_people(page, "ml", safety=safety) == []
        page.goto_search.assert_not_called()

    def test_rate_limiter_waits_before_searching(self):
        limiter = MagicMock()
        page = MagicMock()
        page.get_search_results.return_value = []

        search_people(page, "ml", rate_limiter=limiter)
        limiter.wait.assert_called_once()
