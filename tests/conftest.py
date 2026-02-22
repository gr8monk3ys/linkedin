"""Shared test fixtures."""

import pytest
from sqlmodel import create_engine

from linkedin.data.db_store import (
    DbCompanyRepo,
    DbContactRepo,
    DbDraftRepo,
    DbProfileRepo,
    DbResearchRepo,
)
from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonCalendarRepo,
    JsonCompanyRepo,
    JsonContactRepo,
    JsonConversationRepo,
    JsonDraftRepo,
    JsonInterviewPrepRepo,
    JsonProfileRepo,
    JsonResearchRepo,
)
from linkedin.models.base import SQLModel, reset_engine


@pytest.fixture
def db_engine():
    """In-memory SQLite engine for testing."""
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    yield eng
    reset_engine()


@pytest.fixture
def db_repos(db_engine):
    """Full set of DB repos (new repos fall back to JSON stubs matching factory.py)."""
    from linkedin.data.json_store import (
        JsonApplicationRepo,
        JsonCalendarRepo,
        JsonConversationRepo,
        JsonInterviewPrepRepo,
    )
    return (
        DbContactRepo(db_engine),
        DbCompanyRepo(db_engine),
        DbProfileRepo(db_engine),
        DbDraftRepo(db_engine),
        DbResearchRepo(db_engine),
        JsonApplicationRepo(),
        JsonConversationRepo(),
        JsonCalendarRepo(),
        JsonInterviewPrepRepo(),
    )


@pytest.fixture
def json_repos(tmp_path, monkeypatch):
    """Full set of JSON repos using temp directory."""
    import linkedin.data.json_store as js

    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    monkeypatch.setattr(js, "DRAFTS_FILE", tmp_path / "drafts.json")
    monkeypatch.setattr(js, "RESEARCH_FILE", tmp_path / "research.json")
    monkeypatch.setattr(js, "TEMPLATES_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(js, "JOB_POSTINGS_FILE", tmp_path / "job_postings.json")
    monkeypatch.setattr(js, "RUN_DAILY_STATE_FILE", tmp_path / "run_daily_state.json")
    monkeypatch.setattr(js, "RUN_DAILY_LOG_FILE", tmp_path / "run_daily.log.jsonl")
    monkeypatch.setattr(js, "RUN_DAILY_LOCK_FILE", tmp_path / "run_daily.lock")
    monkeypatch.setattr(js, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")
    monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")

    return (
        JsonContactRepo(),
        JsonCompanyRepo(),
        JsonProfileRepo(),
        JsonDraftRepo(),
        JsonResearchRepo(),
        JsonApplicationRepo(),
        JsonConversationRepo(),
        JsonCalendarRepo(),
        JsonInterviewPrepRepo(),
    )


def sample_contact(**overrides):
    """Factory for sample contact dicts."""
    defaults = {
        "name": "Test User",
        "title": "Engineer",
        "company": "TestCo",
        "linkedin_url": "https://linkedin.com/in/testuser",
        "notes": "Met at conference",
        "status": "not_contacted",
        "source": "linkedin_search",
    }
    defaults.update(overrides)
    return defaults


def sample_company(**overrides):
    """Factory for sample company dicts."""
    defaults = {
        "name": "TestCo",
        "industry": "Tech",
        "size": "51-200",
        "priority": "medium",
    }
    defaults.update(overrides)
    return defaults


def sample_profile(**overrides):
    """Factory for sample profile dicts."""
    defaults = {
        "name": "Test User",
        "headline": "Software Engineer",
        "target_role": "Senior Software Engineer",
        "skills": "Python, JavaScript, SQL",
        "experience_summary": "5 years building web apps",
        "unique_value": "Full-stack with ML experience",
        "industries": "Technology, SaaS",
        "location": "San Francisco, CA",
        "resume_text": "Experienced software engineer with 5 years building scalable web apps.",
    }
    defaults.update(overrides)
    return defaults


def sample_application(**overrides):
    """Factory for sample application dicts."""
    defaults = {
        "company": "Acme Corp",
        "title": "ML Engineer",
        "url": "https://acme.com/jobs/123",
        "jd_text": "We need Python, ML, and 3+ years experience.",
        "status": "saved",
        "notes": "",
        "history": [],
    }
    defaults.update(overrides)
    return defaults


def sample_content_post(**overrides):
    """Factory for sample content post dicts."""
    defaults = {
        "title": "Why I love Python",
        "scheduled_date": "2026-03-01",
        "status": "scheduled",
        "platform": "linkedin",
    }
    defaults.update(overrides)
    return defaults
