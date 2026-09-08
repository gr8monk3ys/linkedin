"""DailyRun: the plan as sections, the classification, and the retry loop — no CliRunner."""

from datetime import datetime
from unittest.mock import patch

from linkedin.app import App
from linkedin.data.paths import DataDir
from linkedin.services.daily_run import DailyRun, RunConfig, build_plan
from tests.conftest import sample_contact, sample_profile


def make(tmp_path, **cfg):
    app = App(DataDir(tmp_path))
    return app, DailyRun(app, RunConfig(**cfg), sleep=lambda s: None)


# -- sections ------------------------------------------------------------------------


def test_plan_sections_are_ordered_and_render_both_ways():
    data = {
        "generated_at": "2026-09-02T09:00:00",
        "profile": {"name": "Lorenzo", "target_role": "Solutions Engineer"},
        "actions": [{"priority": 95, "name": "Ada", "company": "Acme", "action": "follow_up_today", "contact_id": 1}],
        "application_actions": [],
        "inbox_proposals": [],
        "postings": [],
        "templates": [],
    }
    plan = build_plan(data)
    assert [s.key for s in plan.sections] == [
        "actions",
        "invitations",
        "inbound",
        "applications",
        "postings",
        "metrics",
    ]
    md = plan.to_markdown()
    assert md.startswith("# Daily Plan")
    assert "## Priority Actions" in md and "Follow up (today)" in md and "drafts follow-up 1" in md
    assert "## Inbound (needs your confirmation)" in md and "Nothing new" in md


def test_optional_sections_are_marked_so_the_terminal_can_skip_them():
    plan = build_plan(
        {"actions": [], "application_actions": [], "inbox_proposals": [], "postings": [], "templates": []}
    )
    assert {s.key for s in plan.sections if s.optional} == {"invitations", "inbound", "applications", "metrics"}


# -- classification --------------------------------------------------------------


def test_classify_success_when_there_are_actions(tmp_path):
    _, run = make(tmp_path)
    assert run.classify({"actions": [{"x": 1}], "drafts": {}}) == ("success", [])


def test_classify_no_actions_when_a_contact_is_stalled(tmp_path):
    app, run = make(tmp_path)
    app.contact_repo.add(sample_contact(id=1, status="connected", follow_up_date="2000-01-01"))
    status, stalled = run.classify({"actions": [], "drafts": {}})
    assert status == "no_actions" and [c["id"] for c in stalled] == [1]


def test_classify_success_on_a_genuinely_quiet_day(tmp_path):
    _, run = make(tmp_path)
    assert run.classify({"actions": [], "drafts": {}}) == ("success", [])


def test_classify_failed_when_drafts_were_templates(tmp_path):
    """AI was asked for and answered with a template: nothing usable was produced."""
    _, run = make(tmp_path)
    assert run.classify({"actions": [{"x": 1}], "drafts": {"templates": 2}}) == ("failed", [])


# -- drafts ------------------------------------------------------------------------


def test_draft_for_actions_counts_templates_and_saves_only_real_drafts(tmp_path):
    from linkedin.ai.client import AIClientError

    app, run = make(tmp_path)
    app.profile_repo.save(sample_profile())
    app.contact_repo.add(sample_contact(id=1, name="Ada"))
    action = {"action": "send_connection", "contact_id": 1, "name": "Ada"}
    with patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("down")):
        summary = run.draft_for_actions([action], save=True)
    assert summary["generated"] == 0 and summary["failed"] == 1 and summary["templates"] == 1
    assert app.draft_repo.list_all() == []
    with patch("linkedin.ai.client.generate_with_ai", return_value="Hi Ada"):
        summary = run.draft_for_actions([action], save=True)
    assert summary["generated"] == 1 and summary["saved"] == 1
    assert app.draft_repo.list_all()[0]["source"] == "ai"


# -- lifecycle ---------------------------------------------------------------------


def test_execute_logs_a_success_and_records_the_key(tmp_path):
    app, run = make(tmp_path, idempotency_key="k1")
    result = run.execute("manual", datetime.now())
    assert result["status"] == "success" and result["attempts"] == 1
    assert app.data_dir.run_daily_log.exists()
    second = run.execute("manual", datetime.now())
    assert second["status"] == "skipped_duplicate"


def test_execute_retries_with_backoff_then_recovers(tmp_path):
    slept = []
    app = App(DataDir(tmp_path))
    run = DailyRun(app, RunConfig(retry_attempts=2, retry_backoff_seconds=1.0), sleep=slept.append)
    with patch.object(
        DailyRun,
        "cycle",
        side_effect=[RuntimeError("boom"), RuntimeError("boom"), {"actions": [{"x": 1}], "drafts": {}}],
    ):
        result = run.execute("manual", datetime.now())
    assert result["status"] == "success"
    assert result["attempts"] == 3 and result["recovered_after_retries"] == 2
    assert slept == [1.0, 2.0]


def test_execute_exhausts_retries_and_reports_the_streak(tmp_path):
    app = App(DataDir(tmp_path))
    run = DailyRun(app, RunConfig(retry_attempts=1, retry_backoff_seconds=0.0), sleep=lambda s: None)
    with patch.object(DailyRun, "cycle", side_effect=RuntimeError("boom")):
        result = run.execute("manual", datetime.now())
    assert result["status"] == "failed" and result["attempts"] == 2
    assert result["error"] == "boom" and result["failure_streak"] == 2


def test_no_actions_is_reported_with_the_stalled_ids(tmp_path):
    app, run = make(tmp_path)
    app.contact_repo.add(sample_contact(id=7, status="connected", follow_up_date="2000-01-01"))
    with patch.object(DailyRun, "cycle", return_value={"actions": [], "drafts": {}, "postings": [], "templates": []}):
        result = run.execute("manual", datetime.now())
    assert result["status"] == "no_actions" and result["stalled_contact_ids"] == [7]


# -- metrics collection ---------------------------------------------------------


def test_collect_metrics_runs_before_the_plan_and_never_fails_the_run(tmp_path):
    app = App(DataDir(tmp_path))
    calls = []
    run = DailyRun(
        app,
        RunConfig(collect_metrics=True),
        sleep=lambda s: None,
        metrics_collector=lambda: calls.append(1) or {"recorded": "2026-09-02"},
    )
    data = run.cycle()
    assert calls == [1] and data["metrics_collected"] == {"recorded": "2026-09-02"}

    boom = DailyRun(
        app,
        RunConfig(collect_metrics=True),
        sleep=lambda s: None,
        metrics_collector=lambda: (_ for _ in ()).throw(RuntimeError("no browser")),
    )
    data = boom.cycle()
    assert "no browser" in data["metrics_collected"]["error"]
    assert "actions" in data  # the plan still ran


def test_metrics_are_not_collected_unless_asked(tmp_path):
    app = App(DataDir(tmp_path))
    run = DailyRun(app, RunConfig(), sleep=lambda s: None, metrics_collector=lambda: {"recorded": "x"})
    assert "metrics_collected" not in run.cycle()
