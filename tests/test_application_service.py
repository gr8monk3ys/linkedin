"""Tests for ApplicationService."""

import pytest

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
    return JsonApplicationRepo(tmp_path / "applications.json"), JsonProfileRepo(tmp_path / "profile.json"), JsonContactRepo(tmp_path / "contacts.json")


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
        "linkedin.ai.client.generate_with_ai",
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
        "linkedin.ai.client.generate_with_ai",
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
        "linkedin.ai.client.generate_with_ai",
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
    monkeypatch.setattr("linkedin.ai.client.generate_with_ai", _raise_ai_error)
    error, result = svc.tailor_resume(app_id)
    assert error is not None
    assert result == ""


def test_cover_letter_ai_error(svc, app_repos, monkeypatch):
    """AI failure should return an error string and empty result."""
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile())
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr("linkedin.ai.client.generate_with_ai", _raise_ai_error)
    error, result = svc.cover_letter(app_id)
    assert error is not None
    assert result == ""


def test_skills_gap_ai_error(svc, app_repos, monkeypatch):
    """AI failure should return an error string and empty result."""
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile())
    svc.add_application("Acme", "ML Engineer", jd_text="Python required")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr("linkedin.ai.client.generate_with_ai", _raise_ai_error)
    error, result = svc.skills_gap(app_id)
    assert error is not None
    assert result == ""


def test_tailor_resume_with_resume_override(svc, monkeypatch):
    """resume_override bypasses profile lookup entirely."""
    svc.add_application("Acme", "ML Engineer", jd_text="Python required")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
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


def _age(app, *, days):
    """Backdate every timestamp on an application, the way real elapsed time does.

    Backdating `applied_date` alone leaves the history event dated today, which
    is a row the service can never produce.
    """
    from datetime import datetime, timedelta

    stamp = (datetime.now() - timedelta(days=days)).isoformat()
    app["applied_date"] = stamp
    app["created_at"] = stamp
    for event in app.get("history") or []:
        event["date"] = stamp
    return app


# --- Planner rules -----------------------------------------------------------
# Applications were invisible to the daily planner: `get_next_actions` walks
# contacts only, so twenty applications sat at `applied` indefinitely.


def test_application_status_rules_cover_every_status():
    """A status with no rule is invisible to the planner forever.

    Same guard as `contact_service._check_status_coverage` — the contact
    pipeline shipped that hole once already, with `messaged`.
    """
    from linkedin.services.application_service import (
        APPLICATION_STATUS_RULES,
        APPLICATION_STATUSES,
        TERMINAL_APPLICATION_STATUSES,
    )

    covered = set(APPLICATION_STATUS_RULES) | set(TERMINAL_APPLICATION_STATUSES)
    assert covered == set(APPLICATION_STATUSES)


def test_applied_application_becomes_due_after_the_wait(svc):

    app = svc.add_application("Netflix", "ML Engineer")
    svc.advance(app["id"], "applied")
    stored = svc.get_application(app["id"])
    _age(stored, days=21)
    svc.applications.update(stored)

    actions = svc.get_application_actions()
    assert len(actions) == 1
    assert actions[0]["application_id"] == app["id"]
    assert actions[0]["action"] == "chase_application"
    assert "21" in actions[0]["reason"]


def test_freshly_applied_application_is_not_due(svc):
    app = svc.add_application("Netflix", "ML Engineer")
    svc.advance(app["id"], "applied")
    assert svc.get_application_actions() == []


def test_terminal_applications_generate_no_actions(svc):
    from datetime import datetime, timedelta

    for status in ("rejected", "accepted", "ghosted"):
        app = svc.add_application(f"Co-{status}", "Role")
        svc.advance(app["id"], status)
        stored = svc.get_application(app["id"])
        stored["created_at"] = (datetime.now() - timedelta(days=300)).isoformat()
        svc.applications.update(stored)

    assert svc.get_application_actions() == []


def test_saved_application_is_due_immediately(svc):
    """A saved job you never applied to is the whole point of saving it."""
    svc.add_application("Netflix", "ML Engineer")
    actions = svc.get_application_actions()
    assert len(actions) == 1
    assert actions[0]["action"] == "apply_to_saved"


def test_actions_are_sorted_by_priority_and_capped(svc):

    for i in range(5):
        app = svc.add_application(f"Co{i}", "Role")
        svc.advance(app["id"], "applied")
        stored = svc.get_application(app["id"])
        _age(stored, days=30 + i)
        svc.applications.update(stored)

    actions = svc.get_application_actions(limit=3)
    assert len(actions) == 3
    priorities = [a["priority"] for a in actions]
    assert priorities == sorted(priorities, reverse=True)


def test_application_with_no_usable_date_is_surfaced_not_skipped(svc):
    """Mirrors `repair_contact`: a stranded row must not sit invisible."""
    app = svc.add_application("Netflix", "ML Engineer")
    stored = svc.get_application(app["id"])
    stored["status"] = "applied"
    stored["applied_date"] = None
    stored["created_at"] = None
    svc.applications.update(stored)

    actions = svc.get_application_actions()
    assert len(actions) == 1
    assert actions[0]["action"] == "repair_application"


def test_an_import_does_not_reset_the_clock_on_an_old_application(svc):
    """Bookkeeping timestamps must not count as contact with the employer.

    Importing an application sent weeks ago wrote `created_at` of today, and a
    reference date of max(created_at, applied_date) made it look brand new — so
    a stale application would not come up for chasing until ten days after the
    *import*.
    """
    from datetime import datetime, timedelta

    app = svc.add_application("stripe", "Technical Solutions Engineer")
    stored = svc.get_application(app["id"])
    old = (datetime.now() - timedelta(days=21)).isoformat()
    stored["status"] = "applied"
    stored["applied_date"] = old
    stored["history"] = [{"status": "applied", "date": old, "notes": "Imported from autoapply"}]
    stored["created_at"] = datetime.now().isoformat()  # the import happened today
    svc.applications.update(stored)

    actions = svc.get_application_actions()
    assert len(actions) == 1
    assert actions[0]["action"] == "chase_application"
    assert "21" in actions[0]["reason"]
