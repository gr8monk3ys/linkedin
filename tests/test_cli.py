"""Tests for linkedin-cli."""

import json
from datetime import datetime, timedelta
from importlib.metadata import version
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from linkedin.cli import _app_version, cli
from linkedin.data.json_store import ensure_dirs, load_json, save_json


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_data_dir(tmp_path, monkeypatch):
    """Use a temporary directory for data storage."""
    test_data_dir = tmp_path / ".linkedin-cli"
    monkeypatch.setattr("linkedin.data.json_store.DATA_DIR", test_data_dir)
    monkeypatch.setattr("linkedin.data.json_store.PROFILE_FILE", test_data_dir / "my_profile.json")
    monkeypatch.setattr("linkedin.data.json_store.CONTACTS_FILE", test_data_dir / "contacts.json")
    monkeypatch.setattr("linkedin.data.json_store.COMPANIES_FILE", test_data_dir / "companies.json")
    monkeypatch.setattr("linkedin.data.json_store.DRAFTS_FILE", test_data_dir / "drafts.json")
    monkeypatch.setattr("linkedin.data.json_store.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.data.json_store.RESEARCH_FILE", test_data_dir / "research.json")
    monkeypatch.setattr("linkedin.data.json_store.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.data.json_store.JOB_POSTINGS_FILE", test_data_dir / "job_postings.json")
    monkeypatch.setattr("linkedin.data.json_store.RUN_DAILY_STATE_FILE", test_data_dir / "run_daily_state.json")
    monkeypatch.setattr("linkedin.data.json_store.RUN_DAILY_LOG_FILE", test_data_dir / "run_daily.log.jsonl")
    monkeypatch.setattr("linkedin.data.json_store.RUN_DAILY_LOCK_FILE", test_data_dir / "run_daily.lock")
    monkeypatch.setattr("linkedin.data.json_store.BACKUPS_DIR", test_data_dir / "backups")
    # Also patch the data_service module which imports these directly
    monkeypatch.setattr("linkedin.services.data_service.CONTACTS_FILE", test_data_dir / "contacts.json")
    monkeypatch.setattr("linkedin.services.data_service.COMPANIES_FILE", test_data_dir / "companies.json")
    monkeypatch.setattr("linkedin.services.data_service.DRAFTS_FILE", test_data_dir / "drafts.json")
    monkeypatch.setattr("linkedin.services.data_service.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.services.data_service.PROFILE_FILE", test_data_dir / "my_profile.json")
    monkeypatch.setattr("linkedin.services.data_service.RESEARCH_FILE", test_data_dir / "research.json")
    monkeypatch.setattr("linkedin.services.data_service.TEMPLATES_FILE", test_data_dir / "templates.json")
    monkeypatch.setattr("linkedin.services.data_service.JOB_POSTINGS_FILE", test_data_dir / "job_postings.json")
    monkeypatch.setattr("linkedin.services.data_service.RUN_DAILY_STATE_FILE", test_data_dir / "run_daily_state.json")
    monkeypatch.setattr("linkedin.services.data_service.RUN_DAILY_LOG_FILE", test_data_dir / "run_daily.log.jsonl")
    monkeypatch.setattr("linkedin.services.data_service.BACKUPS_DIR", test_data_dir / "backups")
    return test_data_dir


class TestDataStorage:
    """Tests for data storage functions."""

    def test_ensure_dirs_creates_directory(self, temp_data_dir):
        """ensure_dirs should create the data directory."""
        assert not temp_data_dir.exists()
        ensure_dirs()
        assert temp_data_dir.exists()

    def test_load_json_returns_default_when_file_missing(self, temp_data_dir):
        """load_json should return default when file doesn't exist."""
        result = load_json(temp_data_dir / "nonexistent.json", [])
        assert result == []

        result = load_json(temp_data_dir / "nonexistent.json", {})
        assert result == {}

    def test_save_and_load_json(self, temp_data_dir):
        """save_json and load_json should round-trip data."""
        test_data = {"name": "Test", "value": 123}
        test_file = temp_data_dir / "test.json"

        save_json(test_file, test_data)
        loaded = load_json(test_file, {})

        assert loaded == test_data


class TestCLI:
    """Tests for CLI commands."""

    def test_cli_help(self, runner):
        """CLI should show help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "LinkedIn Job Hunt Assistant" in result.output

    def test_cli_version(self, runner):
        """CLI should show version."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert _app_version() in result.output
        assert version("linkedin") in result.output


class TestProfile:
    """Tests for profile commands."""

    def test_profile_show_empty(self, runner, temp_data_dir):
        """profile show should indicate no profile when empty."""
        result = runner.invoke(cli, ["profile", "show"])
        assert result.exit_code == 0
        assert "No profile set up" in result.output

    def test_profile_setup_and_show(self, runner, temp_data_dir):
        """profile setup should save and show should display."""
        # Setup profile with input
        result = runner.invoke(
            cli,
            ["profile", "setup"],
            input="John Doe\nAI Engineer\nML Engineer\nPython, ML\nBuilt RAG systems\nUnique skills\nTech\nSF\nn\n",
        )
        assert result.exit_code == 0
        assert "Profile saved" in result.output

        # Verify show displays it
        result = runner.invoke(cli, ["profile", "show"])
        assert result.exit_code == 0
        assert "John Doe" in result.output


class TestContacts:
    """Tests for contacts CRM commands."""

    def test_contacts_list_empty(self, runner, temp_data_dir):
        """contacts list should indicate no contacts when empty."""
        result = runner.invoke(cli, ["contacts", "list"])
        assert result.exit_code == 0
        assert "No contacts yet" in result.output

    def test_contacts_add_and_list(self, runner, temp_data_dir):
        """contacts add should add and list should show."""
        result = runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane Smith\nCTO\nAcme Corp\nhttps://linkedin.com/in/jane\nGreat connection\n",
        )
        assert result.exit_code == 0
        assert "Added: Jane Smith" in result.output

        result = runner.invoke(cli, ["contacts", "list"])
        assert result.exit_code == 0
        assert "Jane Smith" in result.output
        assert "CTO" in result.output
        assert "Acme Corp" in result.output

    def test_contacts_view(self, runner, temp_data_dir):
        """contacts view should show contact details."""
        # Add a contact first
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Bob Jones\nEngineer\nTech Inc\nhttps://linkedin.com/in/bob\nTest notes\n",
        )

        result = runner.invoke(cli, ["contacts", "view", "1"])
        assert result.exit_code == 0
        assert "Bob Jones" in result.output
        assert "Engineer" in result.output
        assert "Tech Inc" in result.output

    def test_contacts_view_not_found(self, runner, temp_data_dir):
        """contacts view should handle missing contact."""
        result = runner.invoke(cli, ["contacts", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_contacts_update_status(self, runner, temp_data_dir):
        """contacts update should change status."""
        # Add a contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice\nManager\nCorp\nhttps://linkedin.com/in/alice\nNotes\n",
        )

        # Update status
        result = runner.invoke(cli, ["contacts", "update", "1", "--status", "connected"])
        assert result.exit_code == 0
        assert "Updated" in result.output

        # Verify status changed
        result = runner.invoke(cli, ["contacts", "view", "1"])
        assert "connected" in result.output

    def test_contacts_update_auto_records_template_outcome(self, runner, temp_data_dir):
        """contacts update should auto-credit relevant template outcomes."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice\nManager\nCorp\nhttps://linkedin.com/in/alice\nNotes\n",
        )
        runner.invoke(
            cli,
            ["templates", "save", "--name", "Conn", "--type", "connection", "--content", "Hi {{name}}"],
        )
        runner.invoke(cli, ["templates", "use", "1", "1"])

        result = runner.invoke(cli, ["contacts", "update", "1", "--status", "connected"])
        assert result.exit_code == 0
        assert "Auto-recorded template outcome" in result.output

        result = runner.invoke(cli, ["templates", "suggest-best", "--type", "connection"])
        assert result.exit_code == 0
        assert "100.0%" in result.output

    def test_contacts_stats(self, runner, temp_data_dir):
        """contacts stats should show pipeline stats."""
        # Add contacts
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Person1\nRole\nCo\nurl\nNotes\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Person2\nRole\nCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "stats"])
        assert result.exit_code == 0
        assert "Outreach Pipeline" in result.output
        assert "Not Contacted" in result.output


class TestDrafts:
    """Tests for drafts commands."""

    def test_drafts_list_empty(self, runner, temp_data_dir):
        """drafts list should indicate no drafts when empty."""
        result = runner.invoke(cli, ["drafts", "list"])
        assert result.exit_code == 0
        assert "No drafts yet" in result.output

    def test_drafts_connection_no_profile(self, runner, temp_data_dir):
        """drafts connection should require profile setup."""
        # Add a contact without profile
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Test\nRole\nCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["drafts", "connection", "1"])
        assert result.exit_code == 0
        assert "Set up your profile" in result.output

    def test_drafts_connection_contact_not_found(self, runner, temp_data_dir):
        """drafts connection should handle missing contact."""
        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Name\nTitle\nRole\nSkills\nExp\nUnique\nIndustry\nLoc\nn\n",
        )

        result = runner.invoke(cli, ["drafts", "connection", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_connection_generates(self, mock_ai, runner, temp_data_dir):
        """drafts connection should generate AI draft."""
        mock_ai.return_value = "Hi! I'd love to connect and discuss AI engineering."

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        # Add contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Harrison\nCEO\nLangChain\nurl\nRAG expert\n",
        )

        # Generate draft (decline save)
        result = runner.invoke(cli, ["drafts", "connection", "1"], input="n\n")
        assert result.exit_code == 0
        assert "I'd love to connect" in result.output
        mock_ai.assert_called_once()

    def test_drafts_view_not_found(self, runner, temp_data_dir):
        """drafts view should handle missing draft."""
        result = runner.invoke(cli, ["drafts", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output


class TestResearch:
    """Tests for research commands."""

    def test_research_engagement(self, runner, temp_data_dir):
        """research engagement should show strategies."""
        result = runner.invoke(cli, ["research", "engagement"])
        assert result.exit_code == 0
        assert "LinkedIn Engagement Strategies" in result.output
        assert "Post Formats" in result.output

    @patch("linkedin.services.research_service.generate_ai_text")
    def test_research_ideas(self, mock_ai, runner, temp_data_dir):
        """research ideas should generate post ideas."""
        mock_ai.return_value = ("1. Post idea one\n2. Post idea two", None)

        result = runner.invoke(cli, ["research", "ideas", "--topic", "AI"], input="n\n")
        assert result.exit_code == 0
        assert "Post idea" in result.output

    @patch("linkedin.services.research_service.generate_ai_text")
    def test_research_hashtags(self, mock_ai, runner, temp_data_dir):
        """research hashtags should generate hashtag suggestions."""
        mock_ai.return_value = ("#MachineLearning\n#AI\n#DataScience", None)

        result = runner.invoke(cli, ["research", "hashtags", "machine learning"])
        assert result.exit_code == 0
        assert "Hashtag Recommendations" in result.output


class TestDashboard:
    """Tests for dashboard command."""

    def test_dashboard_empty(self, runner, temp_data_dir):
        """dashboard should show empty state."""
        result = runner.invoke(cli, ["dashboard"])
        assert result.exit_code == 0
        assert "Job Hunt Dashboard" in result.output
        assert "Profile: Not set up" in result.output

    def test_dashboard_with_data(self, runner, temp_data_dir):
        """dashboard should show profile and contacts."""
        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        # Add contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane\nCTO\nCorp\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["dashboard"])
        assert result.exit_code == 0
        assert "Lorenzo" in result.output
        assert "ML Role" in result.output
        assert "CONTACTS PIPELINE" in result.output
        assert "Not Contacted" in result.output

    def test_daily_plan_empty(self, runner, temp_data_dir):
        """daily-plan should show actionable empty states."""
        result = runner.invoke(cli, ["daily-plan"])
        assert result.exit_code == 0
        assert "Daily Plan" in result.output
        assert "Priority Actions" in result.output
        assert "No urgent contact actions" in result.output

    def test_daily_plan_with_data(self, runner, temp_data_dir):
        """daily-plan should combine actions, postings, and template recommendations."""
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nSenior Engineer\nPython, SQL\nBuilt AI\nUnique\nTech\nSan Francisco\nn\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice Smith\nEngineer\nAcme\nurl\nNotes\n",
        )
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(cli, ["contacts", "remind", "1", "--date", yesterday])

        runner.invoke(
            cli,
            ["market", "add-posting", "--title", "Senior Engineer", "--company", "Acme", "--location", "San Francisco", "--skills", "Python, SQL"],
        )

        runner.invoke(
            cli,
            ["templates", "save", "--name", "Msg A", "--type", "message", "--content", "Hi {{name}}", "--variant", "A"],
        )
        for _ in range(5):
            runner.invoke(cli, ["templates", "use", "1", "1"])
        runner.invoke(cli, ["templates", "record-response", "1", "--count", "2"])

        result = runner.invoke(cli, ["daily-plan"])
        assert result.exit_code == 0
        assert "Daily Plan" in result.output
        assert "Priority Actions" in result.output
        assert "Best-Match Opportunities" in result.output
        assert "Best Templates" in result.output

    def test_daily_plan_save_recap(self, runner, temp_data_dir):
        """daily-plan should save markdown recap when requested."""
        result = runner.invoke(cli, ["daily-plan", "--save-recap"])
        assert result.exit_code == 0
        assert "Saved recap:" in result.output

        recaps = list((temp_data_dir / "recaps").glob("daily_plan_*.md"))
        assert len(recaps) == 1
        content = recaps[0].read_text()
        assert "# Daily Plan" in content
        assert "## Priority Actions" in content

    def test_daily_plan_json(self, runner, temp_data_dir):
        """daily-plan should support machine-readable JSON output."""
        result = runner.invoke(cli, ["daily-plan", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "generated_at" in payload
        assert "actions" in payload
        assert "postings" in payload
        assert "templates" in payload

    def test_run_daily_once_json(self, runner, temp_data_dir):
        """run-daily should execute one cycle and emit JSON."""
        result = runner.invoke(cli, ["run-daily", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "generated_at" in payload
        assert "drafts" in payload

    def test_run_daily_watch_run_now_max_runs(self, runner, temp_data_dir):
        """run-daily watch mode should support immediate bounded execution."""
        result = runner.invoke(
            cli,
            ["run-daily", "--watch", "--run-now", "--max-runs", "1", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert "generated_at" in payload

    def test_run_daily_watch_catch_up_runs_when_missed(self, runner, temp_data_dir):
        """watch mode should catch up if today's schedule time already passed."""
        result = runner.invoke(
            cli,
            ["run-daily", "--watch", "--time", "00:00", "--max-runs", "1", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["trigger"] == "watch_catch_up"

    def test_run_daily_idempotency_key_skips_duplicates(self, runner, temp_data_dir):
        """run-daily should skip duplicate idempotency keys."""
        first = runner.invoke(cli, ["run-daily", "--json", "--idempotency-key", "daily-smoke"])
        assert first.exit_code == 0
        assert json.loads(first.output)["status"] == "success"

        second = runner.invoke(cli, ["run-daily", "--json", "--idempotency-key", "daily-smoke"])
        assert second.exit_code == 0
        payload = json.loads(second.output)
        assert payload["status"] == "skipped_duplicate"

    def test_run_daily_writes_structured_log(self, runner, temp_data_dir):
        """run-daily should append a JSONL run log entry."""
        result = runner.invoke(cli, ["run-daily", "--json"])
        assert result.exit_code == 0

        log_file = temp_data_dir / "run_daily.log.jsonl"
        assert log_file.exists()
        entries = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        assert entries
        assert entries[-1]["status"] == "success"
        assert "run_id" in entries[-1]

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_run_daily_generate_drafts_falls_back_when_ai_fails(self, mock_ai, runner, temp_data_dir):
        """run-daily draft generation should recover with fallback text on AI failures."""
        from linkedin.ai.client import AIClientError

        mock_ai.side_effect = AIClientError("API unavailable")
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(cli, ["contacts", "remind", "1", "--date", yesterday])

        result = runner.invoke(
            cli,
            ["run-daily", "--json", "--generate-drafts", "--save-drafts"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["drafts"]["generated"] >= 1

    def test_run_daily_skips_when_lock_exists(self, runner, temp_data_dir):
        """run-daily should not execute when another lock is active."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        lock_file = temp_data_dir / "run_daily.lock"
        lock_file.write_text(json.dumps({"pid": 1234, "created_at": datetime.now().isoformat()}))

        result = runner.invoke(cli, ["run-daily", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "skipped_locked"

    @patch("urllib.request.urlopen")
    @patch("linkedin.cli._run_daily_cycle", side_effect=RuntimeError("boom"))
    def test_run_daily_failure_triggers_webhook(self, _mock_run_daily_cycle, mock_urlopen, runner, temp_data_dir):
        """run-daily should notify webhook on failures."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = runner.invoke(
            cli,
            ["run-daily", "--json", "--notify-webhook", "https://example.com/hook"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "failed"
        mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    @patch("linkedin.cli._run_daily_cycle", side_effect=RuntimeError("boom"))
    def test_run_daily_failure_streak_alert(self, _mock_run_daily_cycle, mock_urlopen, runner, temp_data_dir):
        """run-daily should escalate webhook payload when failure streak threshold is reached."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_data_dir / "run_daily.log.jsonl"
        log_file.write_text("\n".join([
            json.dumps({"status": "failed", "run_id": "f1", "finished_at": "2026-02-20T09:00:00"}),
            json.dumps({"status": "failed", "run_id": "f2", "finished_at": "2026-02-21T09:00:00"}),
        ]) + "\n")

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = runner.invoke(
            cli,
            [
                "run-daily",
                "--json",
                "--notify-webhook",
                "https://example.com/hook",
                "--retry-attempts",
                "0",
                "--failure-streak-threshold",
                "3",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "failed"
        assert payload["failure_streak"] == 3
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args.args[0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["payload"]["status"] == "failed_streak"

    @patch("urllib.request.urlopen")
    def test_run_daily_recovery_notification_after_streak(self, mock_urlopen, runner, temp_data_dir):
        """run-daily should send recovery notification when success follows a failure streak."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_data_dir / "run_daily.log.jsonl"
        log_file.write_text("\n".join([
            json.dumps({"status": "failed", "run_id": "f1", "finished_at": "2026-02-19T09:00:00"}),
            json.dumps({"status": "failed", "run_id": "f2", "finished_at": "2026-02-20T09:00:00"}),
            json.dumps({"status": "failed", "run_id": "f3", "finished_at": "2026-02-21T09:00:00"}),
        ]) + "\n")

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        result = runner.invoke(
            cli,
            [
                "run-daily",
                "--json",
                "--notify-webhook",
                "https://example.com/hook",
                "--failure-streak-threshold",
                "3",
                "--notify-on-recovery",
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["recovered_from_failure_streak"] == 3
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args.args[0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["payload"]["status"] == "recovered_after_failure_streak"

    @patch("linkedin.cli._run_daily_with_reliability")
    def test_run_daily_retries_until_success(self, mock_run_reliable, runner, temp_data_dir):
        """run-daily should retry failed runs and return success if recovered."""
        mock_run_reliable.side_effect = [
            {"status": "failed", "error": "temporary"},
            {
                "status": "success",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "profile": {},
                "actions": [],
                "postings": [],
                "templates": [],
                "drafts": {"generated": 0, "saved": 0, "failed": 0, "drafts": []},
            },
        ]

        result = runner.invoke(
            cli,
            ["run-daily", "--json", "--retry-attempts", "1", "--retry-backoff-seconds", "0"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "success"
        assert payload["attempts"] == 2
        assert mock_run_reliable.call_count == 2

    @patch("linkedin.cli._run_daily_with_reliability")
    def test_run_daily_retry_exhaustion(self, mock_run_reliable, runner, temp_data_dir):
        """run-daily should return failed after retries are exhausted."""
        mock_run_reliable.return_value = {"status": "failed", "error": "still failing"}

        result = runner.invoke(
            cli,
            ["run-daily", "--json", "--retry-attempts", "2", "--retry-backoff-seconds", "0"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["status"] == "failed"
        assert payload["attempts"] == 3
        assert mock_run_reliable.call_count == 3

    @patch("linkedin.cli._read_user_crontab_lines", return_value=([], None))
    def test_health_json_reports_schedule_and_api_key(self, _mock_read_cron, runner, temp_data_dir, monkeypatch):
        """health should report schedule validity and API key state."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(cli, ["health", "--json", "--time", "09:00"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        checks = {check["name"]: check for check in payload["checks"]}
        assert checks["schedule_time"]["status"] == "ok"
        assert checks["anthropic_api_key"]["status"] == "warn"

    @patch("linkedin.cli._read_user_crontab_lines", return_value=([], None))
    def test_health_detects_active_lock(self, _mock_read_cron, runner, temp_data_dir):
        """health should flag an active run lock."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        lock_file = temp_data_dir / "run_daily.lock"
        lock_file.write_text(json.dumps({"pid": 5678, "created_at": datetime.now().isoformat()}))

        result = runner.invoke(cli, ["health", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        checks = {check["name"]: check for check in payload["checks"]}
        assert checks["run_lock"]["status"] == "warn"

    def test_run_history_empty(self, runner, temp_data_dir):
        """run-history should show empty-state guidance without logs."""
        result = runner.invoke(cli, ["run-history"])
        assert result.exit_code == 0
        assert "No run history yet" in result.output

    def test_run_history_json_status_filter(self, runner, temp_data_dir):
        """run-history should filter entries by status in JSON mode."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        log_file = temp_data_dir / "run_daily.log.jsonl"
        log_file.write_text("\n".join([
            json.dumps({"status": "success", "run_id": "a1", "trigger": "manual", "finished_at": "2026-02-20T09:00:00"}),
            json.dumps({"status": "failed", "run_id": "b2", "trigger": "watch_scheduled", "finished_at": "2026-02-21T09:00:00", "error": "boom"}),
        ]) + "\n")

        result = runner.invoke(cli, ["run-history", "--json", "--status", "failed"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["total_matching"] == 1
        assert payload["entries"][0]["status"] == "failed"

    @patch("linkedin.cli._read_user_crontab_lines", return_value=([], None))
    def test_automation_status_unconfigured(self, _mock_read_cron, runner, temp_data_dir):
        """automation status should report when no managed schedule exists."""
        result = runner.invoke(cli, ["automation", "status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["backend"] == "cron"
        assert payload["configured"] is False
        assert payload["crontab_error"] == ""

    @patch("linkedin.cli._read_user_crontab_lines", return_value=([], None))
    def test_automation_env_sync(self, _mock_read_cron, runner, temp_data_dir, monkeypatch):
        """automation env sync should persist shell env keys into env file."""
        env_file = temp_data_dir / "cron.env"
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        result = runner.invoke(
            cli,
            ["automation", "env", "sync", "--env-file", str(env_file), "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["ok"] is True
        assert payload["status"]["exists"] is True
        assert payload["status"]["has_anthropic_api_key"] is True

    @patch("linkedin.cli._write_user_crontab_lines", return_value=None)
    @patch("linkedin.cli._read_user_crontab_lines", return_value=([], None))
    def test_automation_doctor_fix_installs_schedule(self, _mock_read_cron, _mock_write_cron, runner, temp_data_dir, monkeypatch):
        """automation doctor --fix should install managed schedule and sync env file."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "doctor-key")
        result = runner.invoke(cli, ["automation", "doctor", "--fix", "--json", "--time", "09:00"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["overall_status"] in {"ok", "warn"}
        assert any(check["name"] == "schedule_fix" for check in payload["checks"])

    @patch(
        "linkedin.cli._read_user_crontab_lines",
        return_value=(
            ["0 9 * * * /bin/zsh -lc 'cd /tmp && linkedin-cli run-daily --json'"],
            None,
        ),
    )
    def test_automation_status_detects_unmanaged_run_daily_job(self, _mock_read_cron, runner, temp_data_dir):
        """automation status should detect unmanaged run-daily cron jobs."""
        result = runner.invoke(cli, ["automation", "status", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["configured"] is True
        assert payload["managed"] is False
        assert payload["schedule_time"] == "09:00"
        assert len(payload["unmanaged_jobs"]) == 1

    @patch("linkedin.cli._write_user_crontab_lines", return_value=None)
    @patch("linkedin.cli._read_user_crontab_lines", return_value=(["MAILTO=test@example.com"], None))
    def test_automation_schedule_installs_managed_block(self, mock_read_cron, mock_write_cron, runner, temp_data_dir):
        """automation schedule should install an idempotent managed cron block."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        stdout_log = temp_data_dir / "cron.out.log"
        stderr_log = temp_data_dir / "cron.err.log"
        result = runner.invoke(
            cli,
            [
                "automation",
                "schedule",
                "--json",
                "--time",
                "09:30",
                "--runner",
                "/usr/local/bin/uv run linkedin-cli",
                "--workdir",
                str(temp_data_dir),
                "--stdout-log",
                str(stdout_log),
                "--stderr-log",
                str(stderr_log),
            ],
        )
        assert result.exit_code == 0

        payload = json.loads(result.output)
        assert payload["configured"] is True
        assert payload["schedule_time"] == "09:30"
        assert payload["workdir"] == str(temp_data_dir.resolve())
        assert payload["stdout_log"] == str(stdout_log)
        assert payload["stderr_log"] == str(stderr_log)

        mock_read_cron.assert_called_once()
        mock_write_cron.assert_called_once()
        written_lines = mock_write_cron.call_args.args[0]
        assert "MAILTO=test@example.com" in written_lines
        assert any(line.strip() == "# >>> linkedin-cli run-daily managed >>>" for line in written_lines)
        assert any(line.strip() == "# <<< linkedin-cli run-daily managed <<<" for line in written_lines)
        cron_lines = [line for line in written_lines if "run-daily" in line and line.strip().startswith("30 9")]
        assert len(cron_lines) == 1

    @patch("linkedin.cli._write_user_crontab_lines", return_value=None)
    @patch(
        "linkedin.cli._read_user_crontab_lines",
        return_value=(
            [
                "MAILTO=test@example.com",
                "# linkedin-cli daily automation (managed by codex)",
                "0 9 * * * /bin/zsh -lc 'cd /tmp && linkedin-cli run-daily --json'",
                "# end linkedin-cli daily automation",
            ],
            None,
        ),
    )
    def test_automation_schedule_adopts_existing_unmanaged_jobs(self, _mock_read_cron, mock_write_cron, runner, temp_data_dir):
        """automation schedule should replace old unmanaged run-daily cron entries by default."""
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        result = runner.invoke(
            cli,
            [
                "automation",
                "schedule",
                "--json",
                "--time",
                "10:15",
                "--runner",
                "/usr/local/bin/uv run linkedin-cli",
                "--workdir",
                str(temp_data_dir),
                "--stdout-log",
                str(temp_data_dir / "cron.out.log"),
                "--stderr-log",
                str(temp_data_dir / "cron.err.log"),
            ],
        )
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["adopted_existing_jobs"] == 1
        assert payload["removed_legacy_comments"] == 2

        written_lines = mock_write_cron.call_args.args[0]
        assert "MAILTO=test@example.com" in written_lines
        assert not any("cd /tmp && linkedin-cli run-daily --json" in line for line in written_lines)
        assert not any("daily automation (managed by codex)" in line for line in written_lines)
        assert any(line.strip().startswith("15 10") and "run-daily" in line for line in written_lines)

    def test_automation_schedule_invalid_runner(self, runner, temp_data_dir):
        """automation schedule should reject malformed runner command values."""
        result = runner.invoke(
            cli,
            [
                "automation",
                "schedule",
                "--runner",
                "'broken",
                "--workdir",
                str(temp_data_dir),
            ],
        )
        assert result.exit_code == 0
        assert "Invalid --runner value" in result.output

    @patch("linkedin.cli._write_user_crontab_lines", return_value=None)
    @patch(
        "linkedin.cli._read_user_crontab_lines",
        return_value=(
            [
                "MAILTO=test@example.com",
                "# >>> linkedin-cli run-daily managed >>>",
                "# Managed by linkedin-cli automation schedule (2026-02-22T09:00:00)",
                "0 9 * * * /bin/zsh -lc 'echo test'",
                "# <<< linkedin-cli run-daily managed <<<",
            ],
            None,
        ),
    )
    def test_automation_unschedule_removes_block(self, _mock_read_cron, mock_write_cron, runner, temp_data_dir):
        """automation unschedule should remove only managed cron entries."""
        result = runner.invoke(cli, ["automation", "unschedule", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["removed"] is True

        written_lines = mock_write_cron.call_args.args[0]
        assert written_lines == ["MAILTO=test@example.com"]

    @patch("linkedin.cli._write_user_crontab_lines", return_value=None)
    @patch("linkedin.cli._read_user_crontab_lines", return_value=(["MAILTO=test@example.com"], None))
    def test_automation_unschedule_noop_when_missing(self, _mock_read_cron, mock_write_cron, runner, temp_data_dir):
        """automation unschedule should no-op when no managed block exists."""
        result = runner.invoke(cli, ["automation", "unschedule", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["removed"] is False
        mock_write_cron.assert_not_called()


class TestCompanies:
    """Tests for companies commands."""

    def test_companies_list_empty(self, runner, temp_data_dir):
        """companies list should indicate no companies when empty."""
        result = runner.invoke(cli, ["companies", "list"])
        assert result.exit_code == 0
        assert "No companies yet" in result.output

    def test_companies_add_and_list(self, runner, temp_data_dir):
        """companies add should add and list should show."""
        result = runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200", "--priority", "high"],
            input="LangChain\nAI/ML\nBuilding RAG tools\n",
        )
        assert result.exit_code == 0
        assert "Added company: LangChain" in result.output

        result = runner.invoke(cli, ["companies", "list"])
        assert result.exit_code == 0
        assert "LangChain" in result.output
        assert "AI/ML" in result.output

    def test_companies_view(self, runner, temp_data_dir):
        """companies view should show company details."""
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        result = runner.invoke(cli, ["companies", "view", "1"])
        assert result.exit_code == 0
        assert "TestCo" in result.output
        assert "Tech" in result.output

    def test_companies_view_not_found(self, runner, temp_data_dir):
        """companies view should handle missing company."""
        result = runner.invoke(cli, ["companies", "view", "999"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_companies_update(self, runner, temp_data_dir):
        """companies update should change priority and add notes."""
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        result = runner.invoke(cli, ["companies", "update", "1", "--priority", "high", "--notes", "Very promising"])
        assert result.exit_code == 0
        assert "Updated" in result.output

    def test_companies_contacts(self, runner, temp_data_dir):
        """companies contacts should list contacts at a company."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # No contacts yet
        result = runner.invoke(cli, ["companies", "contacts", "1"])
        assert result.exit_code == 0
        assert "No contacts" in result.output


class TestEnhancedContacts:
    """Tests for enhanced contacts features."""

    def test_contacts_add_with_company_id(self, runner, temp_data_dir):
        """contacts add should link to company when company-id provided."""
        # Add company first
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact linked to company
        result = runner.invoke(
            cli,
            ["contacts", "add", "--company-id", "1"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )
        assert result.exit_code == 0
        assert "Added: John Doe" in result.output
        assert "Linked to company #1" in result.output

    def test_contacts_list_filter_by_company_id(self, runner, temp_data_dir):
        """contacts list should filter by company-id."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact linked to company
        runner.invoke(
            cli,
            ["contacts", "add", "--company-id", "1"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        # Add contact not linked
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane Doe\nManager\nOtherCo\nurl2\nNotes\n",
        )

        # Filter by company ID
        result = runner.invoke(cli, ["contacts", "list", "--company-id", "1"])
        assert result.exit_code == 0
        assert "John Doe" in result.output
        assert "Jane Doe" not in result.output

    def test_contacts_link_company(self, runner, temp_data_dir):
        """contacts link-company should link contact to company."""
        # Add company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        # Add contact without company link
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nSomeCo\nurl\nNotes\n",
        )

        # Link to company
        result = runner.invoke(cli, ["contacts", "link-company", "1", "1"])
        assert result.exit_code == 0
        assert "Linked" in result.output

    def test_contacts_due_empty(self, runner, temp_data_dir):
        """contacts due should handle no overdue contacts."""
        result = runner.invoke(cli, ["contacts", "due"])
        assert result.exit_code == 0
        assert "No contacts yet" in result.output or "No overdue" in result.output

    def test_contacts_remind(self, runner, temp_data_dir):
        """contacts remind should set follow-up date."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "remind", "1", "--days", "7"])
        assert result.exit_code == 0
        assert "Reminder set" in result.output

    def test_contacts_activity_empty(self, runner, temp_data_dir):
        """contacts activity should show empty state."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["contacts", "activity", "1"])
        assert result.exit_code == 0
        assert "No activities" in result.output

    def test_contacts_next_actions(self, runner, temp_data_dir):
        """contacts next-actions should show prioritized follow-ups."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(cli, ["contacts", "remind", "1", "--date", yesterday])

        result = runner.invoke(cli, ["contacts", "next-actions"])
        assert result.exit_code == 0
        assert "Next Actions" in result.output
        assert "follow-up 1" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Auto follow-up draft")
    def test_contacts_next_actions_generate_and_save_drafts(self, mock_ai, runner, temp_data_dir):
        """next-actions should auto-generate and save drafts when requested."""
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        runner.invoke(cli, ["contacts", "remind", "1", "--date", yesterday])

        result = runner.invoke(
            cli,
            ["contacts", "next-actions", "--limit", "1", "--generate-drafts", "--save-drafts"],
        )
        assert result.exit_code == 0
        assert "Generated 1 draft" in result.output

        result = runner.invoke(cli, ["drafts", "list"])
        assert result.exit_code == 0
        assert "follow_up_1" in result.output

    def test_contacts_dedupe_and_merge(self, runner, temp_data_dir):
        """contacts dedupe and merge should consolidate duplicates."""
        runner.invoke(
            cli,
            ["contacts", "add", "--email", "alice@example.com"],
            input="Alice Smith\nEngineer\nAcme\nurl1\nNote1\n",
        )
        runner.invoke(
            cli,
            ["contacts", "add", "--email", "alice@example.com"],
            input="Alice S\nEngineer\nAcme\nurl2\nNote2\n",
        )

        result = runner.invoke(cli, ["contacts", "dedupe"])
        assert result.exit_code == 0
        assert "Potential Duplicates" in result.output
        assert "merge 1 2" in result.output

        result = runner.invoke(cli, ["contacts", "merge", "1", "2"])
        assert result.exit_code == 0
        assert "Merged contacts" in result.output

        result = runner.invoke(cli, ["contacts", "list"])
        assert result.exit_code == 0
        assert "Alice Smith" in result.output

        result = runner.invoke(cli, ["contacts", "view", "2"])
        assert result.exit_code == 0
        assert "not found" in result.output


class TestCampaigns:
    """Tests for campaign sequencing commands."""

    def test_campaigns_enroll_status_and_due(self, runner, temp_data_dir):
        """campaign enrollment should appear in status and due views."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice Doe\nEngineer\nAcme\nurl\nNotes\n",
        )

        enroll = runner.invoke(cli, ["campaigns", "enroll", "1", "--name", "networking_21d"])
        assert enroll.exit_code == 0
        assert "Enrolled #1" in enroll.output

        status = runner.invoke(cli, ["campaigns", "status", "1", "--json"])
        assert status.exit_code == 0
        status_payload = json.loads(status.output)
        assert status_payload["campaign_name"] == "networking_21d"
        assert status_payload["active"] is True

        due = runner.invoke(cli, ["campaigns", "due", "--json"])
        assert due.exit_code == 0
        due_payload = json.loads(due.output)
        assert due_payload["count"] == 1
        assert due_payload["due_steps"][0]["contact_id"] == 1

    def test_campaigns_advance_and_complete(self, runner, temp_data_dir):
        """campaign advance should progress and complete the sequence."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice Doe\nEngineer\nAcme\nurl\nNotes\n",
        )
        runner.invoke(cli, ["campaigns", "enroll", "1", "--name", "networking_21d"])

        for _ in range(4):
            result = runner.invoke(cli, ["campaigns", "advance", "1"])
            assert result.exit_code == 0

        status = runner.invoke(cli, ["campaigns", "status", "1", "--json"])
        assert status.exit_code == 0
        payload = json.loads(status.output)
        assert payload["active"] is False
        assert payload["completed_at"] is not None

    def test_campaigns_unknown_name(self, runner, temp_data_dir):
        """campaign enrollment should reject unknown campaign names."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice Doe\nEngineer\nAcme\nurl\nNotes\n",
        )
        result = runner.invoke(cli, ["campaigns", "enroll", "1", "--name", "unknown_campaign"])
        assert result.exit_code == 0
        assert "Unknown campaign" in result.output


class TestEnhancedDrafts:
    """Tests for enhanced drafts features."""

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_intro_request(self, mock_ai, runner, temp_data_dir):
        """drafts intro-request should generate intro request."""
        mock_ai.return_value = "Hi, could you introduce me to someone?"

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        # Add two contacts
        runner.invoke(cli, ["contacts", "add"], input="Person1\nRole1\nCo1\nurl1\nNotes1\n")
        runner.invoke(cli, ["contacts", "add"], input="Person2\nRole2\nCo2\nurl2\nNotes2\n")

        result = runner.invoke(cli, ["drafts", "intro-request", "1", "--to", "2"], input="n\n")
        assert result.exit_code == 0
        assert "Introduction Request" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_thank_you(self, mock_ai, runner, temp_data_dir):
        """drafts thank-you should generate thank you note."""
        mock_ai.return_value = "Thank you for your time!"

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        runner.invoke(cli, ["contacts", "add"], input="Person\nRole\nCo\nurl\nNotes\n")

        result = runner.invoke(cli, ["drafts", "thank-you", "1"], input="n\n")
        assert result.exit_code == 0
        assert "Thank You" in result.output

    @patch("linkedin.services.draft_service.generate_with_ai")
    def test_drafts_follow_up(self, mock_ai, runner, temp_data_dir):
        """drafts follow-up should generate follow-up message."""
        mock_ai.return_value = "Just checking in..."

        # Setup profile
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        runner.invoke(cli, ["contacts", "add"], input="Person\nRole\nCo\nurl\nNotes\n")

        result = runner.invoke(cli, ["drafts", "follow-up", "1", "--attempt", "1"], input="n\n")
        assert result.exit_code == 0
        assert "Follow-up" in result.output


class TestDiscover:
    """Tests for discover commands."""

    def test_discover_contacts_no_args(self, runner, temp_data_dir):
        """discover contacts should require --company or --role."""
        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        result = runner.invoke(cli, ["discover", "contacts"])
        assert result.exit_code == 0
        assert "Specify --company or --role" in result.output

    @patch("linkedin.services.discover_service.generate_ai_text")
    def test_discover_contacts_with_company(self, mock_ai, runner, temp_data_dir):
        """discover contacts should generate suggestions for a company."""
        mock_ai.return_value = ("1. Engineering Manager\n2. Developer Advocate", None)

        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        result = runner.invoke(cli, ["discover", "contacts", "--company", "LangChain"])
        assert result.exit_code == 0
        assert "Contact Discovery" in result.output

    @patch("linkedin.services.discover_service.generate_ai_text")
    def test_discover_companies(self, mock_ai, runner, temp_data_dir):
        """discover companies should generate company suggestions."""
        mock_ai.return_value = ("1. Company A\n2. Company B", None)

        runner.invoke(
            cli,
            ["profile", "setup"],
            input="Lorenzo\nAI Engineer\nML Role\nPython\nBuilt AI\nUnique\nTech\nSF\nn\n",
        )

        result = runner.invoke(cli, ["discover", "companies"], input="n\n")
        assert result.exit_code == 0
        assert "Company Discovery" in result.output


class TestDataManagement:
    """Tests for data management commands."""

    def test_data_export_contacts_csv(self, runner, temp_data_dir):
        """data export contacts should create CSV file."""
        # Add a contact
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        output_file = temp_data_dir / "contacts.csv"
        result = runner.invoke(cli, ["data", "export", "contacts", "--output", str(output_file)])
        assert result.exit_code == 0
        assert "Exported 1 contacts" in result.output
        assert output_file.exists()

    def test_data_export_companies_csv(self, runner, temp_data_dir):
        """data export companies should create CSV file."""
        # Add a company
        runner.invoke(
            cli,
            ["companies", "add", "--size", "51-200"],
            input="TestCo\nTech\nGreat company\n",
        )

        output_file = temp_data_dir / "companies.csv"
        result = runner.invoke(cli, ["data", "export", "companies", "--output", str(output_file)])
        assert result.exit_code == 0
        assert "Exported 1 companies" in result.output
        assert output_file.exists()

    def test_data_backup_and_backups_list(self, runner, temp_data_dir):
        """data backup should create backup and backups should list it."""
        # Add some data first
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="John Doe\nEngineer\nTestCo\nurl\nNotes\n",
        )

        # Create backup
        result = runner.invoke(cli, ["data", "backup"])
        assert result.exit_code == 0
        assert "Backup created" in result.output

        # List backups
        result = runner.invoke(cli, ["data", "backups"])
        assert result.exit_code == 0
        assert "linkedin_cli_backup" in result.output

    def test_data_backup_verify_and_restore_dry_run(self, runner, temp_data_dir):
        """data backup verify and restore dry-run should validate archive integrity."""
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Jane Doe\nEngineer\nAcme\nurl\nNotes\n",
        )

        result = runner.invoke(cli, ["data", "backup", "--verify"])
        assert result.exit_code == 0
        assert "Backup created" in result.output
        assert "Verified:" in result.output

        backups = sorted((temp_data_dir / "backups").glob("linkedin_cli_backup_*.zip"))
        assert backups
        backup_file = str(backups[-1])

        verify_result = runner.invoke(cli, ["data", "verify-backup", backup_file, "--json"])
        assert verify_result.exit_code == 0
        verify_payload = json.loads(verify_result.output)
        assert verify_payload["valid"] is True

        dry_run_result = runner.invoke(cli, ["data", "restore", backup_file, "--dry-run"])
        assert dry_run_result.exit_code == 0
        assert "Dry-run passed" in dry_run_result.output


class TestTemplateCommands:
    """Tests for template experiment commands."""

    def test_templates_dashboard_and_suggest_best(self, runner, temp_data_dir):
        runner.invoke(
            cli,
            ["contacts", "add"],
            input="Alice Smith\nEngineer\nAcme\nurl\nNotes\n",
        )

        runner.invoke(
            cli,
            ["templates", "save", "--name", "Conn-A", "--type", "connection", "--content", "Hi {{name}}", "--variant", "A"],
        )
        runner.invoke(
            cli,
            ["templates", "save", "--name", "Conn-B", "--type", "connection", "--content", "Hello {{name}}", "--variant", "B"],
        )

        for _ in range(10):
            runner.invoke(cli, ["templates", "use", "1", "1"])
        for _ in range(10):
            runner.invoke(cli, ["templates", "use", "2", "1"])

        runner.invoke(cli, ["templates", "record-response", "1", "--count", "2"])
        runner.invoke(cli, ["templates", "record-response", "2", "--count", "5"])

        result = runner.invoke(cli, ["templates", "suggest-best", "--type", "connection"])
        assert result.exit_code == 0
        assert "Best template" in result.output
        assert "Conn-B" in result.output

        result = runner.invoke(cli, ["templates", "dashboard"])
        assert result.exit_code == 0
        assert "Template Experiments" in result.output
        assert "By Template Type" in result.output


class TestMarketCommands:
    """Tests for market posting tracking commands."""

    def test_market_add_and_list_postings(self, runner, temp_data_dir):
        result = runner.invoke(
            cli,
            [
                "market",
                "add-posting",
                "--title",
                "Senior Engineer",
                "--company",
                "Acme",
                "--location",
                "Remote",
                "--skills",
                "Python, SQL",
            ],
        )
        assert result.exit_code == 0
        assert "Added posting" in result.output

        result = runner.invoke(cli, ["market", "postings"])
        assert result.exit_code == 0
        assert "Senior Engineer" in result.output
        assert "Acme" in result.output

    def test_market_import_postings_csv(self, runner, temp_data_dir):
        temp_data_dir.mkdir(parents=True, exist_ok=True)
        csv_file = temp_data_dir / "postings.csv"
        csv_file.write_text("title,company,location,skills_required\nML Engineer,Beta,Remote,\"Python, ML\"\n")

        result = runner.invoke(cli, ["market", "import-postings", str(csv_file)])
        assert result.exit_code == 0
        assert "Imported 1 posting" in result.output


class TestAIGeneration:
    """Tests for AI generation function."""

    @patch("anthropic.Anthropic")
    def test_generate_with_ai_success(self, mock_anthropic_class):
        """generate_with_ai should return AI response."""
        from linkedin.ai.client import generate_with_ai

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="Generated text")]
        )

        result = generate_with_ai("Test prompt")
        assert result == "Generated text"

    @patch("anthropic.Anthropic")
    def test_generate_with_ai_failure(self, mock_anthropic_class):
        """generate_with_ai should raise a typed error when API fails."""
        from linkedin.ai.client import AIClientError, generate_with_ai

        mock_anthropic_class.side_effect = Exception("API Error")

        with pytest.raises(AIClientError) as exc:
            generate_with_ai("Test prompt")
        assert "AI generation failed" in str(exc.value)

    @patch("linkedin.ai.client.time.sleep")
    @patch("anthropic.Anthropic")
    def test_generate_with_ai_retries_then_succeeds(self, mock_anthropic_class, mock_sleep):
        """generate_with_ai should retry transient failures and eventually succeed."""
        from linkedin.ai.client import generate_with_ai

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = [
            RuntimeError("temporary timeout"),
            MagicMock(content=[MagicMock(text="Recovered")]),
        ]

        result = generate_with_ai("Test prompt", retries=1, backoff_seconds=0)
        assert result == "Recovered"
        assert mock_client.messages.create.call_count == 2
        mock_sleep.assert_not_called()

    @patch("anthropic.Anthropic")
    def test_generate_with_ai_non_retryable_error(self, mock_anthropic_class):
        """generate_with_ai should not retry auth-style failures."""
        from linkedin.ai.client import AIClientError, generate_with_ai

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = RuntimeError("401 unauthorized")

        with pytest.raises(AIClientError):
            generate_with_ai("Test prompt", retries=3, backoff_seconds=0)
        assert mock_client.messages.create.call_count == 1
