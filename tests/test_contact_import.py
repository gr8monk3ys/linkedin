"""Importing what the browser read: search rows and scraped profiles become contacts."""

import pytest

from linkedin.data.json_store import JsonContactRepo
from linkedin.services.contact_service import import_scraped_profile, import_search_results, parse_headline


@pytest.fixture
def contact_repo(tmp_path):
    return JsonContactRepo(tmp_path / "contacts.json")


@pytest.mark.parametrize(
    "headline, expected",
    [
        ("ML Engineer at Stripe", ("ML Engineer", "Stripe")),
        ("Data Scientist @ Google", ("Data Scientist", "Google")),
        ("Freelance Developer", ("Freelance Developer", "")),
    ],
)
def test_parse_headline(headline, expected):
    assert parse_headline(headline) == expected


def test_import_search_results(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob Jones", "headline": "Data Engineer at Google", "linkedin_url": "https://linkedin.com/in/bob"},
    ]
    added, skipped = import_search_results(results, contact_repo)
    assert len(added) == 2 and skipped == []
    contacts = contact_repo.list_all()
    assert contacts[0]["name"] == "Alice Smith"
    assert contacts[0]["company"] == "Stripe"
    assert contacts[0]["source"] == "linkedin_search"


def test_import_search_results_skips_duplicates(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"}
    ]
    import_search_results(results, contact_repo)
    added, skipped = import_search_results(results, contact_repo)
    assert added == [] and skipped == ["https://linkedin.com/in/alice"]
    assert len(contact_repo.list_all()) == 1


def test_import_search_results_no_skip(contact_repo):
    results = [{"name": "Alice", "headline": "Engineer at Acme", "linkedin_url": "https://linkedin.com/in/alice"}]
    import_search_results(results, contact_repo)
    added, _ = import_search_results(results, contact_repo, skip_existing_urls=False)
    assert len(added) == 1
    assert len(contact_repo.list_all()) == 2


def test_imported_contacts_are_seeded_with_a_follow_up_date(contact_repo):
    """A contact the planner cannot schedule reads to `run-daily` as a stalled planner."""
    added, _ = import_search_results(
        [{"name": "Alice", "headline": "ML Engineer at Acme", "linkedin_url": "u/1"}], contact_repo
    )
    assert added[0]["follow_up_date"] is not None


def test_scraped_profile_creates_contact(contact_repo):
    data = {
        "name": "Jane Doe",
        "headline": "Senior ML Engineer at OpenAI",
        "location": "SF",
        "about": "Building AI systems.",
    }
    contact = import_scraped_profile(data, "https://linkedin.com/in/janedoe", contact_repo)
    assert contact["title"] == "Senior ML Engineer"
    assert contact["company"] == "OpenAI"
    assert contact["source"] == "linkedin_scrape"
    assert contact["follow_up_date"] is not None


def test_scraped_profile_updates_existing(contact_repo):
    contact_repo.add(
        {
            "id": 1,
            "name": "Jane Doe",
            "title": "ML Engineer",
            "company": "Old Co",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "status": "connected",
            "activities": [],
        }
    )
    contact = import_scraped_profile(
        {"name": "Jane Doe", "headline": "Senior ML Engineer at OpenAI"},
        "https://linkedin.com/in/janedoe",
        contact_repo,
    )
    assert contact["company"] == "OpenAI"
    assert len(contact_repo.list_all()) == 1


def test_scraped_profile_without_a_name_is_nothing(contact_repo):
    assert import_scraped_profile({}, "https://linkedin.com/in/nobody", contact_repo) is None
    assert contact_repo.list_all() == []
