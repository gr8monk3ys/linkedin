"""Shared test fixtures."""

import pytest

from linkedin.data.factory import create_repos
from linkedin.data.paths import DataDir


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch) -> DataDir:
    """Every test runs against its own data directory.

    One env var and one reset replace the twenty-two monkeypatches that used
    to be copy-pasted per file — and had drifted, so nine daily-plan tests were
    reading the developer's real applications file.
    """
    root = tmp_path / ".linkedin-cli"
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(root))
    # The resume bridge falls back to ~/code/resume on this machine; a test must never see it.
    from linkedin.services import resume_service

    monkeypatch.setattr(resume_service, "DEFAULT_RESUME_REPO", tmp_path / "no-resume-repo")
    from linkedin.cli import _app

    _app.reset()
    yield DataDir(root)
    _app.reset()


@pytest.fixture
def fake_session(monkeypatch):
    """A FakeSession installed as what `LinkedInSession.open` yields."""
    from tests.fake_session import FakeSession, install

    return install(monkeypatch, FakeSession())


@pytest.fixture
def json_repos(tmp_path):
    """Full set of JSON repos over a temp directory, in factory order."""
    return create_repos(DataDir(tmp_path)).as_tuple()


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
