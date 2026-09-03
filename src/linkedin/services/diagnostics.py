"""One check list, one naming, for `automation doctor` and `automation status`.

`health` and `doctor` each grew their own list of the same facts under
different names (`managed_schedule` vs `crontab`, `automation_env_file` vs
`env_file`). One function produces the checks; the commands render them.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from linkedin.ai.client import probe_api_key
from linkedin.scheduling.crontab import (
    cron_env_file_from_job_line,
    cron_schedule_time_from_job_line,
    default_automation_env_file,
    env_file_status,
    extract_exported_env_vars,
    extract_managed_cron_job_line,
    find_unmanaged_run_daily_cron_jobs,
)
from linkedin.scheduling.schedule import next_scheduled_run
from linkedin.services.run_state import health_lock_check, load_run_history_entries, load_run_state

if TYPE_CHECKING:
    from linkedin.app import App


def check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def overall_status(checks: list[dict], errors: list[str] | None = None) -> str:
    if any(c["status"] == "fail" for c in checks):
        return "fail"
    if errors or any(c["status"] == "warn" for c in checks):
        return "warn"
    return "ok"


def crontab_facts(app: App, cron_lines: list[str], cron_error: str | None) -> dict:
    """What the crontab says about run-daily: the one place this is derived."""
    managed = extract_managed_cron_job_line(cron_lines) if not cron_error else ""
    unmanaged = find_unmanaged_run_daily_cron_jobs(cron_lines) if not cron_error else []
    active = managed or (unmanaged[0] if unmanaged else "")
    env_file = cron_env_file_from_job_line(active) or default_automation_env_file(app.data_dir)
    return {
        "managed_job": managed,
        "unmanaged_jobs": unmanaged,
        "active_job": active,
        "schedule_time": cron_schedule_time_from_job_line(active) if active else "",
        "env_file": env_file,
        "env_status": env_file_status(env_file),
        "cron_error": cron_error or "",
    }


def diagnostics(
    app: App,
    *,
    cron_lines: list[str],
    cron_error: str | None,
    schedule_time: str = "09:00",
    lock_ttl_minutes: int = 180,
    webhook_url: str = "",
    probe_ai: bool = False,
    launch_agents_dir: Path | None = None,
) -> tuple[list[dict], dict]:
    """The full check list plus the crontab facts it was derived from."""
    checks: list[dict] = []
    d = app.data_dir

    try:
        d.ensure()
        probe = d.root / ".healthcheck.tmp"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        checks.append(check("data_dir", "ok", f"Writable: {d.root}"))
    except Exception as exc:
        checks.append(check("data_dir", "fail", f"Not writable: {exc}"))

    try:
        nxt = next_scheduled_run(schedule_time)
        checks.append(check("schedule_time", "ok", f"Valid; next run at {nxt.strftime('%Y-%m-%d %H:%M:%S')}."))
    except ValueError as exc:
        checks.append(check("schedule_time", "fail", str(exc)))

    facts = crontab_facts(app, cron_lines, cron_error)
    facts["launchd_job"] = launchd_job(launch_agents_dir)
    if facts["launchd_job"]:
        job = facts["launchd_job"]
        checks.append(check("schedule", "ok", f"launchd: {job['label']} at {job['time'] or 'custom'}" + (" (collects metrics)" if job["collect_metrics"] else " (no --collect-metrics)")))
    if facts["cron_error"]:
        checks.append(check("crontab", "warn", f"Could not inspect crontab: {facts['cron_error']}"))
    elif facts["managed_job"]:
        checks.append(check("crontab", "ok", f"Managed schedule active ({facts['schedule_time'] or 'custom'})."))
    elif facts["unmanaged_jobs"]:
        checks.append(check("crontab", "warn", f"Unmanaged run-daily cron detected ({facts['schedule_time'] or 'custom'}). Run: linkedin-cli automation schedule"))
    elif facts["launchd_job"]:
        checks.append(check("crontab", "ok", "No cron job; the schedule is the launchd job above."))
    else:
        checks.append(check("crontab", "warn", "No run-daily schedule found. Run: linkedin-cli automation schedule"))

    env = facts["env_status"]
    if env.get("exists"):
        has_key = bool(env.get("has_anthropic_api_key"))
        checks.append(check("env_file", "ok" if has_key else "warn", f"{env.get('path')} ({'has' if has_key else 'missing'} ANTHROPIC_API_KEY, mode={env.get('mode') or 'unknown'})"))
    else:
        checks.append(check("env_file", "warn", f"{env.get('path')} not found."))

    shell_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    cron_key = bool(env.get("has_anthropic_api_key"))
    if shell_key and cron_key:
        checks.append(check("anthropic_api_key", "ok", "Configured in shell and cron env file."))
    elif shell_key:
        checks.append(check("anthropic_api_key", "warn", "Configured in shell only; sync cron env for scheduled runs."))
    elif cron_key:
        checks.append(check("anthropic_api_key", "ok", "Configured in cron env file."))
    else:
        checks.append(check("anthropic_api_key", "warn", "Missing. Use: linkedin-cli automation env sync (or set key manually)."))

    if probe_ai:
        # Presence is not validity. Probe the key scheduled runs will actually use
        # (cron.env) and, separately, the shell's, so the two cannot disagree silently.
        for label, key in (("cron env file", extract_exported_env_vars(facts["env_file"]).get("ANTHROPIC_API_KEY", "")), ("shell", os.environ.get("ANTHROPIC_API_KEY", ""))):
            if not key:
                checks.append(check(f"ai_probe_{label.split()[0]}", "warn", f"No key in {label}."))
                continue
            ok, detail = probe_api_key(key)
            checks.append(check(f"ai_probe_{label.split()[0]}", "ok" if ok else "fail", f"{label}: {detail}"))

    checks.append({"name": "run_lock", **health_lock_check(d, lock_ttl_minutes)})

    try:
        completed = load_run_state(d).get("completed_idempotency_keys", [])
        checks.append(check("idempotency_state", "ok", f"{len(completed) if isinstance(completed, list) else 0} key(s) tracked."))
    except Exception as exc:
        checks.append(check("idempotency_state", "warn", f"Could not load state: {exc}"))

    history = load_run_history_entries(d)
    if history:
        checks.append(check("run_history", "ok", f"{len(history)} runs logged; latest status={history[-1].get('status', 'unknown')}."))
    else:
        checks.append(check("run_history", "warn", "No run history yet."))

    webhook = webhook_url.strip() or os.environ.get("LINKEDIN_RUN_NOTIFY_WEBHOOK", "").strip()
    if not webhook:
        checks.append(check("notify_webhook", "ok", "Not configured (optional)."))
    elif webhook.startswith(("https://", "http://")):
        checks.append(check("notify_webhook", "ok", "Looks valid."))
    else:
        checks.append(check("notify_webhook", "warn", "URL should start with http:// or https://"))

    facts["generated_at"] = datetime.now().isoformat(timespec="seconds")
    facts["latest_run"] = history[-1] if history else {}
    return checks, facts


def launchd_job(launch_agents_dir: Path | None = None) -> dict | None:
    """The macOS LaunchAgent that runs `run-daily`, if one is installed.

    The daily run on this machine is a launchd job, not a cron entry, and the
    doctor reported "no schedule" for a schedule that fired every morning.
    Read from the plist text: label, the run-daily command, its hour and
    minute, and whether it collects metrics.
    """
    root = launch_agents_dir or (Path.home() / "Library" / "LaunchAgents")
    if not root.is_dir():
        return None
    for plist in sorted(root.glob("*.plist")):
        try:
            text = plist.read_text()
        except OSError:
            continue
        # Other tools on this machine have their own run-daily LaunchAgents
        # (goodreads does); the job we want names this CLI.
        if "run-daily" not in text or "linkedin" not in text.lower():
            continue
        label = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text)
        hour = re.search(r"<key>Hour</key>\s*<integer>(\d+)</integer>", text)
        minute = re.search(r"<key>Minute</key>\s*<integer>(\d+)</integer>", text)
        return {
            "path": str(plist),
            "label": label.group(1) if label else plist.stem,
            "time": f"{int(hour.group(1)):02d}:{int(minute.group(1)):02d}" if hour and minute else "",
            "collect_metrics": "--collect-metrics" in text,
        }
    return None
