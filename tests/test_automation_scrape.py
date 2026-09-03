"""Tests for LinkedIn scraping actions."""

from unittest.mock import MagicMock

import pytest

from linkedin.automation.actions.scrape import (
    _parse_headline,
    import_search_results,
    scrape_and_import_profile,
    search_and_collect,
)
from linkedin.data.json_store import JsonContactRepo


@pytest.fixture
def contact_repo(tmp_path, monkeypatch):
    return JsonContactRepo(tmp_path / "contacts.json")


def test_parse_headline_at():
    title, company = _parse_headline("ML Engineer at Stripe")
    assert title == "ML Engineer"
    assert company == "Stripe"


def test_parse_headline_at_symbol():
    title, company = _parse_headline("Data Scientist @ Google")
    assert title == "Data Scientist"
    assert company == "Google"


def test_parse_headline_no_separator():
    title, company = _parse_headline("Freelance Developer")
    assert title == "Freelance Developer"
    assert company == ""


def test_import_search_results(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob Jones", "headline": "Data Engineer at Google", "linkedin_url": "https://linkedin.com/in/bob"},
    ]
    added, skipped = import_search_results(results, contact_repo)
    assert len(added) == 2
    assert len(skipped) == 0
    contacts = contact_repo.list_all()
    assert len(contacts) == 2
    assert contacts[0]["name"] == "Alice Smith"
    assert contacts[0]["company"] == "Stripe"
    assert contacts[0]["source"] == "linkedin_search"


def test_import_search_results_skips_duplicates(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
    ]
    import_search_results(results, contact_repo)
    added, skipped = import_search_results(results, contact_repo)
    assert len(added) == 0
    assert len(skipped) == 1
    assert len(contact_repo.list_all()) == 1  # No duplicates


def test_import_search_results_no_skip(contact_repo):
    results = [{"name": "Alice", "headline": "Engineer at Acme", "linkedin_url": "https://linkedin.com/in/alice"}]
    import_search_results(results, contact_repo)
    added, skipped = import_search_results(results, contact_repo, skip_existing_urls=False)
    assert len(added) == 1
    assert len(contact_repo.list_all()) == 2


def test_search_and_collect_calls_linkedin_page():
    mock_page = MagicMock()
    mock_page.get_search_results.return_value = [
        {"name": "Alice", "headline": "Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "headline": "PM at Meta", "linkedin_url": "https://linkedin.com/in/bob"},
    ]
    results = search_and_collect(mock_page, "ML Engineer", limit=1)
    assert len(results) == 1
    mock_page.goto_search.assert_called_once_with("ML Engineer")


def test_scrape_and_import_profile_creates_contact(contact_repo):
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {
        "name": "Jane Doe",
        "headline": "Senior ML Engineer at OpenAI",
        "location": "San Francisco, CA",
        "about": "Building AI systems.",
    }
    url = "https://linkedin.com/in/janedoe"
    contact = scrape_and_import_profile(mock_page, url, contact_repo)
    assert contact is not None
    assert contact["name"] == "Jane Doe"
    assert contact["title"] == "Senior ML Engineer"
    assert contact["company"] == "OpenAI"
    assert contact["source"] == "linkedin_scrape"


def test_scrape_and_import_profile_updates_existing(contact_repo):
    contact_repo.add({
        "id": 1,
        "name": "Jane Doe",
        "title": "ML Engineer",
        "company": "Old Co",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "status": "connected",
        "activities": [],
    })
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {
        "name": "Jane Doe",
        "headline": "Senior ML Engineer at OpenAI",
    }
    contact = scrape_and_import_profile(mock_page, "https://linkedin.com/in/janedoe", contact_repo)
    assert contact is not None
    assert contact["company"] == "OpenAI"
    assert len(contact_repo.list_all()) == 1  # Not duplicated


def test_scrape_returns_none_on_empty_name(contact_repo):
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {}  # No name
    contact = scrape_and_import_profile(mock_page, "https://linkedin.com/in/nobody", contact_repo)
    assert contact is None


def test_imported_contacts_are_seeded_with_a_follow_up_date(contact_repo):
    """A contact the planner cannot schedule reads to `run-daily` as a stalled planner."""
    results = [{"name": "Alice", "headline": "ML Engineer at Acme", "linkedin_url": "u/1"}]
    added, _ = import_search_results(results, contact_repo)
    assert added[0]["follow_up_date"] is not None


def test_scraped_profile_is_seeded_with_a_follow_up_date(contact_repo):
    page = MagicMock()
    page.get_profile_data.return_value = {"name": "Bob", "headline": "MLE at Acme", "about": ""}
    contact = scrape_and_import_profile(page, "u/2", contact_repo)
    assert contact["follow_up_date"] is not None
