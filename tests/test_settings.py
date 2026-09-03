"""AI disabled by choice: a state the tool understands, not a missing key it nags about."""

from unittest.mock import patch

from click.testing import CliRunner

from linkedin.ai.client import AI_DISABLED, ai_call
from linkedin.app import App
from linkedin.cli import _app, cli
from linkedin.data.paths import DataDir
from linkedin.services.daily_run import DailyRun, RunConfig
from linkedin.services.diagnostics import diagnostics
from linkedin.settings import ai_enabled, load_settings, set_setting
from tests.conftest import sample_contact, sample_profile


def test_defaults_on_and_setting_persists(tmp_path):
    d = DataDir(tmp_path)
    assert load_settings(d) == {"ai_enabled": True}
    set_setting("ai_enabled", False, d)
    assert ai_enabled(d) is False and load_settings(d)["ai_enabled"] is False


def test_ai_call_short_circuits_without_network_or_template(monkeypatch, tmp_path):
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))
    set_setting("ai_enabled", False, DataDir(tmp_path))
    with patch("linkedin.ai.client.generate_with_ai", side_effect=AssertionError("must not be called")):
        r = ai_call("prompt", fallback="template")
    assert not r and r.error == AI_DISABLED and r.was_fallback is False


def test_run_daily_skips_drafting_and_stays_green(monkeypatch, tmp_path):
    """With AI off, a scheduled run must not fail every morning on templates it did not want."""
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))
    app = App(DataDir(tmp_path))
    set_setting("ai_enabled", False, app.data_dir)
    app.profile_repo.save(sample_profile())
    app.contact_repo.add(sample_contact(id=1, status="not_contacted", follow_up_date="2000-01-01"))
    run = DailyRun(app, RunConfig(generate_drafts=True, save_drafts=True), sleep=lambda s: None)
    data = run.cycle()
    assert data["drafts"]["generated"] == 0 and data["drafts"]["templates"] == 0
    assert "written by hand" in data["drafts"]["skipped"]
    assert run.classify(data)[0] == "success"
    assert app.draft_repo.list_all() == []


def test_doctor_reports_disabled_as_ok(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = App(DataDir(tmp_path))
    set_setting("ai_enabled", False, app.data_dir)
    checks, _ = diagnostics(app, cron_lines=[], cron_error=None, probe_ai=True, launch_agents_dir=tmp_path / "none")
    by = {c["name"]: c for c in checks}
    assert by["anthropic_api_key"]["status"] == "ok" and "by choice" in by["anthropic_api_key"]["detail"]
    assert not any(n.startswith("ai_probe") for n in by)


def test_cli_settings_and_hand_written_entry_points():
    runner = CliRunner()
    assert "ai_enabled: True" in runner.invoke(cli, ["settings", "show"]).output
    result = runner.invoke(cli, ["settings", "ai", "off"])
    assert result.exit_code == 0 and "ai_enabled: False" in result.output

    runner.invoke(cli, ["contacts", "add"], input="Ada\nEng\nAcme\nu\n\n")
    result = runner.invoke(cli, ["drafts", "add", "1", "--text", "Hi Ada, short and specific."])
    assert result.exit_code == 0, result.output
    draft = _app.draft_repo.list_all()[0]
    assert draft["source"] == "ai" and draft["generated_from"] == "hand-written"
    assert "automate message 1 --draft-id 1" in result.output

    result = runner.invoke(cli, ["posts", "add-candidate", "--style", "how-to"], input="A post typed by hand.\n")
    assert result.exit_code == 0, result.output
    pending = _app.content_svc.pending_candidates()
    assert len(pending) == 1 and pending[0]["content"] == "A post typed by hand." and pending[0]["source"] == "ai"

    import linkedin.cli as cli_mod

    with patch.object(cli_mod, "collect_fleet_facts", lambda days=7: {"since": "a", "until": "b", "window_days": 7, "public_repos": 0, "merged_total": 0, "merged_by_human": 0, "merged_by_bots": 0, "repos_touched": 0, "top_repos": [], "recently_pushed": [], "sample_titles": []}):
        result = runner.invoke(cli, ["posts", "draft-week", "--count", "1"])
    assert result.exit_code == 1 and "No candidates" in result.output and "disabled" in result.output
