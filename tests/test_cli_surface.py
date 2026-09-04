"""The rendering paths of the smaller groups: analytics, metrics, automation status and env.

Each command is driven once with data and once empty, so a table that stops
rendering is caught here rather than on the terminal.
"""

import datetime as dt
import json

import pytest
from click.testing import CliRunner

from linkedin.automation.session import ActionResult
from linkedin.cli import _app, cli


@pytest.fixture
def runner():
    return CliRunner()


def _seed_pipeline():
    svc = _app.contact_svc
    a = svc.add_contact("Ann", "Engineer", "TestCo", "https://linkedin.com/in/ann")
    b = svc.add_contact("Bob", "Engineer", "TestCo", "https://linkedin.com/in/bob")
    svc.update_contact(a["id"], status="connected")
    svc.update_contact(b["id"], status="responded")
    _app.draft_repo.add({"id": 1, "contact_id": a["id"], "type": "connection", "content": "hi", "source": "ai"})


# -- analytics -------------------------------------------------------------------


def test_analytics_summary_conversion_and_velocity_render(runner):
    for args in (["analytics", "summary"], ["analytics", "conversion"], ["analytics", "velocity", "--weeks", "2"]):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output

    _seed_pipeline()
    summary = runner.invoke(cli, ["analytics", "summary"])
    assert summary.exit_code == 0 and "Analytics Summary" in summary.output and "1/2 (50%)" in summary.output
    funnel = runner.invoke(cli, ["analytics", "conversion"])
    assert funnel.exit_code == 0 and "responded" in funnel.output.lower()
    velocity = runner.invoke(cli, ["analytics", "velocity", "--weeks", "2"])
    assert velocity.exit_code == 0 and "Outreach Velocity" in velocity.output and "2" in velocity.output


# -- metrics ---------------------------------------------------------------------


def test_metrics_show_is_empty_then_shows_deltas_and_post_impressions(runner):
    empty = runner.invoke(cli, ["metrics", "show"])
    assert empty.exit_code == 0 and "No metrics yet" in empty.output

    today = dt.date.today()
    _app.metrics_svc.record({"followers": 100, "connections": 50, "profile_views": 5}, day=today - dt.timedelta(days=8))
    _app.metrics_svc.record({"followers": 110, "connections": 50, "profile_views": None}, day=today)
    post = _app.post_svc.record_published("A post about the fleet", "urn:li:share:1")
    _app.metrics_svc.record({"followers": 110, "posts": {"urn:li:share:1": 42}}, day=today)

    shown = runner.invoke(cli, ["metrics", "show", "--days", "7"])
    assert shown.exit_code == 0, shown.output
    assert "followers" in shown.output and "+10" in shown.output
    assert "Post impressions" in shown.output and "42" in shown.output and str(post["id"]) in shown.output


def test_metrics_collect_records_and_names_what_was_not_read(runner, fake_session):
    fake_session.results["metrics"] = ActionResult("ok", "", {"followers": 7, "connections": None})
    result = runner.invoke(cli, ["metrics", "collect", "--headless"])
    assert result.exit_code == 0, result.output
    assert "Recorded metrics" in result.output and "Could not read: connections" in result.output
    assert _app.metrics_svc.latest()["followers"] == 7 and _app.metrics_svc.latest()["connections"] is None


def test_metrics_collect_fails_loudly_when_the_page_could_not_be_read(runner, fake_session):
    fake_session.results["metrics"] = ActionResult("failed", "dashboard did not load", None)
    result = runner.invoke(cli, ["metrics", "collect"])
    assert result.exit_code == 1 and "Metrics not read" in result.output
    assert _app.metrics_svc.latest() is None


# -- automation status and env ---------------------------------------------------


def test_automation_status_reports_no_schedule_then_the_latest_run(runner, monkeypatch, tmp_path):
    from linkedin.scheduling import install

    monkeypatch.setattr(install, "read_user_crontab_lines", lambda: ([], None))
    monkeypatch.setattr("linkedin.services.diagnostics.launchd_job", lambda *a, **k: None)

    status = runner.invoke(cli, ["automation", "status", "--json"])
    assert status.exit_code == 0, status.output
    payload = json.loads(status.output)
    assert payload["configured"] is False and payload["latest_run"] == {}

    runner.invoke(cli, ["run-daily", "--json", "--trigger", "scheduled"])
    text = runner.invoke(cli, ["automation", "status"])
    assert text.exit_code == 0, text.output
    assert "latest_run" in text.output and "trigger=scheduled" in text.output


def test_automation_env_status_sync_and_set_key(runner, monkeypatch, tmp_path):
    env_file = tmp_path / "cron.env"
    missing = runner.invoke(cli, ["automation", "env", "status", "--env-file", str(env_file)])
    assert missing.exit_code == 0 and "not found" in missing.output

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    nothing = runner.invoke(cli, ["automation", "env", "sync", "--env-file", str(env_file)])
    assert nothing.exit_code == 0 and "No supported keys" in nothing.output

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-shell")
    synced = runner.invoke(cli, ["automation", "env", "sync", "--env-file", str(env_file)])
    assert synced.exit_code == 0 and "ANTHROPIC_API_KEY" in synced.output
    assert "sk-from-shell" in env_file.read_text()

    set_key = runner.invoke(
        cli, ["automation", "env", "set-anthropic-key", "--env-file", str(env_file), "--key", "sk-typed", "--json"]
    )
    assert set_key.exit_code == 0, set_key.output
    assert json.loads(set_key.output)["ok"] is True and "sk-typed" in env_file.read_text()

    present = runner.invoke(cli, ["automation", "env", "status", "--env-file", str(env_file)])
    assert present.exit_code == 0 and "present" in present.output


def test_env_file_defaults_to_the_data_dir_at_call_time(runner):
    """The default is resolved when the command runs, so LINKEDIN_DATA_DIR set after import is honoured."""
    result = runner.invoke(cli, ["automation", "env", "status", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["path"] == str(_app.data_dir.root / "cron.env")
