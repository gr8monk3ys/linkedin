"""The managed-schedule installer, without a CLI runner."""

from pathlib import Path
from unittest.mock import patch

from linkedin.scheduling import install
from linkedin.scheduling.crontab import AUTOMATION_CRON_BEGIN, AUTOMATION_CRON_END


def _spec(tmp_path: Path, **overrides) -> install.ScheduleSpec:
    base = dict(
        schedule_time="09:00",
        runner_tokens=["uv", "run", "linkedin-cli"],
        workdir=tmp_path,
        env_file=tmp_path / "cron.env",
        stdout_log=tmp_path / "logs" / "out.log",
        stderr_log=tmp_path / "logs" / "err.log",
    )
    base.update(overrides)
    return install.ScheduleSpec(**base)


def test_validate_reports_the_first_bad_field(tmp_path):
    assert _spec(tmp_path).validate() is None
    assert "retry-attempts" in _spec(tmp_path, retry_attempts=-1).validate()
    assert "retry-backoff" in _spec(tmp_path, retry_backoff_seconds=-1).validate()
    assert "failure-streak" in _spec(tmp_path, failure_streak_threshold=0).validate()
    assert _spec(tmp_path, schedule_time="25:00").validate()
    assert "workdir" in _spec(tmp_path, workdir=tmp_path / "missing").validate()


def test_save_drafts_implies_generate_drafts(tmp_path):
    tokens = _spec(tmp_path, generate_drafts=False, save_drafts=True).run_tokens()
    assert "--generate-drafts" in tokens and "--save-drafts" in tokens


def test_install_replaces_the_managed_block_and_adopts_unmanaged_jobs(tmp_path):
    existing = [
        "MAILTO=me@example.com",
        "0 8 * * * linkedin-cli run-daily",
        AUTOMATION_CRON_BEGIN,
        "0 7 * * * old",
        AUTOMATION_CRON_END,
        "0 5 * * * /other",
    ]
    written: list[list[str]] = []
    with (
        patch.object(install, "read_user_crontab_lines", return_value=(existing, None)),
        patch.object(install, "write_user_crontab_lines", side_effect=lambda lines: written.append(lines)),
    ):
        result = install.install_schedule(_spec(tmp_path), sync_env=False)

    assert result.error is None
    assert result.adopted_existing_jobs == 1
    lines = written[0]
    assert "MAILTO=me@example.com" in lines and "0 5 * * * /other" in lines
    assert "0 8 * * * linkedin-cli run-daily" not in lines and "0 7 * * * old" not in lines
    assert lines.count(AUTOMATION_CRON_BEGIN) == 1
    assert result.job_line in lines and "run-daily" in result.job_line
    assert (tmp_path / "logs").is_dir()


def test_install_keeps_unmanaged_jobs_when_not_adopting(tmp_path):
    existing = ["0 8 * * * linkedin-cli run-daily"]
    written: list[list[str]] = []
    with (
        patch.object(install, "read_user_crontab_lines", return_value=(existing, None)),
        patch.object(install, "write_user_crontab_lines", side_effect=lambda lines: written.append(lines)),
    ):
        result = install.install_schedule(_spec(tmp_path, adopt_existing=False), sync_env=False)
    assert result.adopted_existing_jobs == 0
    assert "0 8 * * * linkedin-cli run-daily" in written[0]


def test_install_stops_on_validation_read_and_write_errors(tmp_path):
    assert install.install_schedule(_spec(tmp_path, retry_attempts=-1)).error
    with patch.object(install, "read_user_crontab_lines", return_value=([], "no crontab")):
        assert "Could not read" in install.install_schedule(_spec(tmp_path), sync_env=False).error
    with (
        patch.object(install, "read_user_crontab_lines", return_value=([], None)),
        patch.object(install, "write_user_crontab_lines", return_value="denied"),
    ):
        assert "Could not install" in install.install_schedule(_spec(tmp_path), sync_env=False).error


def test_sync_env_copies_shell_keys_and_creates_an_empty_file(tmp_path, monkeypatch):
    env_file = tmp_path / "cron.env"
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert install.sync_env_from_environ(env_file) == ([], "")
    assert env_file.exists()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    keys, error = install.sync_env_from_environ(env_file)
    assert keys == ["ANTHROPIC_API_KEY"] and error == ""
    assert "sk-test" in env_file.read_text()


def test_remove_schedule_reports_absence_and_errors():
    with patch.object(install, "read_user_crontab_lines", return_value=(["0 5 * * * /other"], None)):
        assert install.remove_schedule() == (False, None)
    with patch.object(install, "read_user_crontab_lines", return_value=([], "no crontab")):
        removed, error = install.remove_schedule()
        assert not removed and "Could not read" in error
    block = [AUTOMATION_CRON_BEGIN, "0 9 * * * x", AUTOMATION_CRON_END]
    with (
        patch.object(install, "read_user_crontab_lines", return_value=(block, None)),
        patch.object(install, "write_user_crontab_lines", return_value=None) as write,
    ):
        assert install.remove_schedule() == (True, None)
        assert write.call_args.args[0] == []
