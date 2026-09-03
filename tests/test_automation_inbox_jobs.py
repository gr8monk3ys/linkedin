"""Tests for the read-only automation actions: inbox sync and job search.

Both actions are read-only — they never write to LinkedIn — which is what makes
them safe as the first real execution of this automation stack.
"""

from unittest.mock import MagicMock

import pytest

from linkedin.automation.actions.inbox import read_inbox
from linkedin.automation.actions.jobs import import_job_results, search_jobs
from linkedin.automation.safety import SafetyLimits
from linkedin.data.json_store import JsonProfileRepo
from linkedin.services.market_service import MarketService


@pytest.fixture
def market(tmp_path):
    return MarketService(JsonProfileRepo(tmp_path / "profile.json"), tmp_path / "job_postings.json")


# --- Inbox -------------------------------------------------------------------


def test_read_inbox_visits_both_surfaces():
    page = MagicMock()
    page.get_message_threads.return_value = [{"name": "Ryan"}]
    page.get_pending_sent_invitations.return_value = [{"name": "Andy"}]

    result = read_inbox(page)

    page.goto_messaging.assert_called_once()
    page.goto_sent_invitations.assert_called_once()
    assert result["threads"] == [{"name": "Ryan"}]
    assert result["pending_invitations"] == [{"name": "Andy"}]


def test_read_inbox_preserves_none_for_unreadable_invitations():
    """None must survive the action layer — [] here would mean 'all accepted'."""
    page = MagicMock()
    page.get_message_threads.return_value = []
    page.get_pending_sent_invitations.return_value = None

    assert read_inbox(page)["pending_invitations"] is None


def test_read_inbox_respects_the_search_budget():
    page = MagicMock()
    safety = SafetyLimits(searches=999)

    result = read_inbox(page, safety=safety)

    page.goto_messaging.assert_not_called()
    assert result["threads"] == []
    assert result["pending_invitations"] is None


def test_read_inbox_rate_limits():
    page = MagicMock()
    page.get_message_threads.return_value = []
    page.get_pending_sent_invitations.return_value = []
    limiter = MagicMock()

    read_inbox(page, rate_limiter=limiter)
    assert limiter.wait.called


# --- Jobs --------------------------------------------------------------------


def test_search_jobs_navigates_and_passes_the_limit_down():
    """The page object owns the cap — `get_job_results` takes a limit, unlike
    `get_search_results`, so slicing again here would be dead code."""
    page = MagicMock()
    page.get_job_results.return_value = [{"title": "Role"}]

    results = search_jobs(page, "ML Engineer", location="Los Angeles", limit=3)

    page.goto_job_search.assert_called_once_with("ML Engineer", location="Los Angeles")
    page.get_job_results.assert_called_once_with(limit=3)
    assert results == [{"title": "Role"}]


def test_search_jobs_respects_the_search_budget():
    page = MagicMock()
    safety = SafetyLimits(searches=999)
    assert search_jobs(page, "ML Engineer", safety=safety) == []
    page.goto_job_search.assert_not_called()


def test_import_job_results_scores_against_the_profile(market):
    market.profiles.save({"target_role": "ML Engineer", "skills": "Python, SQL"})
    results = [{
        "title": "ML Engineer",
        "company": "Netflix",
        "location": "Los Angeles",
        "url": "https://www.linkedin.com/jobs/view/1",
        "easy_apply": True,
    }]

    added, skipped = import_job_results(results, market)

    assert len(added) == 1
    assert skipped == 0
    stored = market.list_postings()
    assert stored[0]["company"] == "Netflix"
    assert stored[0]["source"] == "linkedin_jobs"
    assert stored[0]["match_score"] > 0


def test_import_job_results_dedupes_on_url(market):
    results = [{"title": "ML Engineer", "company": "Netflix", "url": "https://x/jobs/view/1"}]
    import_job_results(results, market)
    added, skipped = import_job_results(results, market)

    assert added == []
    assert skipped == 1
    assert len(market.list_postings()) == 1


def test_import_job_results_dedupes_on_company_and_title_without_a_url(market):
    results = [{"title": "ML Engineer", "company": "Netflix", "url": ""}]
    import_job_results(results, market)
    added, skipped = import_job_results(results, market)

    assert added == []
    assert skipped == 1


def test_import_job_results_skips_rows_with_no_title(market):
    added, skipped = import_job_results([{"title": "", "company": "Netflix"}], market)
    assert added == []
    assert skipped == 1
