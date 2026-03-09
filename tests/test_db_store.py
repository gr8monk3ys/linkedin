"""Tests for the database store implementation."""

import pytest
from sqlmodel import create_engine

from linkedin.data.db_store import (
    DbCompanyRepo,
    DbContactRepo,
    DbDraftRepo,
    DbProfileRepo,
    DbResearchRepo,
    DbTemplateRepo,
)
from linkedin.models.base import SQLModel, reset_engine


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()
    reset_engine()


@pytest.fixture
def contact_repo(engine):
    return DbContactRepo(engine)


@pytest.fixture
def company_repo(engine):
    return DbCompanyRepo(engine)


@pytest.fixture
def profile_repo(engine):
    return DbProfileRepo(engine)


@pytest.fixture
def draft_repo(engine):
    return DbDraftRepo(engine)


@pytest.fixture
def research_repo(engine):
    return DbResearchRepo(engine)


@pytest.fixture
def template_repo(engine):
    return DbTemplateRepo(engine)


class TestDbContactRepo:
    def test_add_and_get(self, contact_repo):
        contact = contact_repo.add({"name": "Alice Smith", "title": "Engineer", "company": "Acme"})
        assert contact["id"] is not None
        assert contact["name"] == "Alice Smith"

        fetched = contact_repo.get(contact["id"])
        assert fetched is not None
        assert fetched["name"] == "Alice Smith"
        assert fetched["title"] == "Engineer"
        assert fetched["company"] == "Acme"

    def test_list_all(self, contact_repo):
        contact_repo.add({"name": "Alice"})
        contact_repo.add({"name": "Bob"})
        contacts = contact_repo.list_all()
        assert len(contacts) == 2
        names = {c["name"] for c in contacts}
        assert names == {"Alice", "Bob"}

    def test_update(self, contact_repo):
        contact = contact_repo.add({"name": "Alice", "title": "Engineer"})
        contact_repo.update({"id": contact["id"], "title": "Senior Engineer"})
        updated = contact_repo.get(contact["id"])
        assert updated["title"] == "Senior Engineer"

    def test_delete(self, contact_repo):
        contact = contact_repo.add({"name": "Alice"})
        assert contact_repo.delete(contact["id"]) is True
        assert contact_repo.get(contact["id"]) is None

    def test_delete_nonexistent(self, contact_repo):
        assert contact_repo.delete(999) is False

    def test_get_nonexistent(self, contact_repo):
        assert contact_repo.get(999) is None

    def test_next_id(self, contact_repo):
        assert contact_repo.next_id() == 1
        contact_repo.add({"name": "Alice"})
        assert contact_repo.next_id() == 2

    def test_save_all(self, contact_repo):
        contacts = [
            {"name": "Alice", "title": "Engineer"},
            {"name": "Bob", "title": "Designer"},
        ]
        contact_repo.save_all(contacts)
        all_contacts = contact_repo.list_all()
        assert len(all_contacts) == 2

    def test_update_with_activities(self, contact_repo):
        contact = contact_repo.add({"name": "Alice"})
        contact_repo.update({
            "id": contact["id"],
            "activities": [
                {"date": "2024-01-15T10:00:00", "type": "connection_sent", "note": "Sent request"},
            ],
        })
        updated = contact_repo.get(contact["id"])
        assert len(updated["activities"]) == 1
        assert updated["activities"][0]["type"] == "connection_sent"

    def test_contact_defaults(self, contact_repo):
        contact = contact_repo.add({"name": "Alice"})
        fetched = contact_repo.get(contact["id"])
        assert fetched["status"] == "not_contacted"
        assert fetched["source"] == "linkedin_search"
        assert fetched["email"] == ""


class TestDbCompanyRepo:
    def test_add_and_get(self, company_repo):
        company = company_repo.add({"name": "Acme Corp", "industry": "Tech"})
        assert company["id"] is not None
        fetched = company_repo.get(company["id"])
        assert fetched["name"] == "Acme Corp"
        assert fetched["industry"] == "Tech"

    def test_list_all(self, company_repo):
        company_repo.add({"name": "Acme"})
        company_repo.add({"name": "Globex"})
        companies = company_repo.list_all()
        assert len(companies) == 2

    def test_update(self, company_repo):
        company = company_repo.add({"name": "Acme", "priority": "low"})
        company_repo.update({"id": company["id"], "priority": "high"})
        updated = company_repo.get(company["id"])
        assert updated["priority"] == "high"

    def test_update_key_people(self, company_repo):
        company = company_repo.add({"name": "Acme", "key_people_to_find": ["CTO", "VP Eng"]})
        fetched = company_repo.get(company["id"])
        assert fetched["key_people_to_find"] == ["CTO", "VP Eng"]

        company_repo.update({"id": company["id"], "key_people_to_find": ["CEO"]})
        updated = company_repo.get(company["id"])
        assert updated["key_people_to_find"] == ["CEO"]

    def test_delete(self, company_repo):
        company = company_repo.add({"name": "Acme"})
        assert company_repo.delete(company["id"]) is True
        assert company_repo.get(company["id"]) is None

    def test_delete_nonexistent(self, company_repo):
        assert company_repo.delete(999) is False

    def test_next_id(self, company_repo):
        assert company_repo.next_id() == 1
        company_repo.add({"name": "Acme"})
        assert company_repo.next_id() == 2

    def test_company_defaults(self, company_repo):
        company = company_repo.add({"name": "Acme"})
        fetched = company_repo.get(company["id"])
        assert fetched["size"] == "51-200"
        assert fetched["priority"] == "medium"
        assert fetched["key_people_to_find"] == []


class TestDbProfileRepo:
    def test_get_empty(self, profile_repo):
        profile = profile_repo.get()
        assert profile == {}

    def test_save_and_get(self, profile_repo):
        profile_repo.save({
            "name": "Test User",
            "headline": "Software Engineer",
            "target_role": "Senior Engineer",
            "skills": "Python, SQL",
        })
        profile = profile_repo.get()
        assert profile["name"] == "Test User"
        assert profile["headline"] == "Software Engineer"
        assert profile["target_role"] == "Senior Engineer"

    def test_save_updates_existing(self, profile_repo):
        profile_repo.save({"name": "User 1"})
        profile_repo.save({"name": "User 2"})
        profile = profile_repo.get()
        assert profile["name"] == "User 2"


class TestDbDraftRepo:
    def test_add_and_get(self, draft_repo):
        draft = draft_repo.add({"contact_id": 1, "type": "connection", "content": "Hello!"})
        assert draft["id"] is not None
        fetched = draft_repo.get(draft["id"])
        assert fetched["content"] == "Hello!"
        assert fetched["type"] == "connection"

    def test_list_all(self, draft_repo):
        draft_repo.add({"type": "connection", "content": "Hi"})
        draft_repo.add({"type": "message", "content": "Hey"})
        drafts = draft_repo.list_all()
        assert len(drafts) == 2

    def test_next_id(self, draft_repo):
        assert draft_repo.next_id() == 1
        draft_repo.add({"type": "connection", "content": "Hi"})
        assert draft_repo.next_id() == 2

    def test_draft_with_topic(self, draft_repo):
        draft = draft_repo.add({"type": "post", "content": "Great article", "topic": "AI"})
        fetched = draft_repo.get(draft["id"])
        assert fetched["topic"] == "AI"

    def test_draft_with_target_contact(self, draft_repo):
        draft = draft_repo.add({"type": "intro", "content": "Can you intro me?", "contact_id": 1, "target_contact_id": 2})
        fetched = draft_repo.get(draft["id"])
        assert fetched["target_contact_id"] == 2

    def test_get_nonexistent(self, draft_repo):
        assert draft_repo.get(999) is None


class TestDbResearchRepo:
    def test_get_default(self, research_repo):
        data = research_repo.get()
        assert data == {"ideas": []}

    def test_save_and_get(self, research_repo):
        research_repo.save({"ideas": ["Idea 1", "Idea 2"], "hashtags": ["#python"]})
        data = research_repo.get()
        assert data["ideas"] == ["Idea 1", "Idea 2"]
        assert data["hashtags"] == ["#python"]

    def test_save_overwrites(self, research_repo):
        research_repo.save({"ideas": ["Old"]})
        research_repo.save({"ideas": ["New"]})
        data = research_repo.get()
        assert data["ideas"] == ["New"]


class TestDbTemplateRepo:
    def test_add_and_get(self, template_repo):
        template = template_repo.add({"name": "Intro", "template_type": "connection", "content": "Hi"})
        assert template["id"] is not None
        fetched = template_repo.get(template["id"])
        assert fetched["name"] == "Intro"

    def test_update(self, template_repo):
        template = template_repo.add({"name": "Intro", "template_type": "connection", "content": "Hi"})
        template_repo.update({"id": template["id"], "usage_count": 3, "response_count": 1})
        fetched = template_repo.get(template["id"])
        assert fetched["usage_count"] == 3
        assert fetched["response_count"] == 1
