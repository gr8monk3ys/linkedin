"""Schedule-time parsing and the argv for a scheduled `run-daily`.

Pure functions: no Click, no Rich, no I/O. Extracted from cli.py so the
scheduling rules can be tested without going through a CLI invocation.
"""

import shlex
import shutil
import sys
from datetime import datetime, timedelta


def parse_schedule_time(schedule_time: str) -> tuple[int, int]:
    parts = schedule_time.split(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Time must use HH:MM format (24-hour).")

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Time must use HH:MM format (24-hour).") from exc

    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("Time must use HH:MM format (24-hour).")
    return hour, minute


def scheduled_run_for_date(schedule_time: str, day: datetime.date) -> datetime:
    hour, minute = parse_schedule_time(schedule_time)
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


def next_scheduled_run(schedule_time: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    candidate = scheduled_run_for_date(schedule_time, current.date())

    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


def default_scheduler_runner_tokens() -> list[str]:
    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "run", "linkedin-cli"]

    cli_path = shutil.which("linkedin-cli")
    if cli_path:
        return [cli_path]

    return [sys.executable, "-m", "linkedin.cli"]


def runner_tokens_from_option(runner: str) -> tuple[list[str], str | None]:
    if not runner.strip():
        return default_scheduler_runner_tokens(), None

    try:
        tokens = shlex.split(runner)
    except ValueError as exc:
        return [], f"Invalid --runner value: {exc}"

    if not tokens:
        return [], "Invalid --runner value: expected a command."
    return tokens, None


def build_scheduled_run_daily_tokens(
    runner_tokens: list[str],
    *,
    save_recap: bool,
    generate_drafts: bool,
    save_drafts: bool,
    retry_attempts: int,
    retry_backoff_seconds: float,
    failure_streak_threshold: int,
    notify_on_recovery: bool,
    notify_webhook: str,
) -> list[str]:
    command = [
        *runner_tokens,
        "run-daily",
        "--json",
        "--retry-attempts",
        str(retry_attempts),
        "--retry-backoff-seconds",
        str(retry_backoff_seconds),
        "--failure-streak-threshold",
        str(failure_streak_threshold),
    ]
    if save_recap:
        command.append("--save-recap")
    if generate_drafts:
        command.append("--generate-drafts")
    if save_drafts:
        command.append("--save-drafts")
    if notify_webhook.strip():
        command.extend(["--notify-webhook", notify_webhook.strip()])
    if not notify_on_recovery:
        command.append("--no-notify-on-recovery")
    return command
