"""Install, adopt and remove the managed daily schedule.

`automation schedule` and `automation doctor --fix` both install the same
cron block; this is the one place that does it. Everything here returns
data or an error string, never prints. The crontab I/O functions are
looked up on this module at call time, which is where tests patch them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from linkedin.scheduling import crontab
from linkedin.scheduling.crontab import (
    AUTOMATION_ENV_KEYS,
    build_cron_shell_command,
    build_managed_cron_block,
    build_managed_cron_job_line,
    env_file_status,
    strip_legacy_scheduler_comment_lines,
    strip_managed_cron_block,
    strip_unmanaged_run_daily_cron_jobs,
    write_env_file,
)
from linkedin.scheduling.schedule import build_scheduled_run_daily_tokens, parse_schedule_time


def read_user_crontab_lines() -> tuple[list[str], str | None]:
    return crontab.read_user_crontab_lines()


def write_user_crontab_lines(lines: list[str]) -> str | None:
    return crontab.write_user_crontab_lines(lines)


@dataclass
class ScheduleSpec:
    """Everything a managed schedule is built from."""

    schedule_time: str
    runner_tokens: list[str]
    workdir: Path
    env_file: Path
    stdout_log: Path
    stderr_log: Path
    save_recap: bool = True
    generate_drafts: bool = True
    save_drafts: bool = True
    collect_metrics: bool = True
    retry_attempts: int = 2
    retry_backoff_seconds: float = 10.0
    failure_streak_threshold: int = 3
    notify_on_recovery: bool = True
    notify_webhook: str = ""
    adopt_existing: bool = True

    def validate(self) -> str | None:
        """The first reason this spec cannot be installed, or None."""
        if self.retry_attempts < 0:
            return "--retry-attempts must be 0 or greater."
        if self.retry_backoff_seconds < 0:
            return "--retry-backoff-seconds must be 0 or greater."
        if self.failure_streak_threshold < 1:
            return "--failure-streak-threshold must be at least 1."
        try:
            parse_schedule_time(self.schedule_time)
        except ValueError as exc:
            return str(exc)
        if not self.workdir.exists() or not self.workdir.is_dir():
            return f"Invalid --workdir: {self.workdir}"
        return None

    def run_tokens(self) -> list[str]:
        return build_scheduled_run_daily_tokens(
            self.runner_tokens,
            save_recap=self.save_recap,
            generate_drafts=self.generate_drafts or self.save_drafts,
            save_drafts=self.save_drafts,
            collect_metrics=self.collect_metrics,
            retry_attempts=self.retry_attempts,
            retry_backoff_seconds=self.retry_backoff_seconds,
            failure_streak_threshold=self.failure_streak_threshold,
            notify_on_recovery=self.notify_on_recovery,
            notify_webhook=self.notify_webhook,
        )

    def job_line(self) -> str:
        command = build_cron_shell_command(self.workdir, self.run_tokens(), env_file=self.env_file)
        return build_managed_cron_job_line(
            schedule_time=self.schedule_time,
            cron_command=command,
            stdout_log=self.stdout_log,
            stderr_log=self.stderr_log,
        )


@dataclass
class InstallResult:
    error: str | None = None
    job_line: str = ""
    adopted_existing_jobs: int = 0
    removed_legacy_comments: int = 0
    env_synced_keys: list[str] = field(default_factory=list)
    env_sync_error: str = ""

    def as_dict(self, spec: ScheduleSpec) -> dict:
        return {
            "backend": "cron",
            "configured": self.error is None,
            "schedule_time": spec.schedule_time,
            "workdir": str(spec.workdir),
            "runner": spec.runner_tokens,
            "job_line": self.job_line,
            "stdout_log": str(spec.stdout_log),
            "stderr_log": str(spec.stderr_log),
            "failure_streak_threshold": spec.failure_streak_threshold,
            "notify_on_recovery": spec.notify_on_recovery,
            "env_file": env_file_status(spec.env_file),
            "env_synced_keys": self.env_synced_keys,
            "env_sync_error": self.env_sync_error,
            "adopted_existing_jobs": self.adopted_existing_jobs,
            "removed_legacy_comments": self.removed_legacy_comments,
        }


def sync_env_from_environ(env_file: Path) -> tuple[list[str], str]:
    """Copy the automation keys present in this shell into the cron env file.

    Returns (keys written, error). An absent file is created empty so cron
    has something to source.
    """
    updates = {key: os.environ[key].strip() for key in AUTOMATION_ENV_KEYS if os.environ.get(key, "").strip()}
    if updates:
        _, env_vars, error = write_env_file(env_file, updates)
        if error:
            return [], error
        return sorted(k for k in updates if env_vars.get(k)), ""
    if not env_file.exists():
        _, _, error = write_env_file(env_file, {})
        return [], error or ""
    return [], ""


def install_schedule(spec: ScheduleSpec, *, sync_env: bool = True) -> InstallResult:
    """Replace the managed block in the user's crontab with this spec's job.

    With `adopt_existing`, unmanaged run-daily lines and legacy scheduler
    comments are removed so only one schedule fires.
    """
    result = InstallResult()
    error = spec.validate()
    if error:
        result.error = error
        return result

    spec.stdout_log.parent.mkdir(parents=True, exist_ok=True)
    spec.stderr_log.parent.mkdir(parents=True, exist_ok=True)
    if sync_env:
        result.env_synced_keys, result.env_sync_error = sync_env_from_environ(spec.env_file)

    current, read_error = read_user_crontab_lines()
    if read_error:
        result.error = f"Could not read crontab: {read_error}"
        return result

    cleaned, _ = strip_managed_cron_block(current)
    if spec.adopt_existing:
        cleaned, result.adopted_existing_jobs = strip_unmanaged_run_daily_cron_jobs(cleaned)
        cleaned, result.removed_legacy_comments = strip_legacy_scheduler_comment_lines(cleaned)

    result.job_line = spec.job_line()
    next_lines = list(cleaned)
    if next_lines and next_lines[-1].strip():
        next_lines.append("")
    next_lines.extend(build_managed_cron_block(result.job_line))

    write_error = write_user_crontab_lines(next_lines)
    if write_error:
        result.error = f"Could not install schedule: {write_error}"
    return result


def remove_schedule() -> tuple[bool, str | None]:
    """Strip the managed block. Returns (removed, error)."""
    current, read_error = read_user_crontab_lines()
    if read_error:
        return False, f"Could not read crontab: {read_error}"
    cleaned, removed = strip_managed_cron_block(current)
    if not removed:
        return False, None
    write_error = write_user_crontab_lines(cleaned)
    if write_error:
        return False, f"Could not remove schedule: {write_error}"
    return True, None
