"""Tests for InterviewService."""

import pytest

from linkedin.ai.client import AIClientError
from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonInterviewPrepRepo,
    JsonProfileRepo,
)
from linkedin.services.interview_service import InterviewService
from tests.conftest import sample_profile


def _raise_ai_error(*args, **kwargs):
    raise AIClientError("API error")


@pytest.fixture
def interview_repos(tmp_path, monkeypatch):
    return JsonApplicationRepo(tmp_path / "applications.json"), JsonInterviewPrepRepo(tmp_path / "interview_prep.json"), JsonProfileRepo(tmp_path / "profile.json")


@pytest.fixture
def svc(interview_repos):
    app_repo, prep_repo, profile_repo = interview_repos
    return InterviewService(app_repo, prep_repo, profile_repo)


@pytest.fixture
def app_with_jd(interview_repos):
    app_repo, _, _ = interview_repos
    app = {
        "id": 1,
        "company": "Acme",
        "title": "ML Engineer",
        "jd_text": "We need Python, ML, Kubernetes. Strong communication required.",
        "status": "phone_screen",
        "history": [],
    }
    app_repo.add(app)
    return app


def test_prep_no_application(svc):
    error, _ = svc.prep(999)
    assert error is not None
    assert "not found" in error.lower()


def test_prep_generates_questions(svc, app_with_jd, interview_repos, monkeypatch):
    _, _, profile_repo = interview_repos
    profile_repo.save(sample_profile())
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=1200: "1. Tell me about your ML experience.\n2. How do you handle ambiguity?\n3. Describe a difficult technical challenge.",
    )
    error, result = svc.prep(1)
    assert error is None
    assert len(result) > 0
    # Verify it was saved
    prep = svc.get_prep(1)
    assert prep is not None


def test_research_generates_briefing(svc, app_with_jd, monkeypatch):
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=800: "Acme Corp: Founded 2015, Series B, 200 employees. Known for ML infra.",
    )
    error, result = svc.research(1)
    assert error is None
    assert "Acme" in result


def test_star_generates_answers(svc, app_with_jd, interview_repos, monkeypatch):
    _, _, profile_repo = interview_repos
    profile_repo.save(sample_profile())
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=1000: "STAR Answer 1:\nSituation: ...\nTask: ...\nAction: ...\nResult: ...",
    )
    error, result = svc.star(1)
    assert error is None
    assert len(result) > 0


def test_questions_to_ask(svc, app_with_jd, monkeypatch):
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=400: "1. What does the ML infrastructure look like?\n2. How do you measure success?",
    )
    error, result = svc.questions_to_ask(1)
    assert error is None
    assert "?" in result or len(result) > 0


def test_get_prep_none_when_missing(svc, app_with_jd):
    prep = svc.get_prep(1)
    assert prep is None


def test_research_missing_application(svc):
    """research() should return an error for a nonexistent application."""
    error, result = svc.research(999)
    assert error is not None
    assert "not found" in error.lower()


def test_prep_ai_error(svc, app_with_jd, monkeypatch):
    """AI failure during prep should return an error string and empty result."""
    monkeypatch.setattr("linkedin.ai.client.generate_with_ai", _raise_ai_error)
    error, result = svc.prep(1)
    assert error is not None
    assert result == ""


def test_prep_saves_and_overwrites(svc, app_with_jd, monkeypatch):
    """Calling prep twice should overwrite the previously saved questions."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=1200: "First response",
    )
    svc.prep(1)

    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=1200: "Updated response",
    )
    svc.prep(1)

    prep = svc.get_prep(1)
    assert prep is not None
    assert "Updated response" in str(prep)
