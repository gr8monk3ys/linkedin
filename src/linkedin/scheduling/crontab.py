"""Managed crontab block and cron env file management.

The CLI owns one delimited block in the user's crontab; everything here reads
and rewrites that block without touching unmanaged lines. Pure functions plus
two `crontab(1)` shell-outs.
"""

import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from linkedin.data.paths import DataDir
from linkedin.scheduling.schedule import parse_schedule_time

# The CLI owns exactly one delimited block in the crontab; unmanaged lines
# outside these markers are never rewritten.
AUTOMATION_CRON_BEGIN = "# >>> linkedin-cli run-daily managed >>>"
AUTOMATION_CRON_END = "# <<< linkedin-cli run-daily managed <<<"
AUTOMATION_ENV_KEYS = ("ANTHROPIC_API_KEY", "LINKEDIN_RUN_NOTIFY_WEBHOOK")


def default_automation_env_file(data_dir: DataDir) -> Path:
    return data_dir.cron_env


def sanitize_env_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", str(name).strip().upper())


def extract_exported_env_vars(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env_vars: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        key = sanitize_env_key(key)
        if not key:
            continue
        value = value.strip().strip("'").strip('"')
        env_vars[key] = value
    return env_vars


def write_env_file(path: Path, updates: dict[str, str]) -> tuple[bool, dict[str, str], str | None]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, {}, str(exc)

    current = extract_exported_env_vars(path)
    for key, value in updates.items():
        sanitized_key = sanitize_env_key(key)
        if not sanitized_key:
            continue
        trimmed = str(value).strip()
        if trimmed:
            current[sanitized_key] = trimmed

    lines = [
        "# Managed by linkedin-cli automation env sync",
        "# Used by cron-managed run-daily jobs",
    ]
    for key in sorted(current):
        lines.append(f"export {key}={shlex.quote(current[key])}")
    path.write_text("\n".join(lines) + "\n")

    try:
        path.chmod(0o600)
    except OSError:
        # Not all filesystems honor chmod; continue with best effort.
        pass

    return True, current, None


def env_file_status(path: Path) -> dict:
    exists = path.exists()
    if not exists:
        return {
            "path": str(path),
            "exists": False,
            "has_anthropic_api_key": False,
            "key_count": 0,
            "mode": "",
        }

    env_vars = extract_exported_env_vars(path)
    mode = ""
    try:
        mode = oct(path.stat().st_mode & 0o777)
    except OSError:
        mode = ""
    return {
        "path": str(path),
        "exists": True,
        "has_anthropic_api_key": bool(env_vars.get("ANTHROPIC_API_KEY")),
        "key_count": len(env_vars),
        "mode": mode,
    }


def build_cron_shell_command(workdir: Path, run_tokens: list[str], env_file: Path | None = None) -> str:
    segments = [f"cd {shlex.quote(str(workdir))}"]
    if env_file is not None:
        env_file_str = shlex.quote(str(env_file))
        segments.append(f"if [ -f {env_file_str} ]; then set -a; source {env_file_str}; set +a; fi")
    segments.append(shlex.join(run_tokens))
    inner = " && ".join(segments)
    return f"/bin/zsh -lc {shlex.quote(inner)}"


def build_managed_cron_job_line(
    schedule_time: str,
    cron_command: str,
    stdout_log: Path,
    stderr_log: Path,
) -> str:
    hour, minute = parse_schedule_time(schedule_time)
    return f"{minute} {hour} * * * {cron_command} >> {shlex.quote(str(stdout_log))} 2>> {shlex.quote(str(stderr_log))}"


def build_managed_cron_block(job_line: str) -> list[str]:
    timestamp = datetime.now().isoformat(timespec="seconds")
    return [
        AUTOMATION_CRON_BEGIN,
        f"# Managed by linkedin-cli automation schedule ({timestamp})",
        job_line,
        AUTOMATION_CRON_END,
    ]


def strip_managed_cron_block(lines: list[str]) -> tuple[list[str], bool]:
    cleaned: list[str] = []
    in_block = False
    removed = False

    for raw_line in lines:
        line = raw_line.strip()
        if line == AUTOMATION_CRON_BEGIN:
            in_block = True
            removed = True
            continue

        if in_block and line == AUTOMATION_CRON_END:
            in_block = False
            continue

        if in_block:
            removed = True
            continue

        cleaned.append(raw_line)

    return cleaned, removed


def extract_managed_cron_job_line(lines: list[str]) -> str:
    in_block = False
    for raw_line in lines:
        line = raw_line.strip()
        if line == AUTOMATION_CRON_BEGIN:
            in_block = True
            continue
        if in_block and line == AUTOMATION_CRON_END:
            return ""
        if in_block and line and not line.startswith("#"):
            return line
    return ""


def find_unmanaged_run_daily_cron_jobs(lines: list[str]) -> list[str]:
    jobs: list[str] = []
    in_managed_block = False
    for raw_line in lines:
        line = raw_line.strip()
        if line == AUTOMATION_CRON_BEGIN:
            in_managed_block = True
            continue
        if line == AUTOMATION_CRON_END:
            in_managed_block = False
            continue
        if in_managed_block or not line or line.startswith("#"):
            continue

        lowered = line.lower()
        if "run-daily" in lowered and ("linkedin-cli" in lowered or "linkedin.cli" in lowered):
            jobs.append(line)
    return jobs


def strip_unmanaged_run_daily_cron_jobs(lines: list[str]) -> tuple[list[str], int]:
    cleaned: list[str] = []
    removed = 0

    for raw_line in lines:
        line = raw_line.strip()
        if line and not line.startswith("#"):
            lowered = line.lower()
            if "run-daily" in lowered and ("linkedin-cli" in lowered or "linkedin.cli" in lowered):
                removed += 1
                continue
        cleaned.append(raw_line)

    return cleaned, removed


def strip_legacy_scheduler_comment_lines(lines: list[str]) -> tuple[list[str], int]:
    cleaned: list[str] = []
    removed = 0
    legacy_markers = {
        "# linkedin-cli daily automation (managed by codex)",
        "# end linkedin-cli daily automation",
    }

    for raw_line in lines:
        if raw_line.strip().lower() in legacy_markers:
            removed += 1
            continue
        cleaned.append(raw_line)

    return cleaned, removed


def cron_schedule_time_from_job_line(job_line: str) -> str:
    parts = job_line.split()
    if len(parts) < 6:
        return ""

    minute_token, hour_token, dom, month, dow = parts[:5]
    if dom != "*" or month != "*" or dow != "*":
        return ""

    if not minute_token.isdigit() or not hour_token.isdigit():
        return ""

    minute = int(minute_token)
    hour = int(hour_token)
    if minute < 0 or minute > 59 or hour < 0 or hour > 23:
        return ""
    return f"{hour:02d}:{minute:02d}"


def cron_env_file_from_job_line(job_line: str) -> Path | None:
    if not job_line:
        return None

    match = re.search(r"source\s+([^;]+);", job_line)
    if not match:
        return None

    candidate = match.group(1).strip().strip("'").strip('"')
    if not candidate:
        return None
    return Path(candidate).expanduser()


def read_user_crontab_lines() -> tuple[list[str], str | None]:
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return [], "crontab command not found."

    if result.returncode == 0:
        return result.stdout.splitlines(), None

    stderr = (result.stderr or result.stdout or "").strip()
    lower = stderr.lower()
    if "no crontab for" in lower or "no crontab" in lower:
        return [], None
    return [], stderr or f"crontab -l failed with exit code {result.returncode}."


def write_user_crontab_lines(lines: list[str]) -> str | None:
    payload = "\n".join(lines).rstrip()
    if payload:
        payload += "\n"

    try:
        result = subprocess.run(
            ["crontab", "-"],
            input=payload,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "crontab command not found."

    if result.returncode != 0:
        return (
            result.stderr or result.stdout or ""
        ).strip() or f"crontab install failed with exit code {result.returncode}."
    return None
