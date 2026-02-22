"""Tests for ApplicationService."""

import pytest

import linkedin.data.json_store as js
from linkedin.ai.client import AIClientError
from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonContactRepo,
    JsonProfileRepo,
)
from linkedin.services.application_service import ApplicationService
from tests.conftest import sample_profile


def _raise_ai_error(*args, **kwargs):
    raise AIClientError("API error")


@pytest.fixture
def app_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    return JsonApplicationRepo(), JsonProfileRepo(), JsonContactRepo()


@pytest.fixture
def svc(app_repos):
    app_repo, profile_repo, contact_repo = app_repos
    return ApplicationService(app_repo, profile_repo, contact_repo)


def test_add_and_list(svc):
    svc.add_application("Acme", "ML Engineer", url="https://acme.com", jd_text="Python required")
    apps = svc.list_applications()
    assert len(apps) == 1
    assert apps[0]["company"] == "Acme"
    assert apps[0]["status"] == "saved"
    assert apps[0]["id"] is not None


def test_advance_status(svc):
    svc.add_application("Acme", "ML Engineer")
    apps = svc.list_applications()
    app_id = apps[0]["id"]
    svc.advance(app_id, "applied", notes="Submitted via website")
    app = svc.get_application(app_id)
    assert app["status"] == "applied"
    assert len(app["history"]) == 1
    assert app["history"][0]["status"] == "applied"
    assert app["history"][0]["notes"] == "Submitted via website"


def test_advance_invalid_status(svc):
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    error, _ = svc.advance(app_id, "hired")  # not valid
    assert error is not None


def test_delete(svc):
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    assert svc.delete(app_id) is True
    assert svc.get_application(app_id) is None


def test_filter_by_status(svc):
    svc.add_application("Acme", "ML Engineer")
    svc.advance(svc.list_applications()[0]["id"], "applied")
    svc.add_application("Beta", "Data Engineer")
    applied = svc.list_applications(status="applied")
    assert len(applied) == 1
    assert applied[0]["company"] == "Acme"


def test_stats_empty(svc):
    stats = svc.get_stats()
    assert stats["total"] == 0
    assert stats["by_status"] == {}


def test_stats_counts(svc):
    svc.add_application("A", "E1")
    svc.add_application("B", "E2")
    svc.advance(svc.list_applications()[0]["id"], "applied")
    stats = svc.get_stats()
    assert stats["total"] == 2
    assert stats["by_status"].get("applied") == 1
    assert stats["by_status"].get("saved") == 1


def test_tailor_resume_no_profile(svc):
    svc.add_application("Acme", "ML Engineer", jd_text="Python, ML")
    app_id = svc.list_applications()[0]["id"]
    error, _ = svc.tailor_resume(app_id)
    assert error is not None  # no profile set


def test_tailor_resume_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(resume_text="I built ML models for 3 years."))
    svc.add_application("Acme", "ML Engineer", jd_text="Need Python, MLOps")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=800: "• Built ML pipelines\n• Deployed models with MLOps",
    )
    error, result = svc.tailor_resume(app_id)
    assert error is None
    assert "ML" in result


def test_cover_letter_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(resume_text="5 years Python."))
    svc.add_application("Acme", "ML Engineer", jd_text="Python ML engineer")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=800: "Dear Hiring Manager, I am excited...",
    )
    error, result = svc.cover_letter(app_id)
    assert error is None
    assert "Hiring Manager" in result


def test_skills_gap_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(skills="Python, ML", resume_text="5 years Python."))
    svc.add_application("Acme", "ML Engineer", jd_text="Python, Kubernetes, MLOps")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=600: "You have: Python, ML\nMissing: Kubernetes, MLOps",
    )
    error, result = svc.skills_gap(app_id)
    assert error is None
    assert "Missing" in result


def test_tailor_resume_ai_error(svc, app_repos, monkeypatch):
    """AI failure should return an error string and empty result."""
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile())
    svc.add_application("Acme", "ML Engineer", jd_text="Python required")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr("linkedin.services.application_service.generate_with_ai", _raise_ai_error)
    error, result = svc.tailor_resume(app_id)
    assert error is not None
    assert result == ""


def test_cover_letter_ai_error(svc, app_repos, monkeypatch):
    """AI failure should return an error string and empty result."""
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile())
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr("linkedin.services.application_service.generate_with_ai", _raise_ai_error)
    error, result = svc.cover_letter(app_id)
    assert error is not None
    assert result == ""


def test_skills_gap_ai_error(svc, app_repos, monkeypatch):
    """AI failure should return an error string and empty result."""
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile())
    svc.add_application("Acme", "ML Engineer", jd_text="Python required")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr("linkedin.services.application_service.generate_with_ai", _raise_ai_error)
    error, result = svc.skills_gap(app_id)
    assert error is not None
    assert result == ""


def test_tailor_resume_with_resume_override(svc, monkeypatch):
    """resume_override bypasses profile lookup entirely."""
    svc.add_application("Acme", "ML Engineer", jd_text="Python required")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=800: "• Optimized data pipelines",
    )
    error, result = svc.tailor_resume(app_id, resume_override="Led ML team for 3 years.")
    assert error is None
    assert "Optimized" in result


def test_advance_same_status_allowed(svc):
    """Re-applying the same status should not error."""
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    svc.advance(app_id, "applied")
    error, _ = svc.advance(app_id, "applied")
    assert error is None


def test_list_filter_company_case_insensitive(svc):
    """Company filter should match regardless of case."""
    svc.add_application("Stripe Inc", "Engineer")
    results = svc.list_applications(company="stripe")
    assert len(results) == 1
    assert results[0]["company"] == "Stripe Inc"
