"""Tests for the scheduling primitives extracted out of cli.py.

These ran only incidentally through CLI invocations before; the rules they
encode (when the next run is, which crontab lines are ours) are worth pinning
down directly.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from linkedin.scheduling.crontab import (
    AUTOMATION_CRON_BEGIN,
    AUTOMATION_CRON_END,
    build_cron_shell_command,
    build_managed_cron_block,
    build_managed_cron_job_line,
    cron_env_file_from_job_line,
    cron_schedule_time_from_job_line,
    extract_exported_env_vars,
    extract_managed_cron_job_line,
    find_unmanaged_run_daily_cron_jobs,
    read_user_crontab_lines,
    sanitize_env_key,
    strip_managed_cron_block,
    strip_unmanaged_run_daily_cron_jobs,
    write_env_file,
    write_user_crontab_lines,
)
from linkedin.scheduling.schedule import (
    build_scheduled_run_daily_tokens,
    next_scheduled_run,
    parse_schedule_time,
    runner_tokens_from_option,
    scheduled_run_for_date,
)


class TestParseScheduleTime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("09:00", (9, 0)), ("00:00", (0, 0)), ("23:59", (23, 59)), ("9:5", (9, 5))],
    )
    def test_valid(self, value, expected):
        assert parse_schedule_time(value) == expected

    @pytest.mark.parametrize("value", ["", "9", "09-00", "24:00", "23:60", "-1:00", "aa:bb", "09:00:00"])
    def test_invalid(self, value):
        with pytest.raises(ValueError, match="HH:MM"):
            parse_schedule_time(value)


class TestNextScheduledRun:
    def test_later_today_stays_today(self):
        now = datetime(2026, 8, 29, 7, 0)
        assert next_scheduled_run("09:00", now) == datetime(2026, 8, 29, 9, 0)

    def test_already_passed_rolls_to_tomorrow(self):
        now = datetime(2026, 8, 29, 10, 0)
        assert next_scheduled_run("09:00", now) == datetime(2026, 8, 30, 9, 0)

    def test_exactly_now_rolls_to_tomorrow(self):
        """Equal times must advance, or a watch loop would fire the same slot twice."""
        now = datetime(2026, 8, 29, 9, 0)
        assert next_scheduled_run("09:00", now) == datetime(2026, 8, 30, 9, 0)

    def test_crosses_month_boundary(self):
        now = datetime(2026, 8, 31, 23, 59)
        assert next_scheduled_run("09:00", now) == datetime(2026, 9, 1, 9, 0)

    def test_scheduled_run_for_date_zeroes_seconds(self):
        result = scheduled_run_for_date("09:30", datetime(2026, 8, 29, 18, 45, 12).date())
        assert result == datetime(2026, 8, 29, 9, 30)


class TestRunnerTokens:
    def test_blank_falls_back_to_a_discovered_runner(self):
        tokens, error = runner_tokens_from_option("   ")
        assert error is None
        assert tokens

    def test_explicit_runner_is_split_like_a_shell(self):
        tokens, error = runner_tokens_from_option("/usr/bin/env python -m linkedin.cli")
        assert error is None
        assert tokens == ["/usr/bin/env", "python", "-m", "linkedin.cli"]

    def test_unbalanced_quotes_are_reported(self):
        tokens, error = runner_tokens_from_option('python "unclosed')
        assert tokens == []
        assert "Invalid --runner" in error


class TestScheduledRunDailyTokens:
    def _tokens(self, **overrides):
        kwargs = dict(
            save_recap=False,
            generate_drafts=False,
            save_drafts=False,
            retry_attempts=2,
            retry_backoff_seconds=10.0,
            failure_streak_threshold=3,
            notify_on_recovery=True,
            notify_webhook="",
        )
        kwargs.update(overrides)
        return build_scheduled_run_daily_tokens(["uv", "run", "linkedin-cli"], **kwargs)

    def test_always_json_and_always_run_daily(self):
        tokens = self._tokens()
        assert tokens[:5] == ["uv", "run", "linkedin-cli", "run-daily", "--json"]

    def test_optional_flags_are_omitted_when_off(self):
        tokens = self._tokens()
        assert "--save-recap" not in tokens
        assert "--generate-drafts" not in tokens
        assert "--notify-webhook" not in tokens

    def test_flags_appear_when_enabled(self):
        tokens = self._tokens(save_recap=True, generate_drafts=True, save_drafts=True)
        for flag in ("--save-recap", "--generate-drafts", "--save-drafts"):
            assert flag in tokens

    def test_webhook_is_trimmed_and_paired(self):
        tokens = self._tokens(notify_webhook="  https://example.com/hook  ")
        assert tokens[tokens.index("--notify-webhook") + 1] == "https://example.com/hook"

    def test_recovery_flag_is_negative(self):
        assert "--no-notify-on-recovery" not in self._tokens(notify_on_recovery=True)
        assert "--no-notify-on-recovery" in self._tokens(notify_on_recovery=False)


class TestManagedCronBlock:
    def _job_line(self, env_file=None):
        return build_managed_cron_job_line(
            schedule_time="09:00",
            cron_command=build_cron_shell_command(
                Path("/repo"), ["uv", "run", "linkedin-cli"], env_file=env_file
            ),
            stdout_log=Path("/logs/out.log"),
            stderr_log=Path("/logs/err.log"),
        )

    def test_job_line_uses_minute_then_hour(self):
        assert self._job_line().startswith("0 9 * * * ")

    def test_block_is_delimited(self):
        block = build_managed_cron_block(self._job_line())
        assert block[0] == AUTOMATION_CRON_BEGIN
        assert block[-1] == AUTOMATION_CRON_END

    def test_round_trips_through_extract(self):
        job_line = self._job_line()
        block = build_managed_cron_block(job_line)
        assert extract_managed_cron_job_line(block) == job_line

    def test_schedule_time_is_recovered_from_the_line(self):
        assert cron_schedule_time_from_job_line(self._job_line()) == "09:00"

    def test_strip_removes_only_the_managed_block(self):
        lines = ["0 5 * * * /other/job", *build_managed_cron_block(self._job_line()), "# unrelated"]
        remaining, removed = strip_managed_cron_block(lines)
        assert removed is True
        assert remaining == ["0 5 * * * /other/job", "# unrelated"]

    def test_strip_is_a_noop_without_a_block(self):
        lines = ["0 5 * * * /other/job"]
        remaining, removed = strip_managed_cron_block(lines)
        assert removed is False
        assert remaining == lines

    def test_env_file_is_recovered_from_the_line(self):
        line = self._job_line(env_file=Path("/env/cron.env"))
        assert cron_env_file_from_job_line(line) == Path("/env/cron.env")

    def test_no_env_file_returns_none(self):
        assert cron_env_file_from_job_line(self._job_line()) is None


class TestUnmanagedCronJobs:
    def _managed(self):
        return build_managed_cron_block(
            build_managed_cron_job_line(
                schedule_time="09:00",
                cron_command=build_cron_shell_command(Path("/repo"), ["uv", "run", "linkedin-cli"]),
                stdout_log=Path("/logs/out.log"),
                stderr_log=Path("/logs/err.log"),
            )
        )

    def test_finds_a_hand_written_run_daily_job(self):
        lines = ["0 8 * * * cd /repo && linkedin-cli run-daily --save-recap"]
        assert find_unmanaged_run_daily_cron_jobs(lines) == lines

    def test_ignores_the_managed_block(self):
        assert find_unmanaged_run_daily_cron_jobs(self._managed()) == []

    def test_ignores_unrelated_and_commented_jobs(self):
        lines = ["0 8 * * * /some/other/job", "# 0 8 * * * linkedin-cli run-daily"]
        assert find_unmanaged_run_daily_cron_jobs(lines) == []

    def test_strip_removes_unmanaged_but_keeps_managed(self):
        managed = self._managed()
        lines = ["0 8 * * * linkedin-cli run-daily", *managed, "0 5 * * * /other"]
        remaining, count = strip_unmanaged_run_daily_cron_jobs(lines)
        assert count == 1
        assert remaining == [*managed, "0 5 * * * /other"]


class TestCronShellCommand:
    def test_quotes_the_working_directory(self):
        cmd = build_cron_shell_command(Path("/repos/my project"), ["uv", "run", "linkedin-cli"])
        assert "'/repos/my project'" in cmd

    def test_sources_the_env_file_before_running(self):
        cmd = build_cron_shell_command(Path("/repo"), ["linkedin-cli"], env_file=Path("/env/cron.env"))
        assert cmd.index("cron.env") < cmd.index("linkedin-cli")


class TestEnvFile:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("anthropic_api_key", "ANTHROPIC_API_KEY"), ("  my-key  ", "MY_KEY"), ("a.b$c", "A_B_C")],
    )
    def test_sanitize_env_key(self, raw, expected):
        assert sanitize_env_key(raw) == expected

    def test_write_then_extract_round_trips(self, tmp_path):
        path = tmp_path / "cron.env"
        wrote, values, error = write_env_file(path, {"ANTHROPIC_API_KEY": "sk-test"})
        assert error is None and wrote is True
        assert values == {"ANTHROPIC_API_KEY": "sk-test"}
        assert extract_exported_env_vars(path) == {"ANTHROPIC_API_KEY": "sk-test"}

    def test_existing_keys_are_preserved_not_clobbered(self, tmp_path):
        path = tmp_path / "cron.env"
        write_env_file(path, {"ANTHROPIC_API_KEY": "sk-test"})
        _wrote, values, _error = write_env_file(path, {"LINKEDIN_RUN_NOTIFY_WEBHOOK": "https://hook"})
        assert values == {
            "ANTHROPIC_API_KEY": "sk-test",
            "LINKEDIN_RUN_NOTIFY_WEBHOOK": "https://hook",
        }

    def test_blank_values_do_not_overwrite(self, tmp_path):
        path = tmp_path / "cron.env"
        write_env_file(path, {"ANTHROPIC_API_KEY": "sk-test"})
        _wrote, values, _error = write_env_file(path, {"ANTHROPIC_API_KEY": "   "})
        assert values["ANTHROPIC_API_KEY"] == "sk-test"

    def test_env_file_is_not_world_readable(self, tmp_path):
        """It holds an API key."""
        path = tmp_path / "cron.env"
        write_env_file(path, {"ANTHROPIC_API_KEY": "sk-test"})
        assert path.stat().st_mode & 0o077 == 0

    def test_missing_file_extracts_nothing(self, tmp_path):
        assert extract_exported_env_vars(tmp_path / "absent.env") == {}


class TestCrontabIO:
    def test_read_returns_lines(self):
        proc = MagicMock(returncode=0, stdout="0 9 * * * job\n", stderr="")
        with patch("linkedin.scheduling.crontab.subprocess.run", return_value=proc):
            lines, error = read_user_crontab_lines()
        assert error is None
        assert lines == ["0 9 * * * job"]

    def test_empty_crontab_is_not_an_error(self):
        proc = MagicMock(returncode=1, stdout="", stderr="no crontab for user")
        with patch("linkedin.scheduling.crontab.subprocess.run", return_value=proc):
            lines, error = read_user_crontab_lines()
        assert lines == [] and error is None

    def test_write_reports_failure(self):
        proc = MagicMock(returncode=1, stdout="", stderr="permission denied")
        with patch("linkedin.scheduling.crontab.subprocess.run", return_value=proc):
            assert "permission denied" in write_user_crontab_lines(["0 9 * * * job"])

    def test_write_success_returns_none(self):
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch("linkedin.scheduling.crontab.subprocess.run", return_value=proc):
            assert write_user_crontab_lines(["0 9 * * * job"]) is None


def test_scheduled_tokens_carry_collect_metrics():
    from linkedin.scheduling.schedule import build_scheduled_run_daily_tokens

    base = dict(save_recap=True, generate_drafts=True, save_drafts=True, retry_attempts=1, retry_backoff_seconds=1.0, failure_streak_threshold=3, notify_on_recovery=True, notify_webhook="")
    assert "--collect-metrics" in build_scheduled_run_daily_tokens(["linkedin-cli"], collect_metrics=True, **base)
    assert "--collect-metrics" not in build_scheduled_run_daily_tokens(["linkedin-cli"], **base)
