"""Shared test fixtures."""

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
from linkedin.data.json_store import (
    JsonCompanyRepo,
    JsonContactRepo,
    JsonDraftRepo,
    JsonProfileRepo,
    JsonResearchRepo,
    JsonTemplateRepo,
)
from linkedin.data.twenty_client import TwentyClient
from linkedin.data.twenty_store import TwentyCompanyRepo, TwentyContactRepo, TwentyDraftRepo, _IdMapper
from linkedin.models.base import SQLModel, reset_engine


@pytest.fixture
def db_engine():
    """In-memory SQLite engine for testing."""
    eng = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()
    reset_engine()


@pytest.fixture
def db_repos(db_engine):
    """Full set of DB repos."""
    return (
        DbContactRepo(db_engine),
        DbCompanyRepo(db_engine),
        DbProfileRepo(db_engine),
        DbDraftRepo(db_engine),
        DbResearchRepo(db_engine),
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
    monkeypatch.setattr(js, "TEMPLATES_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(js, "RESEARCH_FILE", tmp_path / "research.json")
    monkeypatch.setattr(js, "BACKUPS_DIR", tmp_path / "backups")

    return (
        JsonContactRepo(),
        JsonCompanyRepo(),
        JsonProfileRepo(),
        JsonDraftRepo(),
        JsonResearchRepo(),
    )


@pytest.fixture
def twenty_repos(tmp_path):
    """Full set of Twenty repos with mocked client."""
    client = TwentyClient(base_url="http://test:3000", api_key="test-key")
    mapper = _IdMapper(tmp_path / "twenty_id_map.json")
    return (
        TwentyContactRepo(client, mapper),
        TwentyCompanyRepo(client, mapper),
        TwentyDraftRepo(client, mapper),
        client,
        mapper,
    )


@pytest.fixture
def db_template_repo(db_engine):
    """DB template repo using the shared in-memory engine."""
    return DbTemplateRepo(db_engine)


@pytest.fixture
def json_template_repo(json_repos):
    """JSON template repo using the patched temp directory."""
    return JsonTemplateRepo()


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
    }
    defaults.update(overrides)
    return defaults
