#!/usr/bin/env python3
"""
LinkedIn Job Hunt Assistant - CRM + AI Drafts + Content Research

A local tool to accelerate your job search:
- Track contacts and outreach status
- Generate personalized connection/message drafts with AI
- Research high-engagement content strategies
- Manage your LinkedIn presence strategically
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

import linkedin.data.json_store as json_store
from linkedin.ai.client import AIClientError
from linkedin.constants import (
    ACTIVITY_EMOJI,
    COMPANY_PRIORITIES,
    COMPANY_SIZES,
    CONTACT_SOURCES,
    CONTACT_STATUSES,
    DASHBOARD_PIPELINE,
    PIPELINE_DISPLAY,
    PRIORITY_EMOJI,
    STATUS_EMOJI,
    CompanyPriority,
    ContactStatus,
)
from linkedin.data.factory import create_repos
from linkedin.services.analytics_service import AnalyticsService
from linkedin.services.company_service import CompanyService
from linkedin.services.contact_service import ContactService
from linkedin.services.dashboard_service import DashboardService
from linkedin.services.data_service import DataService
from linkedin.services.discover_service import DiscoverService
from linkedin.services.draft_service import DraftService
from linkedin.services.market_service import MarketService
from linkedin.services.optimizer_service import OptimizerService
from linkedin.services.profile_service import ProfileService
from linkedin.services.research_service import ResearchService
from linkedin.services.template_service import TemplateService

console = Console()


def _app_version() -> str:
    """Read package version, falling back when running from source without install."""
    try:
        return version("linkedin")
    except PackageNotFoundError:
        return "0.0.0"


# Repositories
(
    _contact_repo,
    _company_repo,
    _profile_repo,
    _draft_repo,
    _research_repo,
    _application_repo,
    _conversation_repo,
    _calendar_repo,
    _interview_prep_repo,
) = create_repos()

# Services
_profile_svc = ProfileService(_profile_repo)
_contact_svc = ContactService(_contact_repo, _company_repo)
_company_svc = CompanyService(_company_repo, _contact_repo)
_draft_svc = DraftService(_draft_repo, _contact_repo, _profile_repo)
_discover_svc = DiscoverService(_profile_repo, _company_repo, _contact_repo)
_research_svc = ResearchService(_profile_repo, _research_repo, _draft_repo)
_data_svc = DataService()
_dashboard_svc = DashboardService(_profile_repo, _contact_repo, _company_repo, _draft_repo)
_analytics_svc = AnalyticsService(_contact_repo, _draft_repo)
_market_svc = MarketService(_profile_repo)
_optimizer_svc = OptimizerService(_profile_repo)
_template_svc = TemplateService(_contact_repo, _draft_repo)

NEXT_ACTION_LABELS = {
    "follow_up_overdue": "Follow up (overdue)",
    "follow_up_today": "Follow up (today)",
    "stale_connection_sent": "Follow up on stale request",
    "send_first_message": "Send first message",
    "schedule_call": "Propose a call",
}
NEXT_ACTION_COMMANDS = {
    "follow_up_overdue": "linkedin-cli drafts follow-up {id}",
    "follow_up_today": "linkedin-cli drafts follow-up {id}",
    "stale_connection_sent": "linkedin-cli drafts follow-up {id}",
    "send_first_message": "linkedin-cli drafts message {id}",
    "schedule_call": "linkedin-cli contacts update {id} --status call_scheduled",
}
AUTOMATION_CRON_BEGIN = "# >>> linkedin-cli run-daily managed >>>"
AUTOMATION_CRON_END = "# <<< linkedin-cli run-daily managed <<<"
AUTOMATION_ENV_KEYS = ("ANTHROPIC_API_KEY", "LINKEDIN_RUN_NOTIFY_WEBHOOK")


def _save_daily_plan_recap(
    profile: dict,
    actions: list[dict],
    postings: list[dict],
    template_rows: list[tuple[str, dict]],
    recap_dir: str = "",
) -> Path:
    """Persist a markdown snapshot of the daily plan and return its path."""
    out_dir = Path(recap_dir) if recap_dir else json_store.DATA_DIR / "recaps"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recap_path = out_dir / f"daily_plan_{timestamp}.md"

    lines = [
        "# Daily Plan",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Focus",
        f"- Name: {profile.get('name', 'Not set')}" if profile else "- Name: Not set",
        f"- Target Role: {profile.get('target_role', 'Not set')}" if profile else "- Target Role: Not set",
        "",
        "## Priority Actions",
    ]

    if not actions:
        lines.append("- No urgent contact actions today.")
    else:
        for action in actions:
            command_template = NEXT_ACTION_COMMANDS.get(action["action"], "linkedin-cli contacts view {id}")
            lines.append(
                f"- [{action['priority']}] {action.get('name', 'Unknown')} ({action.get('company', '')})"
                f" | {NEXT_ACTION_LABELS.get(action['action'], action['action'])}"
                f" | `{command_template.format(id=action['contact_id'])}`"
            )

    lines.extend(["", "## Best-Match Opportunities"])
    if not postings:
        lines.append("- No postings above threshold.")
    else:
        for posting in postings:
            reason = posting.get("match_reasons", ["-"])[0]
            lines.append(
                f"- [{posting.get('match_score', 0)}] {posting.get('title', 'Unknown')} @ {posting.get('company', 'Unknown')}"
                f" ({posting.get('location', '-')}) - {reason}"
            )

    lines.extend(["", "## Best Templates"])
    if not template_rows:
        lines.append("- No template performance data yet.")
    else:
        for template_type, template in template_rows:
            lines.append(
                f"- {template_type}: #{template.get('id')} {template.get('name', '')} "
                f"(variant {template.get('variant', 'A')}, rate {template.get('response_rate', '0%')}, "
                f"uses {template.get('usage_count', 0)})"
            )

    recap_path.write_text("\n".join(lines) + "\n")
    return recap_path


def _response_rate_from_counts(template: dict) -> str:
    usage = template.get("usage_count", 0)
    responses = template.get("response_count", 0)
    if not usage:
        return "0%"
    return f"{(responses / usage * 100):.1f}%"


def _build_daily_plan_data(actions_limit: int, postings_limit: int, min_posting_score: int) -> tuple[dict, list[tuple[str, dict]]]:
    profile = _profile_svc.get_profile()
    actions = _contact_svc.get_next_actions(limit=actions_limit)
    postings = _market_svc.list_postings(limit=postings_limit, min_score=min_posting_score)

    template_rows: list[tuple[str, dict]] = []
    template_recommendations: list[dict] = []
    for template_type in ("connection", "message", "follow_up"):
        best = _template_svc.suggest_best(template_type)
        if not best:
            continue
        best_entry = dict(best)
        best_entry["response_rate"] = best_entry.get("response_rate") or _response_rate_from_counts(best_entry)
        template_rows.append((template_type, best_entry))
        template_recommendations.append({"type": template_type, **best_entry})

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "profile": profile,
        "actions": actions,
        "postings": postings,
        "templates": template_recommendations,
    }, template_rows


def _render_daily_plan(data: dict) -> None:
    profile = data["profile"]
    actions = data["actions"]
    postings = data["postings"]
    template_recommendations = data["templates"]

    console.print("\n[bold]📌 Daily Plan[/bold]\n")
    if profile:
        console.print(
            f"[bold]Focus:[/bold] {profile.get('target_role', 'Role not set')} | "
            f"{profile.get('name', 'Profile')}"
        )
    else:
        console.print("[yellow]Set up profile for better recommendations: linkedin-cli profile setup[/yellow]")

    console.print("\n[bold]1) Priority Actions[/bold]")
    if not actions:
        console.print("  [dim]No urgent contact actions today.[/dim]")
    else:
        action_table = Table()
        action_table.add_column("Priority", style="dim")
        action_table.add_column("Contact", style="cyan")
        action_table.add_column("Action", style="yellow")
        action_table.add_column("Command", style="green")
        for action in actions:
            command_template = NEXT_ACTION_COMMANDS.get(action["action"], "linkedin-cli contacts view {id}")
            action_table.add_row(
                str(action["priority"]),
                f"{action['name']} ({action.get('company', '')})".strip(),
                NEXT_ACTION_LABELS.get(action["action"], action["action"]),
                command_template.format(id=action["contact_id"]),
            )
        console.print(action_table)

    console.print("\n[bold]2) Best-Match Opportunities[/bold]")
    if not postings:
        console.print("  [dim]No postings above score threshold. Add/import postings in market commands.[/dim]")
    else:
        postings_table = Table()
        postings_table.add_column("Score", style="green")
        postings_table.add_column("Role", style="cyan")
        postings_table.add_column("Company", style="white")
        postings_table.add_column("Why", style="yellow")
        for posting in postings:
            reason = posting.get("match_reasons", ["-"])[0]
            postings_table.add_row(
                str(posting.get("match_score", 0)),
                posting.get("title", "")[:35],
                posting.get("company", "")[:20],
                reason[:55],
            )
        console.print(postings_table)

    console.print("\n[bold]3) Best Templates[/bold]")
    if not template_recommendations:
        console.print("  [dim]No template performance data yet. Use templates and record responses.[/dim]")
    else:
        template_table = Table()
        template_table.add_column("Type", style="cyan")
        template_table.add_column("Template", style="white")
        template_table.add_column("Variant", style="dim")
        template_table.add_column("Rate", style="green")
        template_table.add_column("Uses", style="yellow")
        for template in template_recommendations:
            template_table.add_row(
                template["type"],
                f"#{template['id']} {template.get('name', '')[:24]}",
                template.get("variant", "A"),
                template.get("response_rate", "0%"),
                str(template.get("usage_count", 0)),
            )
        console.print(template_table)


def _generate_action_drafts(actions: list[dict], save_drafts: bool = False, show_output: bool = True) -> dict:
    generated = 0
    saved = 0
    failed = 0
    drafts: list[dict] = []

    for action in actions:
        contact_id = action["contact_id"]
        error = None
        draft_text = ""
        draft_type = "message"

        if action["action"] in {"follow_up_overdue", "follow_up_today", "stale_connection_sent"}:
            error, draft_text = _draft_svc.generate_follow_up(contact_id, attempt=1)
            draft_type = "follow_up_1"
        elif action["action"] == "send_first_message":
            error, draft_text = _draft_svc.generate_message(
                contact_id,
                context="We're connected, and I want to send a concise first message.",
            )
            draft_type = "message"
        elif action["action"] == "schedule_call":
            error, draft_text = _draft_svc.generate_message(
                contact_id,
                context="They responded recently; propose a short call as the next step.",
            )
            draft_type = "message"
        else:
            continue

        if error:
            failed += 1
            if show_output:
                console.print(f"[yellow]Could not generate draft for contact #{contact_id}: {error}[/yellow]")
            continue

        generated += 1
        draft_entry = {
            "contact_id": contact_id,
            "name": action.get("name", ""),
            "generated_from": action["action"],
            "draft_type": draft_type,
            "content": draft_text,
        }
        drafts.append(draft_entry)

        if show_output:
            console.print(f"\n[bold cyan]Auto Draft for #{contact_id} ({action['name']}):[/bold cyan]")
            console.print(Panel(draft_text, border_style="cyan"))

        if save_drafts:
            _draft_svc.save_draft(contact_id, draft_type, draft_text, generated_from=action["action"])
            saved += 1

    if show_output:
        console.print(
            f"\n[green]Generated {generated} draft(s)[/green]"
            + (f", saved {saved}" if save_drafts else "")
            + (f", failed {failed}" if failed else "")
        )

    return {"generated": generated, "saved": saved, "failed": failed, "drafts": drafts}


def _render_generated_drafts(draft_summary: dict) -> None:
    drafts = draft_summary.get("drafts", [])
    if not drafts:
        console.print("\n[bold]4) Generated Drafts[/bold]")
        console.print("  [dim]No drafts generated from current actions.[/dim]")
        return

    console.print("\n[bold]4) Generated Drafts[/bold]")
    for draft in drafts:
        console.print(
            f"[bold cyan]Auto Draft for #{draft['contact_id']} ({draft.get('name', 'Unknown')}):[/bold cyan]"
        )
        console.print(Panel(draft["content"], border_style="cyan"))

    generated = draft_summary.get("generated", 0)
    saved = draft_summary.get("saved", 0)
    failed = draft_summary.get("failed", 0)
    console.print(
        f"\n[green]Generated {generated} draft(s)[/green]"
        + (f", saved {saved}" if saved else "")
        + (f", failed {failed}" if failed else "")
    )


def _emit_daily_run_output(data: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    _render_daily_plan(data)
    draft_summary = data.get("drafts", {})
    if draft_summary.get("generated", 0) or draft_summary.get("drafts"):
        _render_generated_drafts(draft_summary)

    recap_path = data.get("recap_path")
    if recap_path:
        console.print(f"\n[green]✓ Saved recap: {recap_path}[/green]")


def _run_daily_cycle(
    actions_limit: int,
    postings_limit: int,
    min_posting_score: int,
    save_recap: bool = False,
    recap_dir: str = "",
    generate_drafts: bool = False,
    save_drafts: bool = False,
    show_draft_output: bool = True,
) -> dict:
    data, template_rows = _build_daily_plan_data(actions_limit, postings_limit, min_posting_score)

    if generate_drafts or save_drafts:
        data["drafts"] = _generate_action_drafts(
            data["actions"],
            save_drafts=save_drafts,
            show_output=show_draft_output,
        )
    else:
        data["drafts"] = {"generated": 0, "saved": 0, "failed": 0, "drafts": []}

    if save_recap:
        recap_path = _save_daily_plan_recap(
            data["profile"],
            data["actions"],
            data["postings"],
            template_rows,
            recap_dir=recap_dir,
        )
        data["recap_path"] = str(recap_path)

    return data


def _parse_schedule_time(schedule_time: str) -> tuple[int, int]:
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


def _scheduled_run_for_date(schedule_time: str, day: datetime.date) -> datetime:
    hour, minute = _parse_schedule_time(schedule_time)
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


def _next_scheduled_run(schedule_time: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    candidate = _scheduled_run_for_date(schedule_time, current.date())

    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate


def _default_scheduler_runner_tokens() -> list[str]:
    uv_path = shutil.which("uv")
    if uv_path:
        return [uv_path, "run", "linkedin-cli"]

    cli_path = shutil.which("linkedin-cli")
    if cli_path:
        return [cli_path]

    return [sys.executable, "-m", "linkedin.cli"]


def _runner_tokens_from_option(runner: str) -> tuple[list[str], str | None]:
    if not runner.strip():
        return _default_scheduler_runner_tokens(), None

    try:
        tokens = shlex.split(runner)
    except ValueError as exc:
        return [], f"Invalid --runner value: {exc}"

    if not tokens:
        return [], "Invalid --runner value: expected a command."
    return tokens, None


def _build_scheduled_run_daily_tokens(
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


def _default_automation_env_file() -> Path:
    return json_store.DATA_DIR / "cron.env"


def _sanitize_env_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "_", str(name).strip().upper())


def _extract_exported_env_vars(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    env_vars: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        key = _sanitize_env_key(key)
        if not key:
            continue
        value = value.strip().strip("'").strip('"')
        env_vars[key] = value
    return env_vars


def _write_env_file(path: Path, updates: dict[str, str]) -> tuple[bool, dict[str, str], str | None]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return False, {}, str(exc)

    current = _extract_exported_env_vars(path)
    for key, value in updates.items():
        sanitized_key = _sanitize_env_key(key)
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


def _env_file_status(path: Path) -> dict:
    exists = path.exists()
    if not exists:
        return {
            "path": str(path),
            "exists": False,
            "has_anthropic_api_key": False,
            "key_count": 0,
            "mode": "",
        }

    env_vars = _extract_exported_env_vars(path)
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


def _build_cron_shell_command(workdir: Path, run_tokens: list[str], env_file: Path | None = None) -> str:
    segments = [f"cd {shlex.quote(str(workdir))}"]
    if env_file is not None:
        env_file_str = shlex.quote(str(env_file))
        segments.append(f"if [ -f {env_file_str} ]; then set -a; source {env_file_str}; set +a; fi")
    segments.append(shlex.join(run_tokens))
    inner = " && ".join(segments)
    return f"/bin/zsh -lc {shlex.quote(inner)}"


def _build_managed_cron_job_line(
    schedule_time: str,
    cron_command: str,
    stdout_log: Path,
    stderr_log: Path,
) -> str:
    hour, minute = _parse_schedule_time(schedule_time)
    return (
        f"{minute} {hour} * * * {cron_command} "
        f">> {shlex.quote(str(stdout_log))} 2>> {shlex.quote(str(stderr_log))}"
    )


def _build_managed_cron_block(job_line: str) -> list[str]:
    timestamp = datetime.now().isoformat(timespec="seconds")
    return [
        AUTOMATION_CRON_BEGIN,
        f"# Managed by linkedin-cli automation schedule ({timestamp})",
        job_line,
        AUTOMATION_CRON_END,
    ]


def _strip_managed_cron_block(lines: list[str]) -> tuple[list[str], bool]:
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


def _extract_managed_cron_job_line(lines: list[str]) -> str:
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


def _find_unmanaged_run_daily_cron_jobs(lines: list[str]) -> list[str]:
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


def _strip_unmanaged_run_daily_cron_jobs(lines: list[str]) -> tuple[list[str], int]:
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


def _strip_legacy_scheduler_comment_lines(lines: list[str]) -> tuple[list[str], int]:
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


def _cron_schedule_time_from_job_line(job_line: str) -> str:
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


def _cron_env_file_from_job_line(job_line: str) -> Path | None:
    if not job_line:
        return None

    match = re.search(r"source\s+([^;]+);", job_line)
    if not match:
        return None

    candidate = match.group(1).strip().strip("'").strip('"')
    if not candidate:
        return None
    return Path(candidate).expanduser()


def _read_user_crontab_lines() -> tuple[list[str], str | None]:
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


def _write_user_crontab_lines(lines: list[str]) -> str | None:
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
        return (result.stderr or result.stdout or "").strip() or f"crontab install failed with exit code {result.returncode}."
    return None


def _load_run_state() -> dict:
    raw = json_store.load_json(
        json_store.RUN_DAILY_STATE_FILE,
        {"completed_idempotency_keys": [], "alerts": {}},
    )
    if not isinstance(raw, dict):
        return {"completed_idempotency_keys": [], "alerts": {}}

    completed_raw = raw.get("completed_idempotency_keys", [])
    if not isinstance(completed_raw, list):
        completed_raw = []

    completed: list[dict] = []
    for item in completed_raw:
        if isinstance(item, str):
            completed.append({"key": item, "completed_at": ""})
            continue
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            completed.append({
                "key": key,
                "completed_at": str(item.get("completed_at", "")),
                "run_id": str(item.get("run_id", "")),
            })

    alerts_raw = raw.get("alerts", {})
    if not isinstance(alerts_raw, dict):
        alerts_raw = {}

    last_failure_streak_notified = alerts_raw.get("last_failure_streak_notified", 0)
    try:
        last_failure_streak_notified = int(last_failure_streak_notified)
    except (TypeError, ValueError):
        last_failure_streak_notified = 0

    return {
        "completed_idempotency_keys": completed[-1000:],
        "alerts": {
            "last_failure_streak_notified": max(0, last_failure_streak_notified),
        },
    }


def _save_run_state(state: dict) -> None:
    json_store.save_json(json_store.RUN_DAILY_STATE_FILE, state)


def _failure_streak(entries: list[dict]) -> int:
    streak = 0
    for entry in reversed(entries):
        status = str(entry.get("status", ""))
        if status == "failed":
            streak += 1
            continue
        if status == "success":
            break
    return streak


def _get_last_failure_streak_notified() -> int:
    state = _load_run_state()
    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict):
        return 0
    try:
        return max(0, int(alerts.get("last_failure_streak_notified", 0)))
    except (TypeError, ValueError):
        return 0


def _set_last_failure_streak_notified(streak: int) -> None:
    state = _load_run_state()
    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict):
        alerts = {}
    alerts["last_failure_streak_notified"] = max(0, int(streak))
    state["alerts"] = alerts
    _save_run_state(state)


def _idempotency_key_seen(key: str) -> bool:
    if not key:
        return False
    state = _load_run_state()
    completed = state.get("completed_idempotency_keys", [])
    return any(item.get("key") == key for item in completed if isinstance(item, dict))


def _record_idempotency_key(key: str, run_id: str) -> None:
    if not key:
        return
    state = _load_run_state()
    completed = state.get("completed_idempotency_keys", [])
    if not isinstance(completed, list):
        completed = []
    completed.append({
        "key": key,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
    })
    state["completed_idempotency_keys"] = completed[-1000:]
    _save_run_state(state)


def _append_run_log(entry: dict) -> None:
    json_store.ensure_dirs()
    path = json_store.RUN_DAILY_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def _load_run_history_entries() -> list[dict]:
    path = json_store.RUN_DAILY_LOG_FILE
    if not path.exists():
        return []

    entries: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            entries.append(raw)
    return entries


def _entry_timestamp(entry: dict) -> datetime | None:
    return _parse_iso_datetime(str(entry.get("finished_at") or entry.get("started_at") or ""))


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _health_lock_check(lock_ttl_minutes: int) -> dict:
    lock_path = json_store.RUN_DAILY_LOCK_FILE
    if not lock_path.exists():
        return {"status": "ok", "detail": "No active run lock."}

    now = datetime.now()
    max_age = timedelta(minutes=max(1, lock_ttl_minutes))
    pid = ""
    created_at = ""
    try:
        payload = json.loads(lock_path.read_text())
        if isinstance(payload, dict):
            pid = str(payload.get("pid", ""))
            created_at = str(payload.get("created_at", ""))
    except Exception:
        pass

    created = _parse_iso_datetime(created_at)
    if created is None:
        created = datetime.fromtimestamp(lock_path.stat().st_mtime)

    age_seconds = max(0, int((now - created).total_seconds()))
    if now - created > max_age:
        return {
            "status": "warn",
            "detail": f"Stale lock detected (age={age_seconds}s).",
        }

    pid_part = f"pid={pid}, " if pid else ""
    return {
        "status": "warn",
        "detail": f"Active lock ({pid_part}age={age_seconds}s).",
    }


def _acquire_run_lock(lock_ttl_minutes: int = 180) -> tuple[bool, str]:
    json_store.ensure_dirs()
    lock_path = json_store.RUN_DAILY_LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    max_age = timedelta(minutes=max(1, lock_ttl_minutes))

    if lock_path.exists():
        stale = False
        holder_info = "unknown process"
        try:
            payload = json.loads(lock_path.read_text())
            if isinstance(payload, dict):
                pid = payload.get("pid")
                created_at = _parse_iso_datetime(str(payload.get("created_at", "")))
                if pid:
                    holder_info = f"pid={pid}"
                if created_at:
                    age = now - created_at
                    if age > max_age:
                        stale = True
                    else:
                        holder_info = f"{holder_info}, age={int(age.total_seconds())}s"
        except Exception:
            pass

        if not stale:
            try:
                age = now - datetime.fromtimestamp(lock_path.stat().st_mtime)
                if age > max_age:
                    stale = True
            except OSError:
                pass

        if stale:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                return False, "Failed to clear stale lock file."
        else:
            return False, f"Another run is in progress ({holder_info})."

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, "Another run is already in progress."

    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "pid": os.getpid(),
            "created_at": now.isoformat(timespec="seconds"),
        }))
    return True, ""


def _release_run_lock() -> None:
    try:
        json_store.RUN_DAILY_LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _effective_idempotency_key(
    key: str,
    watch_mode: bool,
    schedule_time: str,
    run_at: datetime,
) -> str:
    trimmed = key.strip()
    day_key = run_at.date().isoformat()
    if trimmed:
        if watch_mode:
            return f"{trimmed}:{day_key}"
        return trimmed
    if watch_mode:
        return f"schedule:{schedule_time}:{day_key}"
    return ""


def _send_run_notification(webhook_url: str, payload: dict) -> str | None:
    if not webhook_url:
        return None

    body = {
        "text": (
            f"linkedin-cli run-daily {payload.get('status', 'unknown')} "
            f"(run_id={payload.get('run_id', '-')}, trigger={payload.get('trigger', '-')})"
        ),
        "payload": payload,
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.URLError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return str(exc)
    return None


def _run_daily_with_reliability(
    *,
    trigger: str,
    run_at: datetime,
    idempotency_key: str,
    allow_duplicate: bool,
    watch_mode: bool,
    schedule_time: str,
    actions_limit: int,
    postings_limit: int,
    min_posting_score: int,
    save_recap: bool,
    recap_dir: str,
    generate_drafts: bool,
    save_drafts: bool,
    notify_webhook: str,
    notify_on_success: bool,
    notify_on_failure: bool,
    failure_streak_threshold: int,
    notify_on_recovery: bool,
) -> dict:
    run_id = uuid.uuid4().hex
    started_at = datetime.now()
    effective_key = _effective_idempotency_key(idempotency_key, watch_mode, schedule_time, run_at)

    if effective_key and not allow_duplicate and _idempotency_key_seen(effective_key):
        result = {
            "status": "skipped_duplicate",
            "run_id": run_id,
            "trigger": trigger,
            "idempotency_key": effective_key,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "reason": "Idempotency key already completed.",
        }
        _append_run_log(result)
        return result

    streak_threshold = max(1, int(failure_streak_threshold))

    try:
        data = _run_daily_cycle(
            actions_limit=actions_limit,
            postings_limit=postings_limit,
            min_posting_score=min_posting_score,
            save_recap=save_recap,
            recap_dir=recap_dir,
            generate_drafts=generate_drafts,
            save_drafts=save_drafts,
            show_draft_output=False,
        )
    except Exception as exc:  # pragma: no cover - exercised via CLI failure paths
        failed = {
            "status": "failed",
            "run_id": run_id,
            "trigger": trigger,
            "idempotency_key": effective_key,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "error": str(exc),
        }
        _append_run_log(failed)
        history = _load_run_history_entries()
        current_streak = _failure_streak(history)
        failed["failure_streak"] = current_streak

        notification_error = None
        streak_mode = streak_threshold > 1 and current_streak >= streak_threshold
        if (
            notify_webhook
            and notify_on_failure
            and streak_mode
        ):
            last_notified = _get_last_failure_streak_notified()
            if current_streak > last_notified:
                alert_payload = dict(failed)
                alert_payload["status"] = "failed_streak"
                alert_payload["failure_streak_threshold"] = streak_threshold
                notification_error = _send_run_notification(notify_webhook, alert_payload)
                if not notification_error:
                    _set_last_failure_streak_notified(current_streak)

        if (not streak_mode) and notification_error is None and notify_webhook and notify_on_failure:
            notification_error = _send_run_notification(notify_webhook, failed)

        if notification_error:
            failed["notification_error"] = notification_error
        return failed

    history_before_success = _load_run_history_entries()
    prior_failure_streak = _failure_streak(history_before_success)
    finished_at = datetime.now()
    data["status"] = "success"
    data["run_id"] = run_id
    data["trigger"] = trigger
    data["idempotency_key"] = effective_key
    data["started_at"] = started_at.isoformat(timespec="seconds")
    data["finished_at"] = finished_at.isoformat(timespec="seconds")

    log_entry = {
        "status": "success",
        "run_id": run_id,
        "trigger": trigger,
        "idempotency_key": effective_key,
        "started_at": data["started_at"],
        "finished_at": data["finished_at"],
        "actions_count": len(data.get("actions", [])),
        "postings_count": len(data.get("postings", [])),
        "templates_count": len(data.get("templates", [])),
        "drafts_generated": int(data.get("drafts", {}).get("generated", 0)),
        "drafts_saved": int(data.get("drafts", {}).get("saved", 0)),
        "recap_path": data.get("recap_path", ""),
    }
    _append_run_log(log_entry)

    if effective_key:
        _record_idempotency_key(effective_key, run_id)

    if prior_failure_streak > 0:
        data["recovered_from_failure_streak"] = prior_failure_streak
    _set_last_failure_streak_notified(0)

    notify_error = None
    if notify_webhook and streak_threshold > 1 and prior_failure_streak >= streak_threshold and notify_on_recovery:
        recovery_payload = dict(log_entry)
        recovery_payload["status"] = "recovered_after_failure_streak"
        recovery_payload["prior_failure_streak"] = prior_failure_streak
        recovery_payload["failure_streak_threshold"] = streak_threshold
        notify_error = _send_run_notification(notify_webhook, recovery_payload)
    elif notify_webhook and notify_on_success:
        notify_error = _send_run_notification(notify_webhook, log_entry)

    if notify_error:
        data["notification_error"] = notify_error

    return data


def _emit_run_status(result: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    status = result.get("status", "unknown")
    if status == "skipped_duplicate":
        console.print(
            f"[yellow]Skipped duplicate run for key '{result.get('idempotency_key', '')}'.[/yellow]"
        )
        return
    if status == "skipped_locked":
        console.print(f"[yellow]{result.get('reason', 'Run skipped due to lock.')}[/yellow]")
        return
    if status == "failed":
        console.print(f"[red]run-daily failed: {result.get('error', 'Unknown error')}[/red]")
        if result.get("notification_error"):
            console.print(f"[yellow]Notification failed: {result['notification_error']}[/yellow]")


def _execute_run_with_retries(
    *,
    retry_attempts: int,
    retry_backoff_seconds: float,
    as_json: bool,
    trigger: str,
    run_at: datetime,
    idempotency_key: str,
    allow_duplicate: bool,
    watch_mode: bool,
    schedule_time: str,
    actions_limit: int,
    postings_limit: int,
    min_posting_score: int,
    save_recap: bool,
    recap_dir: str,
    generate_drafts: bool,
    save_drafts: bool,
    notify_webhook: str,
    notify_on_success: bool,
    failure_streak_threshold: int,
    notify_on_recovery: bool,
) -> dict:
    max_attempts = max(1, retry_attempts + 1)
    result: dict = {}
    for attempt in range(max_attempts):
        result = _run_daily_with_reliability(
            trigger=trigger,
            run_at=run_at,
            idempotency_key=idempotency_key,
            allow_duplicate=allow_duplicate,
            watch_mode=watch_mode,
            schedule_time=schedule_time,
            actions_limit=actions_limit,
            postings_limit=postings_limit,
            min_posting_score=min_posting_score,
            save_recap=save_recap,
            recap_dir=recap_dir,
            generate_drafts=generate_drafts,
            save_drafts=save_drafts,
            notify_webhook=notify_webhook,
            notify_on_success=notify_on_success,
            notify_on_failure=(attempt == max_attempts - 1),
            failure_streak_threshold=failure_streak_threshold,
            notify_on_recovery=notify_on_recovery,
        )
        result["attempts"] = attempt + 1
        if result.get("status") != "failed":
            if attempt > 0:
                result["recovered_after_retries"] = attempt
            return result

        if attempt >= max_attempts - 1:
            return result

        sleep_for = max(0.0, retry_backoff_seconds) * (2 ** attempt)
        if not as_json:
            console.print(
                f"[yellow]Run failed (attempt {attempt + 1}/{max_attempts}); retrying in {sleep_for:.1f}s...[/yellow]"
            )
        if sleep_for > 0:
            time.sleep(sleep_for)

    return result


# =============================================================================
# CLI Setup
# =============================================================================

@click.group()
@click.version_option(version=_app_version(), prog_name="linkedin-cli")
def cli():
    """
    LinkedIn Job Hunt Assistant

    \b
    A local CRM + AI-powered tool to accelerate your job search:
    - Track contacts and outreach status
    - Generate personalized drafts with AI
    - Research high-engagement content
    - Plan your LinkedIn strategy

    \b
    Quick Start:
      1. linkedin-cli profile setup     # Add your info
      2. linkedin-cli contacts add      # Add target contacts
      3. linkedin-cli drafts connection <contact-id>   # AI writes your outreach
    """
    pass


# =============================================================================
# Profile Commands
# =============================================================================

@cli.group()
def profile():
    """Manage your profile info (used for AI personalization)."""
    pass


@profile.command("setup")
def profile_setup():
    """Set up your profile for personalized drafts."""
    console.print("\n[bold]Profile Setup[/bold]")
    console.print("This info helps AI generate personalized outreach.\n")

    existing = _profile_svc.get_profile()

    data = {
        "name": click.prompt("Your name", default=existing.get("name", "")),
        "headline": click.prompt("Your headline/title", default=existing.get("headline", "")),
        "target_role": click.prompt("Target role you're seeking", default=existing.get("target_role", "")),
        "skills": click.prompt("Key skills (comma-separated)", default=existing.get("skills", "")),
        "experience_summary": click.prompt("Brief experience summary", default=existing.get("experience_summary", "")),
        "unique_value": click.prompt("What makes you unique?", default=existing.get("unique_value", "")),
        "industries": click.prompt("Target industries (comma-separated)", default=existing.get("industries", "")),
        "location": click.prompt("Your location", default=existing.get("location", "")),
    }

    _profile_svc.save_profile(data)
    console.print("\n[green]✓ Profile saved![/green]")


@profile.command("show")
def profile_show():
    """Display your saved profile."""
    data = _profile_svc.get_profile()

    if not data:
        console.print("[yellow]No profile set up. Run: linkedin-cli profile setup[/yellow]")
        return

    table = Table(title="Your Profile")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    for key, value in data.items():
        if key != "updated_at":
            table.add_row(key.replace("_", " ").title(), str(value))

    console.print(table)


# =============================================================================
# Companies Commands
# =============================================================================

@cli.group()
def companies():
    """Track target companies for networking."""
    pass


@companies.command("add")
@click.option("--name", "-n", prompt="Company name", help="Company name")
@click.option("--industry", "-i", prompt="Industry", help="Industry/sector")
@click.option("--size", "-s", type=click.Choice(COMPANY_SIZES), default="51-200", help="Company size")
@click.option("--linkedin", "-l", default="", help="LinkedIn company URL")
@click.option("--website", "-w", default="", help="Company website")
@click.option("--why", prompt="Why target this company?", help="Why target this company")
@click.option("--priority", "-p", type=click.Choice(COMPANY_PRIORITIES), default="medium", help="Priority level")
def companies_add(name, industry, size, linkedin, website, why, priority):
    """Add a new target company."""
    company = _company_svc.add_company(name, industry, size, linkedin, website, why, priority)
    console.print(f"\n[green]✓ Added company: {name} ({industry})[/green]")
    console.print(f"  ID: #{company['id']} | Priority: {priority}")


@companies.command("list")
@click.option("--priority", "-p", type=click.Choice(COMPANY_PRIORITIES + ["all"]), default="all", help="Filter by priority")
@click.option("--industry", "-i", default=None, help="Filter by industry")
def companies_list_cmd(priority, industry):
    """List all target companies."""
    result = _company_svc.list_companies(priority, industry)

    if not result:
        console.print("[yellow]No companies yet. Run: linkedin-cli companies add[/yellow]")
        return

    table = Table(title=f"Target Companies ({len(result)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Industry", style="white")
    table.add_column("Size", style="dim")
    table.add_column("Priority", style="yellow")
    table.add_column("Contacts", style="green")

    for c in result:
        emoji = PRIORITY_EMOJI.get(CompanyPriority(c.get("priority", "medium")), "")
        num_contacts = c.get("contact_count", 0)
        table.add_row(
            str(c["id"]),
            c["name"],
            c.get("industry", ""),
            c.get("size", ""),
            f"{emoji} {c.get('priority', 'medium')}",
            str(num_contacts) if num_contacts else "-",
        )

    console.print(table)


@companies.command("view")
@click.argument("company_id", type=int)
def companies_view(company_id):
    """View detailed info for a company."""
    result = _company_svc.get_company(company_id)
    if not result:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    company_contacts = result.get("contacts", [])
    key_people = result.get("key_people_to_find", [])
    key_people_str = ", ".join(key_people) if key_people else "Not specified"

    console.print(Panel(f"""
[bold]{result['name']}[/bold]
{result.get('industry', 'Industry not set')} | {result.get('size', 'Size not set')} employees

[cyan]LinkedIn:[/cyan] {result.get('linkedin_url') or 'Not set'}
[cyan]Website:[/cyan] {result.get('website') or 'Not set'}
[cyan]Priority:[/cyan] {result.get('priority', 'medium')}
[cyan]Added:[/cyan] {result['created_at'][:10]}

[bold]Why Target:[/bold]
{result.get('why_target', 'Not specified')}

[bold]Key People to Find:[/bold]
{key_people_str}

[bold]Notes:[/bold]
{result.get('notes') or 'No notes'}

[bold]Contacts ({len(company_contacts)}):[/bold]
{chr(10).join([f"  - {c['name']} - {c['title']}" for c in company_contacts]) if company_contacts else '  None yet'}
    """, title=f"Company #{company_id}"))


@companies.command("update")
@click.argument("company_id", type=int)
@click.option("--priority", "-p", type=click.Choice(COMPANY_PRIORITIES), help="Update priority")
@click.option("--notes", "-n", help="Add notes")
@click.option("--add-role", "-r", help="Add a role to find")
@click.option("--linkedin", "-l", help="Update LinkedIn URL")
@click.option("--website", "-w", help="Update website")
def companies_update(company_id, priority, notes, add_role, linkedin, website):
    """Update a company's info."""
    result = _company_svc.update_company(company_id, priority, notes, add_role, linkedin, website)
    if not result:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Updated company #{company_id}[/green]")


@companies.command("delete")
@click.argument("company_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to delete this company?")
def companies_delete(company_id):
    """Delete a company."""
    result = _company_svc.delete_company(company_id)
    if not result:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Deleted company #{company_id}: {result['name']}[/green]")


@companies.command("contacts")
@click.argument("company_id", type=int)
def companies_contacts(company_id):
    """List contacts at a company."""
    company, company_contacts = _company_svc.get_company_contacts(company_id)

    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    if not company_contacts:
        console.print(f"[yellow]No contacts at {company['name']} yet.[/yellow]")
        console.print(f"Add one with: linkedin-cli contacts add --company-id {company_id}")
        return

    table = Table(title=f"Contacts at {company['name']} ({len(company_contacts)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")

    for c in company_contacts:
        emoji = STATUS_EMOJI.get(ContactStatus(c["status"]), "")
        table.add_row(
            str(c["id"]),
            c["name"],
            c["title"][:30],
            f"{emoji} {c['status'].replace('_', ' ')}",
        )

    console.print(table)


# =============================================================================
# Contacts Commands
# =============================================================================

@cli.group()
def contacts():
    """CRM for tracking target contacts and outreach status."""
    pass


@contacts.command("add")
@click.option("--name", "-n", prompt="Contact name", help="Full name")
@click.option("--title", "-t", prompt="Their title", help="Job title")
@click.option("--company", "-c", prompt="Company", help="Company name")
@click.option("--linkedin", "-l", prompt="LinkedIn URL", help="Profile URL")
@click.option("--notes", prompt="Notes (why contact them?)", default="", help="Why reach out?")
@click.option("--company-id", type=int, default=None, help="Link to a tracked company")
@click.option("--email", "-e", default="", help="Email address")
@click.option("--source", type=click.Choice(CONTACT_SOURCES), default="linkedin_search", help="How you found them")
@click.option("--referral-id", type=int, default=None, help="Contact ID who referred them")
def contacts_add(name, title, company, linkedin, notes, company_id, email, source, referral_id):
    """Add a new contact to track."""
    result = _contact_svc.add_contact(name, title, company, linkedin, notes, company_id, email, source, referral_id)

    if isinstance(result, str):
        console.print(f"[red]{result}[/red]")
        return

    console.print(f"\n[green]✓ Added: {name} ({title} at {result['company']})[/green]")
    console.print(f"  ID: #{result['id']}")
    if company_id:
        console.print(f"  Linked to company #{company_id}")


@contacts.command("list")
@click.option("--status", "-s", type=click.Choice(CONTACT_STATUSES + ["all"]), default="all")
@click.option("--company", "-c", default=None, help="Filter by company name")
@click.option("--company-id", type=int, default=None, help="Filter by company ID")
@click.option("--source", type=click.Choice(CONTACT_SOURCES + ["all"]), default="all", help="Filter by source")
def contacts_list(status, company, company_id, source):
    """List all contacts."""
    from datetime import datetime

    filtered = _contact_svc.list_contacts(status, company, company_id, source)

    if not filtered:
        console.print("[yellow]No contacts yet. Run: linkedin-cli contacts add[/yellow]")
        return

    table = Table(title=f"Contacts ({len(filtered)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Company", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Follow Up", style="dim")

    for c in filtered:
        emoji = STATUS_EMOJI.get(ContactStatus(c["status"]), "")
        follow_up = c.get("follow_up_date", "")
        if follow_up:
            try:
                follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
                if follow_up_date < datetime.now().date():
                    follow_up = f"[red]⚠ {follow_up}[/red]"
            except (ValueError, AttributeError):
                pass
        table.add_row(
            str(c["id"]),
            c["name"],
            c["title"][:30],
            c["company"],
            f"{emoji} {c['status'].replace('_', ' ')}",
            follow_up or "-",
        )

    console.print(table)


@contacts.command("update")
@click.argument("contact_id", type=int)
@click.option("--status", "-s", type=click.Choice(CONTACT_STATUSES), help="Update status")
@click.option("--notes", "-n", help="Add notes")
@click.option("--follow-up", "-f", help="Set follow-up date (YYYY-MM-DD)")
@click.option("--email", "-e", help="Set email address")
def contacts_update(contact_id, status, notes, follow_up, email):
    """Update a contact's status or notes."""
    result = _contact_svc.update_contact(contact_id, status, notes, follow_up, email)
    if not result:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    feedback = None
    if status:
        feedback = _template_svc.auto_record_outcome(contact_id, status)

    console.print(f"[green]✓ Updated contact #{contact_id}[/green]")
    if feedback and feedback.get("recorded"):
        console.print(
            "[green]"
            f"✓ Auto-recorded template outcome for #{feedback['template_id']} "
            f"({feedback.get('template_name', 'template')})"
            "[/green]"
        )


@contacts.command("view")
@click.argument("contact_id", type=int)
def contacts_view(contact_id):
    """View detailed info for a contact."""
    result = _contact_svc.view_contact(contact_id)
    if not result:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    company_link = ""
    if result.get("company_id"):
        company_link = f" (Company #{result['company_id']})"

    referrer_info = ""
    referrer = result.get("referrer")
    if referrer:
        referrer_info = f"\n[cyan]Referred by:[/cyan] {referrer['name']}"

    email_info = f"\n[cyan]Email:[/cyan] {result.get('email')}" if result.get("email") else ""
    source_info = f"\n[cyan]Source:[/cyan] {result.get('source', 'unknown').replace('_', ' ')}"

    console.print(Panel(f"""
[bold]{result['name']}[/bold]
{result['title']} at {result['company']}{company_link}

[cyan]LinkedIn:[/cyan] {result['linkedin_url']}{email_info}
[cyan]Status:[/cyan] {result['status'].replace('_', ' ')}{source_info}{referrer_info}
[cyan]Added:[/cyan] {result['created_at'][:10]}
[cyan]Last Contact:[/cyan] {result.get('last_contact', 'Never')[:10] if result.get('last_contact') else 'Never'}
[cyan]Follow Up:[/cyan] {result.get('follow_up_date', 'Not set')}

[bold]Notes:[/bold]
{result.get('notes', 'No notes')}
    """, title=f"Contact #{contact_id}"))


@contacts.command("stats")
def contacts_stats():
    """Show outreach statistics."""
    stats = _contact_svc.get_stats()

    if stats["total"] == 0:
        console.print("[yellow]No contacts yet[/yellow]")
        return

    console.print("\n[bold]Outreach Pipeline[/bold]\n")

    total = stats["total"]
    for status, label in PIPELINE_DISPLAY:
        count = stats["status_counts"].get(status.value, 0)
        bar = "█" * (count * 20 // total) if total > 0 else ""
        console.print(f"  {label:25} {bar} {count}")

    console.print("\n[bold]Conversion Rates[/bold]")
    sc = stats["status_counts"]
    if sc.get("connection_sent", 0) > 0:
        rate = sc.get("connected", 0) / sc["connection_sent"] * 100
        console.print(f"  Connection acceptance: {rate:.0f}%")
    if sc.get("messaged", 0) > 0:
        rate = sc.get("responded", 0) / sc["messaged"] * 100
        console.print(f"  Message response rate: {rate:.0f}%")


@contacts.command("activity")
@click.argument("contact_id", type=int)
def contacts_activity(contact_id):
    """View activity log for a contact."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    activities = contact.get("activities", [])

    console.print(f"\n[bold]Activity Log for {contact['name']}[/bold]\n")

    if not activities:
        console.print("[dim]No activities recorded yet.[/dim]")
        console.print("\nActivities are logged when you update contact status.")
        return

    for activity in reversed(activities):
        emoji = ACTIVITY_EMOJI.get(activity.get("type", ""), "•")
        date = activity.get("date", "")[:10]
        activity_type = activity.get("type", "unknown").replace("_", " ")
        note = activity.get("note", "")
        console.print(f"  {emoji} [{date}] {activity_type}")
        if note:
            console.print(f"      {note}")


@contacts.command("link-company")
@click.argument("contact_id", type=int)
@click.argument("company_id", type=int)
def contacts_link_company(contact_id, company_id):
    """Link a contact to a company."""
    error = _contact_svc.link_company(contact_id, company_id)
    if error:
        console.print(f"[red]{error}[/red]")
        return

    contact = _contact_svc.get_contact(contact_id)
    company = _company_svc.companies.get(company_id)
    console.print(f"[green]✓ Linked {contact['name']} to {company['name']}[/green]")


@contacts.command("due")
@click.option("--days", "-d", type=int, default=0, help="Show follow-ups due within N days (0 = overdue only)")
def contacts_due(days):
    """Show contacts with overdue or upcoming follow-ups."""
    all_contacts = _contact_svc.list_contacts()
    if not all_contacts:
        console.print("[yellow]No contacts yet[/yellow]")
        return

    due_data = _contact_svc.get_due_contacts(days)

    overdue = due_data["overdue"]
    due_today = due_data["due_today"]
    upcoming = due_data["upcoming"]
    stale = due_data["stale"]

    if not overdue and not due_today and not upcoming and not stale:
        console.print("[green]✓ No overdue follow-ups![/green]")
        return

    if overdue:
        console.print("\n[bold red]⚠️  Overdue Follow-ups[/bold red]\n")
        for contact, follow_date, days_overdue in overdue:
            console.print(f"  ! {contact['name']} ({contact['company']}) - [red]{days_overdue} days overdue[/red]")
            console.print(f"    Status: {contact['status'].replace('_', ' ')}")
            console.print(f"    → linkedin-cli drafts follow-up {contact['id']}\n")

    if due_today:
        console.print("\n[bold yellow]📅 Due Today[/bold yellow]\n")
        for contact, follow_date, _ in due_today:
            console.print(f"  ! {contact['name']} ({contact['company']})")
            console.print(f"    Status: {contact['status'].replace('_', ' ')}")
            console.print(f"    → linkedin-cli drafts follow-up {contact['id']}\n")

    if upcoming:
        console.print("\n[bold cyan]📆 Upcoming Follow-ups[/bold cyan]\n")
        for contact, follow_date, days_until in upcoming:
            console.print(f"  - {contact['name']} ({contact['company']}) - [dim]in {-days_until} days[/dim]")

    if stale:
        console.print("\n[bold yellow]📤 Stale Connection Requests (>14 days)[/bold yellow]\n")
        for contact, days_since in stale:
            console.print(f"  ! {contact['name']} ({contact['company']}) - {days_since} days ago")
            console.print("    → Consider sending a follow-up or finding another contact\n")


@contacts.command("next-actions")
@click.option("--limit", "-l", type=int, default=10, help="Maximum number of actions to show")
@click.option("--generate-drafts", is_flag=True, help="Generate draft messages for shown actions")
@click.option("--save-drafts", is_flag=True, help="Save generated drafts automatically")
def contacts_next_actions(limit, generate_drafts, save_drafts):
    """Show prioritized next actions for your outreach pipeline."""
    if save_drafts:
        generate_drafts = True

    actions = _contact_svc.get_next_actions(limit=limit)
    if not actions:
        console.print("[green]✓ No urgent actions right now.[/green]")
        return

    table = Table(title=f"Next Actions ({len(actions)})")
    table.add_column("Priority", style="dim")
    table.add_column("Contact", style="cyan")
    table.add_column("Action", style="yellow")
    table.add_column("Why", style="white")
    table.add_column("Suggested Command", style="green")

    for action in actions:
        contact_id = action["contact_id"]
        display_name = f"{action['name']} ({action.get('company', '')})".strip()
        command_template = NEXT_ACTION_COMMANDS.get(action["action"], "linkedin-cli contacts view {id}")
        table.add_row(
            str(action["priority"]),
            display_name,
            NEXT_ACTION_LABELS.get(action["action"], action["action"]),
            action["reason"],
            command_template.format(id=contact_id),
        )

    console.print(table)

    if not generate_drafts:
        return

    _generate_action_drafts(actions, save_drafts=save_drafts, show_output=True)


@contacts.command("dedupe")
@click.option("--min-score", type=float, default=0.65, help="Minimum duplicate confidence score (0.0-1.0)")
@click.option("--limit", type=int, default=20, help="Maximum duplicate pairs to show")
def contacts_dedupe(min_score, limit):
    """Find likely duplicate contacts."""
    candidates = _contact_svc.find_duplicate_candidates(min_score=min_score, limit=limit)
    if not candidates:
        console.print("[green]✓ No likely duplicates found.[/green]")
        return

    table = Table(title=f"Potential Duplicates ({len(candidates)})")
    table.add_column("Score", style="yellow")
    table.add_column("Confidence", style="dim")
    table.add_column("Primary", style="cyan")
    table.add_column("Duplicate", style="cyan")
    table.add_column("Signals", style="white")
    table.add_column("Suggested Merge", style="green")

    for candidate in candidates:
        table.add_row(
            f"{candidate['score']:.2f}",
            candidate["confidence"],
            f"#{candidate['primary_id']} {candidate['primary_name']}",
            f"#{candidate['duplicate_id']} {candidate['duplicate_name']}",
            ", ".join(candidate["signals"]) or "-",
            f"linkedin-cli contacts merge {candidate['primary_id']} {candidate['duplicate_id']}",
        )

    console.print(table)


@contacts.command("merge")
@click.argument("primary_id", type=int)
@click.argument("duplicate_id", type=int)
@click.option("--prefer", type=click.Choice(["primary", "duplicate"]), default="primary", help="Preferred record fields")
def contacts_merge(primary_id, duplicate_id, prefer):
    """Merge two contacts into one canonical record."""
    result = _contact_svc.merge_contacts(primary_id, duplicate_id, prefer=prefer)
    if isinstance(result, str):
        console.print(f"[red]{result}[/red]")
        return

    console.print(f"[green]✓ Merged contacts into #{result['id']} ({result.get('name', 'Unknown')})[/green]")


@contacts.command("remind")
@click.argument("contact_id", type=int)
@click.option("--days", "-d", type=int, default=7, help="Set reminder for N days from now")
@click.option("--date", help="Set specific follow-up date (YYYY-MM-DD)")
def contacts_remind(contact_id, days, date):
    """Set a follow-up reminder for a contact."""
    follow_up_date = _contact_svc.set_reminder(contact_id, days, date)
    if not follow_up_date:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    contact = _contact_svc.get_contact(contact_id)
    console.print(f"[green]✓ Reminder set for {contact['name']}: {follow_up_date}[/green]")


# =============================================================================
# Campaigns Commands
# =============================================================================

@cli.group("campaigns")
def campaigns():
    """Manage lightweight multi-step outreach campaigns."""
    pass


@campaigns.command("enroll")
@click.argument("contact_id", type=int)
@click.option("--name", "campaign_name", default="networking_21d", help="Campaign name")
@click.option("--start-date", default="", help="Campaign start date (YYYY-MM-DD)")
def campaigns_enroll(contact_id, campaign_name, start_date):
    """Enroll a contact into a campaign sequence."""
    result = _contact_svc.enroll_campaign(
        contact_id,
        campaign_name=campaign_name,
        start_date=start_date or None,
    )
    if result is None:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return
    if isinstance(result, str):
        console.print(f"[red]{result}[/red]")
        return

    campaign = result.get("campaign", {})
    console.print(
        f"[green]✓ Enrolled #{contact_id} in {campaign.get('name', campaign_name)} "
        f"(start={campaign.get('enrolled_at', '-')}).[/green]"
    )


@campaigns.command("status")
@click.argument("contact_id", type=int, required=False)
@click.option("--active-only", is_flag=True, help="Show only active campaign enrollments")
@click.option("--name", "campaign_name", default="", help="Filter by campaign name")
@click.option("--json", "as_json", is_flag=True, help="Output campaign status as JSON")
def campaigns_status(contact_id, active_only, campaign_name, as_json):
    """Show campaign progress for one contact or all enrolled contacts."""
    if contact_id is not None:
        status = _contact_svc.campaign_status(contact_id)
        if status is None:
            message = f"Contact #{contact_id} not found."
            if as_json:
                click.echo(json.dumps({"error": message}, indent=2))
            else:
                console.print(f"[red]{message}[/red]")
            return
        if not status:
            message = f"Contact #{contact_id} is not enrolled in a campaign."
            if as_json:
                click.echo(json.dumps({"contact_id": contact_id, "campaign": {}}, indent=2))
            else:
                console.print(f"[yellow]{message}[/yellow]")
            return
        if as_json:
            click.echo(json.dumps(status, indent=2))
            return

        current_step = status.get("current_step") or {}
        console.print(
            f"[bold]Campaign:[/bold] {status.get('campaign_name')} | "
            f"[bold]Contact:[/bold] #{status.get('contact_id')} {status.get('contact_name')}"
        )
        console.print(f"[bold]Active:[/bold] {status.get('active')}")
        console.print(f"[bold]Progress:[/bold] step {status.get('step_index', 0) + 1} / {status.get('total_steps', 0)}")
        if current_step:
            console.print(f"[bold]Current Step:[/bold] {current_step.get('label', '-')}")
            console.print(f"[bold]Due Date:[/bold] {status.get('due_date', '-')}")
        if status.get("completed_at"):
            console.print(f"[bold]Completed:[/bold] {status.get('completed_at')}")
        return

    rows = _contact_svc.list_campaign_contacts(active_only=active_only, campaign_name=campaign_name)
    if as_json:
        click.echo(json.dumps({"campaigns": rows}, indent=2))
        return

    if not rows:
        console.print("[yellow]No campaign enrollments found.[/yellow]")
        return

    table = Table(title=f"Campaign Enrollments ({len(rows)})")
    table.add_column("Contact", style="cyan")
    table.add_column("Campaign", style="white")
    table.add_column("Active", style="yellow")
    table.add_column("Step", style="dim")
    table.add_column("Due", style="green")
    for row in rows:
        current_step = row.get("current_step") or {}
        table.add_row(
            f"#{row.get('contact_id')} {row.get('contact_name')}",
            str(row.get("campaign_name", "")),
            "yes" if row.get("active") else "no",
            current_step.get("label", "-"),
            str(row.get("due_date") or "-"),
        )
    console.print(table)


@campaigns.command("due")
@click.option("--limit", type=int, default=10, help="Maximum due campaign steps to show")
@click.option("--json", "as_json", is_flag=True, help="Output due campaign steps as JSON")
def campaigns_due(limit, as_json):
    """Show currently due campaign steps with suggested commands."""
    due = _contact_svc.get_due_campaign_steps(limit=limit)
    if as_json:
        click.echo(json.dumps({"due_steps": due, "count": len(due)}, indent=2))
        return

    if not due:
        console.print("[green]✓ No campaign steps due right now.[/green]")
        return

    table = Table(title=f"Due Campaign Steps ({len(due)})")
    table.add_column("Priority", style="dim")
    table.add_column("Contact", style="cyan")
    table.add_column("Campaign", style="white")
    table.add_column("Step", style="yellow")
    table.add_column("Due", style="dim")
    table.add_column("Command", style="green")
    for row in due:
        table.add_row(
            str(row.get("priority", "")),
            f"#{row.get('contact_id')} {row.get('contact_name')}",
            str(row.get("campaign_name", "")),
            str(row.get("step_label", "")),
            f"{row.get('due_date')} ({row.get('days_overdue', 0)}d overdue)",
            str(row.get("suggested_command", "")),
        )
    console.print(table)


@campaigns.command("advance")
@click.argument("contact_id", type=int)
@click.option("--complete", is_flag=True, help="Mark campaign as complete immediately")
def campaigns_advance(contact_id, complete):
    """Advance a contact to the next campaign step."""
    result = _contact_svc.advance_campaign(contact_id, complete=complete)
    if result is None:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return
    if isinstance(result, str):
        console.print(f"[yellow]{result}[/yellow]")
        return

    status = _contact_svc.campaign_status(contact_id) or {}
    if not status:
        console.print(f"[green]✓ Campaign completed for contact #{contact_id}.[/green]")
        return
    current_step = status.get("current_step") or {}
    if status.get("active"):
        console.print(
            f"[green]✓ Advanced to step {status.get('step_index', 0) + 1}/{status.get('total_steps', 0)}: "
            f"{current_step.get('label', '-')}"
            f" (due {status.get('due_date', '-')})[/green]"
        )
    else:
        console.print(f"[green]✓ Campaign completed for contact #{contact_id}.[/green]")


# =============================================================================
# Drafts Commands
# =============================================================================

@cli.group()
def drafts():
    """Generate and manage AI-powered outreach drafts."""
    pass


@drafts.command("connection")
@click.argument("contact_id", type=int)
def drafts_connection(contact_id):
    """Generate a personalized connection request for a contact."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating connection request for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_connection(contact_id)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Connection Request Draft", border_style="green"))
    console.print(f"\n[dim]Characters: {len(draft)}/300[/dim]")

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "connection", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("message")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="Additional context for the message")
def drafts_message(contact_id, context):
    """Generate a personalized follow-up message."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating message for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_message(contact_id, context)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Message Draft", border_style="blue"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "message", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("intro-request")
@click.argument("contact_id", type=int)
@click.option("--to", "target_id", type=int, required=True, help="Contact ID to be introduced to")
def drafts_intro_request(contact_id, target_id):
    """Generate a message asking for an introduction to another contact."""
    console.print("\n[bold]Generating intro request...[/bold]\n")

    error, draft = _draft_svc.generate_intro_request(contact_id, target_id)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Introduction Request Draft", border_style="magenta"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "intro_request", draft, target_contact_id=target_id)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("thank-you")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="What to thank them for")
def drafts_thank_you(contact_id, context):
    """Generate a thank you message after a call or meeting."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating thank you note for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_thank_you(contact_id, context)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Thank You Note Draft", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "thank_you", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("follow-up")
@click.argument("contact_id", type=int)
@click.option("--attempt", "-a", type=int, default=1, help="Which follow-up attempt (1, 2, or 3)")
def drafts_follow_up(contact_id, attempt):
    """Generate a follow-up message after no response."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating follow-up #{attempt} for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_follow_up(contact_id, attempt)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title=f"Follow-up #{attempt} Draft", border_style="yellow"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, f"follow_up_{attempt}", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("batch-connections")
@click.option("--limit", "-l", type=int, default=5, help="Max number of drafts to generate")
@click.option("--save-all", is_flag=True, help="Save all drafts without prompting")
def drafts_batch_connections(limit, save_all):
    """Generate connection requests for all not_contacted contacts."""
    error, results = _draft_svc.generate_batch_connections(limit)

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    if not results:
        console.print("[green]✓ All contacts have been contacted![/green]")
        return

    console.print(f"\n[bold]Generating connection requests for {len(results)} contacts...[/bold]\n")

    generated = 0
    for contact, draft in results:
        console.print(f"\n[cyan]{contact['name']}[/cyan] ({contact['title']} at {contact['company']}):")
        console.print(Panel(draft, border_style="green"))
        console.print(f"[dim]Characters: {len(draft)}/300[/dim]\n")

        if save_all or click.confirm("Save this draft?"):
            _draft_svc.save_draft(contact["id"], "connection", draft)
            generated += 1

    console.print(f"\n[green]✓ Generated and saved {generated} drafts![/green]")


@drafts.command("list")
def drafts_list_cmd():
    """List all saved drafts."""
    result = _draft_svc.list_drafts()

    if not result:
        console.print("[yellow]No drafts yet. Generate one with: linkedin-cli drafts connection <id>[/yellow]")
        return

    table = Table(title="Saved Drafts")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("For", style="green")
    table.add_column("Preview", style="white")
    table.add_column("Created", style="dim")

    for d in result:
        preview = d["content"][:50] + "..." if len(d["content"]) > 50 else d["content"]
        table.add_row(
            str(d["id"]),
            d["type"],
            d.get("contact_name", "Unknown"),
            preview,
            d["created_at"][:10],
        )

    console.print(table)


@drafts.command("view")
@click.argument("draft_id", type=int)
def drafts_view(draft_id):
    """View a saved draft."""
    draft = _draft_svc.get_draft(draft_id)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found[/red]")
        return

    console.print(Panel(draft["content"], title=f"Draft #{draft_id} ({draft['type']})", border_style="blue"))


# =============================================================================
# Discovery Commands
# =============================================================================

@cli.group()
def discover():
    """AI-powered suggestions for contacts and companies."""
    pass


@discover.command("contacts")
@click.option("--company", "-c", default=None, help="Suggest contacts to find at a company")
@click.option("--role", "-r", default=None, help="Suggest contacts by role/title")
def discover_contacts(company, role):
    """Get AI suggestions for who to connect with."""
    error, suggestions = _discover_svc.discover_contacts(company, role)

    if error:
        if "Specify" in error:
            console.print(f"[yellow]{error}[/yellow]")
            console.print("Examples:")
            console.print("  linkedin-cli discover contacts --company 'LangChain'")
            console.print("  linkedin-cli discover contacts --role 'Engineering Manager'")
        else:
            console.print(f"[yellow]{error}[/yellow]")
        return

    label = f"at {company}" if company else f"for {role}"
    console.print(f"\n[bold]Finding who to connect with {label}...[/bold]\n")
    console.print(Panel(suggestions, title="Contact Discovery Suggestions", border_style="cyan"))


@discover.command("companies")
def discover_companies():
    """Get AI suggestions for companies to target."""
    error, suggestions = _discover_svc.discover_companies()

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print("\n[bold]Discovering companies to target...[/bold]\n")
    console.print(Panel(suggestions, title="Company Discovery Suggestions", border_style="green"))

    if click.confirm("\nWould you like to add any of these companies?"):
        console.print("[dim]Use 'linkedin-cli companies add' to add companies[/dim]")


# =============================================================================
# Research Commands
# =============================================================================

@cli.group()
def research():
    """Research content strategies and post ideas."""
    pass


@research.command("engagement")
def research_engagement():
    """Show high-engagement content strategies for LinkedIn."""
    content = _research_svc.get_engagement_strategies()
    console.print(Markdown(content))


@research.command("ideas")
@click.option("--topic", "-t", default=None, help="Topic to generate ideas for")
def research_ideas(topic):
    """Generate post ideas based on your profile."""
    try:
        focus, ideas = _research_svc.generate_ideas(topic)
    except AIClientError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return

    console.print(f"\n[bold]Generating post ideas for: {focus}...[/bold]\n")
    console.print(Panel(ideas, title="Post Ideas", border_style="green"))

    if click.confirm("\nSave these ideas?"):
        _research_svc.save_ideas(focus, ideas)
        console.print("[green]✓ Ideas saved![/green]")


@research.command("draft-post")
@click.argument("topic")
@click.option("--style", "-s", type=click.Choice(["story", "listicle", "contrarian", "how-to"]), default="story")
def research_draft_post(topic, style):
    """Generate a full post draft."""
    console.print(f"\n[bold]Generating {style} post about: {topic}...[/bold]\n")

    try:
        draft = _research_svc.generate_post_draft(topic, style)
    except AIClientError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return
    console.print(Panel(draft, title=f"Post Draft ({style})", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _research_svc.save_post_draft(topic, style, draft)
        console.print("[green]✓ Post draft saved![/green]")


@research.command("hashtags")
@click.argument("topic")
def research_hashtags(topic):
    """Get hashtag recommendations for a topic."""
    console.print(f"\n[bold]Finding hashtags for: {topic}...[/bold]\n")

    try:
        hashtags = _research_svc.generate_hashtags(topic)
    except AIClientError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        return
    console.print(Panel(hashtags, title="Hashtag Recommendations", border_style="cyan"))


# =============================================================================
# Data Management Commands
# =============================================================================

@cli.group()
def data():
    """Import, export, and backup your data."""
    pass


@data.command("export")
@click.argument("data_type", type=click.Choice(["contacts", "companies", "all"]))
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="csv", help="Export format")
def data_export(data_type, output, fmt):
    """Export contacts or companies to a file."""
    if data_type in ("contacts", "all"):
        count, out_file = _data_svc.export_contacts(output, fmt)
        if count:
            console.print(f"[green]✓ Exported {count} contacts to {out_file}[/green]")
        else:
            console.print("[yellow]No contacts to export[/yellow]")

    if data_type in ("companies", "all"):
        comp_output = output
        if data_type == "all" and output:
            comp_output = output.replace("contacts", "companies")
            if fmt == "csv":
                comp_output = comp_output.replace(".csv", "_companies.csv")
            else:
                comp_output = comp_output.replace(".json", "_companies.json")
        count, out_file = _data_svc.export_companies(comp_output, fmt)
        if count:
            console.print(f"[green]✓ Exported {count} companies to {out_file}[/green]")
        else:
            console.print("[yellow]No companies to export[/yellow]")


@data.command("import")
@click.argument("data_type", type=click.Choice(["contacts", "companies"]))
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing data instead of replacing")
def data_import(data_type, file_path, merge):
    """Import contacts or companies from a file."""
    if data_type == "contacts":
        count = _data_svc.import_contacts(file_path, merge)
        console.print(f"[green]✓ Imported {count} contacts[/green]")
    else:
        count = _data_svc.import_companies(file_path, merge)
        console.print(f"[green]✓ Imported {count} companies[/green]")


@data.command("backup")
@click.option("--output", "-o", default=None, help="Output backup file path")
@click.option("--verify", is_flag=True, help="Verify backup integrity after creation")
def data_backup(output, verify):
    """Create a backup of all data files."""
    backup_name, backed_up = _data_svc.create_backup(output)
    console.print(f"[green]✓ Backup created: {backup_name}[/green]")
    console.print(f"  Backed up {backed_up} files")
    if verify:
        report = _data_svc.verify_backup(backup_name)
        if report.get("valid"):
            console.print(
                "[green]"
                f"  Verified: {report.get('files_checked', 0)} files "
                f"({report.get('json_files_checked', 0)} JSON/JSONL parsed)"
                "[/green]"
            )
        else:
            console.print(f"[red]  Verification failed: {', '.join(report.get('errors', []))}[/red]")


@data.command("restore")
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Validate backup readability without writing files")
def data_restore(backup_file, dry_run):
    """Restore data from a backup file."""
    if not dry_run and not click.confirm("This will overwrite your current data. Continue?"):
        console.print("[yellow]Restore cancelled.[/yellow]")
        return

    restored = _data_svc.restore_backup(backup_file, dry_run=dry_run)
    if restored is None:
        console.print("[red]Invalid or unsafe backup file.[/red]")
        return
    if dry_run:
        console.print(f"[green]✓ Dry-run passed for {restored} file(s).[/green]")
        return
    console.print(f"[green]✓ Restored {restored} files from backup[/green]")


@data.command("verify-backup")
@click.argument("backup_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output verification report as JSON")
def data_verify_backup(backup_file, as_json):
    """Verify backup safety and file integrity."""
    report = _data_svc.verify_backup(backup_file)
    if as_json:
        click.echo(json.dumps(report, indent=2))
        return

    if report.get("valid"):
        console.print("[green]✓ Backup verification passed.[/green]")
        console.print(f"  Files checked: {report.get('files_checked', 0)}")
        console.print(f"  JSON/JSONL parsed: {report.get('json_files_checked', 0)}")
    else:
        console.print("[red]Backup verification failed.[/red]")
        for error in report.get("errors", []):
            console.print(f"  - {error}")


@data.command("backups")
def data_backups():
    """List available backups."""
    backups = _data_svc.list_backups()

    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        console.print("Create one with: linkedin-cli data backup")
        return

    table = Table(title="Available Backups")
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Created", style="green")

    for b in backups:
        table.add_row(b["name"], f"{b['size_kb']:.1f} KB", b["created"])

    console.print(table)
    console.print("\nRestore with: linkedin-cli data restore <backup-file>")


# =============================================================================
# Dashboard
# =============================================================================

@cli.command()
def dashboard():
    """Show overview of your job hunt progress."""
    data = _dashboard_svc.get_dashboard_data()

    console.print("\n[bold]📊 Job Hunt Dashboard[/bold]\n")

    # Profile status
    if data["profile"]:
        console.print(f"[bold]PROFILE:[/bold] {data['profile'].get('name', 'Set up')} → {data['profile'].get('target_role', 'Role TBD')}")
    else:
        console.print("[yellow]⚠[/yellow] Profile: Not set up (run: linkedin-cli profile setup)")

    # Contacts Pipeline
    console.print("\n[bold]CONTACTS PIPELINE[/bold]")
    if data["contacts_total"]:
        total = data["contacts_total"]
        max_label_len = max(len(label) for _, label in DASHBOARD_PIPELINE)
        for status, label in DASHBOARD_PIPELINE:
            count = data["status_counts"].get(status.value, 0)
            bar_width = int(count * 20 / total) if total > 0 else 0
            bar = "█" * bar_width
            console.print(f"  {label:{max_label_len}} {bar:20} {count}")
    else:
        console.print("  [dim]No contacts yet[/dim]")

    # Overdue follow-ups
    overdue = data["overdue"]
    stale = data["stale_connections"]
    if overdue or stale:
        console.print(f"\n[bold red]⚠️  OVERDUE FOLLOW-UPS ({len(overdue) + len(stale)})[/bold red]")
        for contact, days_o in overdue[:3]:
            console.print(f"  ! {contact['name']} - Follow up was {days_o} days ago")
        for contact, days_s in stale[:3]:
            console.print(f"  ! {contact['name']} - Connection sent {days_s} days ago, no response")
        if len(overdue) + len(stale) > 6:
            console.print(f"  [dim]... and {len(overdue) + len(stale) - 6} more[/dim]")

    # Target companies
    if data["companies"]:
        console.print(f"\n[bold]TARGET COMPANIES ({len(data['companies'])})[/bold]")
        high_priority = [c for c in data["companies"] if c.get("priority") == "high"]
        display_companies = high_priority[:3] if high_priority else data["companies"][:3]

        for company in display_companies:
            contact_count = data["company_contacts"].get(company["id"], 0)
            priority_marker = PRIORITY_EMOJI.get(CompanyPriority(company.get("priority", "medium")), "🟡")
            console.print(f"  {priority_marker} {company['name']} ({contact_count} contacts)")

    # Drafts summary
    console.print("\n[bold]DRAFTS[/bold]")
    console.print(f"  Total saved: {data['drafts_total']}")
    if data["draft_types"]:
        type_summary = ", ".join([f"{v} {k.replace('_', ' ')}" for k, v in list(data["draft_types"].items())[:3]])
        console.print(f"  [dim]{type_summary}[/dim]")

    # Suggested actions
    console.print("\n[bold]SUGGESTED ACTIONS[/bold]")
    for suggestion in data["suggestions"][:5]:
        console.print(f"  → {suggestion}")


@cli.command("daily-plan")
@click.option("--actions-limit", type=int, default=8, help="Maximum prioritized actions to show")
@click.option("--postings-limit", type=int, default=5, help="Maximum job postings to show")
@click.option("--min-posting-score", type=int, default=40, help="Minimum posting match score (0-100)")
@click.option("--save-recap", is_flag=True, help="Save this daily plan as a markdown recap")
@click.option("--recap-dir", default="", help="Optional output directory for recap files")
@click.option("--json", "as_json", is_flag=True, help="Output the daily plan as JSON")
def daily_plan(actions_limit, postings_limit, min_posting_score, save_recap, recap_dir, as_json):
    """Show an operational daily plan: actions, opportunities, and best templates."""
    data = _run_daily_cycle(
        actions_limit=actions_limit,
        postings_limit=postings_limit,
        min_posting_score=min_posting_score,
        save_recap=save_recap,
        recap_dir=recap_dir,
    )
    _emit_daily_run_output(data, as_json=as_json)


@cli.command("run-daily")
@click.option("--actions-limit", type=int, default=8, help="Maximum prioritized actions to show")
@click.option("--postings-limit", type=int, default=5, help="Maximum job postings to show")
@click.option("--min-posting-score", type=int, default=40, help="Minimum posting match score (0-100)")
@click.option("--save-recap", is_flag=True, help="Save each run as a markdown recap")
@click.option("--recap-dir", default="", help="Optional output directory for recap files")
@click.option("--generate-drafts", is_flag=True, help="Generate drafts from prioritized actions on each run")
@click.option("--save-drafts", is_flag=True, help="Save generated drafts on each run")
@click.option("--watch", is_flag=True, help="Run continuously once per day at --time")
@click.option("--time", "schedule_time", default="09:00", help="Daily run time in HH:MM (24-hour local)")
@click.option("--run-now", is_flag=True, help="When --watch is set, run immediately before waiting for schedule")
@click.option("--max-runs", type=int, default=0, help="Maximum runs in watch mode (0 means unlimited)")
@click.option("--catch-up-missed/--no-catch-up-missed", default=True, help="In watch mode, run now if today's scheduled time was missed")
@click.option("--retry-attempts", type=int, default=1, help="Additional retries when a run fails")
@click.option("--retry-backoff-seconds", type=float, default=5.0, help="Base delay in seconds between retries")
@click.option("--lock-ttl-minutes", type=int, default=180, help="Minutes before an existing lock is treated as stale")
@click.option("--idempotency-key", default="", help="Optional idempotency key to prevent duplicate runs")
@click.option("--allow-duplicate", is_flag=True, help="Ignore idempotency checks and force execution")
@click.option("--notify-webhook", default="", help="Webhook URL for failure notifications")
@click.option("--notify-on-success", is_flag=True, help="Also notify webhook on successful runs")
@click.option("--failure-streak-threshold", type=int, default=3, help="Notify when N consecutive runs fail")
@click.option("--notify-on-recovery/--no-notify-on-recovery", default=True, help="Notify when a streak failure recovers")
@click.option("--json", "as_json", is_flag=True, help="Output each run as JSON")
def run_daily(
    actions_limit,
    postings_limit,
    min_posting_score,
    save_recap,
    recap_dir,
    generate_drafts,
    save_drafts,
    watch,
    schedule_time,
    run_now,
    max_runs,
    catch_up_missed,
    retry_attempts,
    retry_backoff_seconds,
    lock_ttl_minutes,
    idempotency_key,
    allow_duplicate,
    notify_webhook,
    notify_on_success,
    failure_streak_threshold,
    notify_on_recovery,
    as_json,
):
    """Run the daily plan now, or on a schedule for hands-off execution."""
    if max_runs < 0:
        console.print("[red]--max-runs must be 0 or greater.[/red]")
        return

    if lock_ttl_minutes < 1:
        console.print("[red]--lock-ttl-minutes must be at least 1.[/red]")
        return

    if retry_attempts < 0:
        console.print("[red]--retry-attempts must be 0 or greater.[/red]")
        return

    if retry_backoff_seconds < 0:
        console.print("[red]--retry-backoff-seconds must be 0 or greater.[/red]")
        return

    if failure_streak_threshold < 1:
        console.print("[red]--failure-streak-threshold must be at least 1.[/red]")
        return

    if save_drafts:
        generate_drafts = True

    notify_target = notify_webhook.strip() or os.environ.get("LINKEDIN_RUN_NOTIFY_WEBHOOK", "").strip()

    lock_acquired, lock_error = _acquire_run_lock(lock_ttl_minutes=lock_ttl_minutes)
    if not lock_acquired:
        skipped = {
            "status": "skipped_locked",
            "trigger": "startup",
            "reason": lock_error,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }
        _append_run_log(skipped)
        _emit_run_status(skipped, as_json=as_json)
        return

    try:
        if not watch:
            result = _execute_run_with_retries(
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                as_json=as_json,
                trigger="manual",
                run_at=datetime.now(),
                idempotency_key=idempotency_key,
                allow_duplicate=allow_duplicate,
                watch_mode=False,
                schedule_time=schedule_time,
                actions_limit=actions_limit,
                postings_limit=postings_limit,
                min_posting_score=min_posting_score,
                save_recap=save_recap,
                recap_dir=recap_dir,
                generate_drafts=generate_drafts,
                save_drafts=save_drafts,
                notify_webhook=notify_target,
                notify_on_success=notify_on_success,
                failure_streak_threshold=failure_streak_threshold,
                notify_on_recovery=notify_on_recovery,
            )
            if result.get("status") == "success":
                _emit_daily_run_output(result, as_json=as_json)
            else:
                _emit_run_status(result, as_json=as_json)
            return

        try:
            _next_scheduled_run(schedule_time)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return

        runs_completed = 0
        if not as_json:
            console.print(
                "[bold]Daily runner started[/bold] "
                f"(time={schedule_time}, max_runs={'unlimited' if max_runs == 0 else max_runs})"
            )

        if catch_up_missed and not run_now:
            now = datetime.now()
            scheduled_today = _scheduled_run_for_date(schedule_time, now.date())
            if now >= scheduled_today:
                result = _execute_run_with_retries(
                    retry_attempts=retry_attempts,
                    retry_backoff_seconds=retry_backoff_seconds,
                    as_json=as_json,
                    trigger="watch_catch_up",
                    run_at=scheduled_today,
                    idempotency_key=idempotency_key,
                    allow_duplicate=allow_duplicate,
                    watch_mode=True,
                    schedule_time=schedule_time,
                    actions_limit=actions_limit,
                    postings_limit=postings_limit,
                    min_posting_score=min_posting_score,
                    save_recap=save_recap,
                    recap_dir=recap_dir,
                    generate_drafts=generate_drafts,
                    save_drafts=save_drafts,
                    notify_webhook=notify_target,
                    notify_on_success=notify_on_success,
                    failure_streak_threshold=failure_streak_threshold,
                    notify_on_recovery=notify_on_recovery,
                )
                if result.get("status") == "success":
                    _emit_daily_run_output(result, as_json=as_json)
                else:
                    _emit_run_status(result, as_json=as_json)
                runs_completed += 1
                if max_runs and runs_completed >= max_runs:
                    return

        if run_now:
            result = _execute_run_with_retries(
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                as_json=as_json,
                trigger="watch_run_now",
                run_at=datetime.now(),
                idempotency_key=idempotency_key,
                allow_duplicate=allow_duplicate,
                watch_mode=True,
                schedule_time=schedule_time,
                actions_limit=actions_limit,
                postings_limit=postings_limit,
                min_posting_score=min_posting_score,
                save_recap=save_recap,
                recap_dir=recap_dir,
                generate_drafts=generate_drafts,
                save_drafts=save_drafts,
                notify_webhook=notify_target,
                notify_on_success=notify_on_success,
                failure_streak_threshold=failure_streak_threshold,
                notify_on_recovery=notify_on_recovery,
            )
            if result.get("status") == "success":
                _emit_daily_run_output(result, as_json=as_json)
            else:
                _emit_run_status(result, as_json=as_json)
            runs_completed += 1
            if max_runs and runs_completed >= max_runs:
                return

        while True:
            next_run = _next_scheduled_run(schedule_time)
            wait_seconds = max(1, int((next_run - datetime.now()).total_seconds()))
            if not as_json:
                console.print(
                    f"\n[dim]Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(in {wait_seconds} sec)[/dim]"
                )
            time.sleep(wait_seconds)

            result = _execute_run_with_retries(
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                as_json=as_json,
                trigger="watch_scheduled",
                run_at=next_run,
                idempotency_key=idempotency_key,
                allow_duplicate=allow_duplicate,
                watch_mode=True,
                schedule_time=schedule_time,
                actions_limit=actions_limit,
                postings_limit=postings_limit,
                min_posting_score=min_posting_score,
                save_recap=save_recap,
                recap_dir=recap_dir,
                generate_drafts=generate_drafts,
                save_drafts=save_drafts,
                notify_webhook=notify_target,
                notify_on_success=notify_on_success,
                failure_streak_threshold=failure_streak_threshold,
                notify_on_recovery=notify_on_recovery,
            )
            if result.get("status") == "success":
                _emit_daily_run_output(result, as_json=as_json)
            else:
                _emit_run_status(result, as_json=as_json)

            runs_completed += 1
            if max_runs and runs_completed >= max_runs:
                if not as_json:
                    console.print(f"\n[green]Reached max runs ({max_runs}). Stopping.[/green]")
                return
    except KeyboardInterrupt:
        if not as_json:
            console.print("\n[yellow]Stopped run-daily.[/yellow]")
    finally:
        _release_run_lock()


@cli.command("health")
@click.option("--time", "schedule_time", default="09:00", help="Schedule time to validate (HH:MM)")
@click.option("--lock-ttl-minutes", type=int, default=180, help="Minutes before lock is considered stale")
@click.option("--webhook", "webhook_url", default="", help="Optional webhook URL to validate")
@click.option("--json", "as_json", is_flag=True, help="Output checks as JSON")
def health(schedule_time, lock_ttl_minutes, webhook_url, as_json):
    """Run automation health checks for daily operations."""
    checks: list[dict] = []
    shell_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    cron_env_path: Path | None = None
    cron_env_status: dict | None = None

    try:
        json_store.ensure_dirs()
        probe = json_store.DATA_DIR / ".healthcheck.tmp"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        checks.append({"name": "data_dir", "status": "ok", "detail": f"Writable: {json_store.DATA_DIR}"})
    except Exception as exc:
        checks.append({"name": "data_dir", "status": "fail", "detail": f"Not writable: {exc}"})

    try:
        next_run = _next_scheduled_run(schedule_time)
        checks.append({
            "name": "schedule_time",
            "status": "ok",
            "detail": f"Valid; next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')}.",
        })
    except ValueError as exc:
        checks.append({"name": "schedule_time", "status": "fail", "detail": str(exc)})

    cron_lines, cron_error = _read_user_crontab_lines()
    if cron_error:
        checks.append({
            "name": "managed_schedule",
            "status": "warn",
            "detail": f"Could not inspect crontab: {cron_error}",
        })
    else:
        managed_job = _extract_managed_cron_job_line(cron_lines)
        unmanaged_jobs = _find_unmanaged_run_daily_cron_jobs(cron_lines)
        active_job = managed_job or (unmanaged_jobs[0] if unmanaged_jobs else "")
        cron_env_path = _cron_env_file_from_job_line(active_job) or _default_automation_env_file()
        cron_env_status = _env_file_status(cron_env_path)

        if managed_job:
            managed_time = _cron_schedule_time_from_job_line(active_job)
            checks.append({
                "name": "managed_schedule",
                "status": "ok",
                "detail": f"Configured via cron at {managed_time or 'custom'}",
            })
        else:
            if unmanaged_jobs:
                detected_time = _cron_schedule_time_from_job_line(unmanaged_jobs[0]) or "custom"
                checks.append({
                    "name": "managed_schedule",
                    "status": "warn",
                    "detail": f"Unmanaged run-daily cron detected at {detected_time}. Run automation schedule to manage it.",
                })
            else:
                checks.append({
                    "name": "managed_schedule",
                    "status": "warn",
                    "detail": "No run-daily schedule found. Use: linkedin-cli automation schedule",
                })

    has_shell_key = bool(shell_api_key)
    has_cron_key = bool(cron_env_status and cron_env_status.get("has_anthropic_api_key"))
    if has_shell_key and has_cron_key:
        checks.append({"name": "anthropic_api_key", "status": "ok", "detail": "Configured in shell and cron env file."})
    elif has_shell_key:
        checks.append({"name": "anthropic_api_key", "status": "warn", "detail": "Configured in shell only; sync cron env for scheduled runs."})
    elif has_cron_key:
        checks.append({"name": "anthropic_api_key", "status": "ok", "detail": "Configured in cron env file."})
    else:
        checks.append({
            "name": "anthropic_api_key",
            "status": "warn",
            "detail": "Missing. Use: linkedin-cli automation env sync (or set key manually).",
        })

    if cron_env_status is None:
        checks.append({
            "name": "automation_env_file",
            "status": "warn",
            "detail": "Could not infer cron env file path.",
        })
    else:
        if cron_env_status.get("exists"):
            key_status = "has ANTHROPIC_API_KEY" if cron_env_status.get("has_anthropic_api_key") else "missing ANTHROPIC_API_KEY"
            checks.append({
                "name": "automation_env_file",
                "status": "ok" if cron_env_status.get("has_anthropic_api_key") else "warn",
                "detail": f"{cron_env_status.get('path')} ({key_status}, mode={cron_env_status.get('mode') or 'unknown'})",
            })
        else:
            checks.append({
                "name": "automation_env_file",
                "status": "warn",
                "detail": f"{cron_env_status.get('path')} not found.",
            })

    checks.append({"name": "run_lock", **_health_lock_check(lock_ttl_minutes)})

    try:
        state = _load_run_state()
        completed = state.get("completed_idempotency_keys", [])
        count = len(completed) if isinstance(completed, list) else 0
        checks.append({"name": "idempotency_state", "status": "ok", "detail": f"{count} key(s) tracked."})
    except Exception as exc:
        checks.append({"name": "idempotency_state", "status": "warn", "detail": f"Could not load state: {exc}"})

    history = _load_run_history_entries()
    if not history:
        checks.append({"name": "run_history", "status": "warn", "detail": "No run history yet."})
    else:
        last = history[-1]
        checks.append({
            "name": "run_history",
            "status": "ok",
            "detail": f"{len(history)} runs logged; latest status={last.get('status', 'unknown')}.",
        })

    effective_webhook = webhook_url.strip() or os.environ.get("LINKEDIN_RUN_NOTIFY_WEBHOOK", "").strip()
    if not effective_webhook:
        checks.append({"name": "notify_webhook", "status": "ok", "detail": "Not configured (optional)."})
    elif effective_webhook.startswith(("https://", "http://")):
        checks.append({"name": "notify_webhook", "status": "ok", "detail": "Looks valid."})
    else:
        checks.append({"name": "notify_webhook", "status": "warn", "detail": "URL should start with http:// or https://"})

    overall = "ok"
    if any(check["status"] == "fail" for check in checks):
        overall = "fail"
    elif any(check["status"] == "warn" for check in checks):
        overall = "warn"

    result = {
        "overall_status": overall,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    table = Table(title="Automation Health")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")
    for check in checks:
        status = check["status"]
        style = "green" if status == "ok" else "yellow" if status == "warn" else "red"
        table.add_row(check["name"], f"[{style}]{status}[/{style}]", check["detail"])
    console.print(table)
    color = "green" if overall == "ok" else "yellow" if overall == "warn" else "red"
    console.print(f"[{color}]Overall: {overall}[/{color}]")


@cli.command("run-history")
@click.option("--limit", type=int, default=20, help="Maximum rows to display")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["all", "success", "failed", "skipped_duplicate", "skipped_locked"]),
    default="all",
    help="Filter by run status",
)
@click.option("--trigger", default="", help="Optional trigger filter (manual, watch_scheduled, etc.)")
@click.option("--since-days", type=int, default=0, help="Only include runs from the last N days")
@click.option("--json", "as_json", is_flag=True, help="Output entries as JSON")
def run_history(limit, status_filter, trigger, since_days, as_json):
    """Inspect historical run-daily executions."""
    if limit < 1:
        console.print("[red]--limit must be at least 1.[/red]")
        return
    if since_days < 0:
        console.print("[red]--since-days must be 0 or greater.[/red]")
        return

    entries = _load_run_history_entries()
    if not entries:
        message = "No run history yet. Run: linkedin-cli run-daily --json"
        if as_json:
            click.echo(json.dumps({"entries": [], "message": message}, indent=2))
        else:
            console.print(f"[yellow]{message}[/yellow]")
        return

    filtered = entries
    if status_filter != "all":
        filtered = [entry for entry in filtered if entry.get("status") == status_filter]

    if trigger:
        lowered = trigger.strip().lower()
        filtered = [entry for entry in filtered if str(entry.get("trigger", "")).lower() == lowered]

    if since_days > 0:
        cutoff = datetime.now() - timedelta(days=since_days)
        filtered = [
            entry for entry in filtered
            if (timestamp := _entry_timestamp(entry)) and timestamp >= cutoff
        ]

    displayed = list(reversed(filtered[-limit:]))
    if as_json:
        click.echo(json.dumps({"entries": displayed, "total_matching": len(filtered)}, indent=2))
        return

    if not displayed:
        console.print("[yellow]No run history entries matched the current filters.[/yellow]")
        return

    table = Table(title=f"Run History ({len(displayed)} of {len(filtered)})")
    table.add_column("Finished", style="dim")
    table.add_column("Status", style="white")
    table.add_column("Trigger", style="cyan")
    table.add_column("Run ID", style="yellow")
    table.add_column("Actions", style="dim")
    table.add_column("Drafts", style="dim")
    table.add_column("Error", style="red")

    for entry in displayed:
        finished = str(entry.get("finished_at", ""))[:19] or "-"
        status = str(entry.get("status", "unknown"))
        trigger_name = str(entry.get("trigger", "-"))
        run_id = str(entry.get("run_id", "-"))[:12]
        actions = str(entry.get("actions_count", "-"))
        drafts = str(entry.get("drafts_generated", "-"))
        error = str(entry.get("error", ""))[:80]
        table.add_row(finished, status, trigger_name, run_id, actions, drafts, error)

    console.print(table)


@cli.group("automation")
def automation():
    """Manage unattended run-daily scheduling."""
    pass


@automation.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output schedule status as JSON")
def automation_status(as_json):
    """Show managed schedule status and latest run health."""
    lines, cron_error = _read_user_crontab_lines()
    managed_job = _extract_managed_cron_job_line(lines) if not cron_error else ""
    unmanaged_jobs = _find_unmanaged_run_daily_cron_jobs(lines) if not cron_error else []
    active_job = managed_job or (unmanaged_jobs[0] if unmanaged_jobs else "")
    schedule_time = _cron_schedule_time_from_job_line(active_job) if active_job else ""
    env_file = _cron_env_file_from_job_line(active_job) or _default_automation_env_file()
    env_status = _env_file_status(env_file)
    history = _load_run_history_entries()
    latest = history[-1] if history else None
    lock_check = _health_lock_check(lock_ttl_minutes=180)

    result = {
        "backend": "cron",
        "configured": bool(active_job),
        "managed": bool(managed_job),
        "schedule_time": schedule_time,
        "job_line": active_job,
        "unmanaged_jobs": unmanaged_jobs,
        "env_file": env_status,
        "crontab_error": cron_error or "",
        "run_log_file": str(json_store.RUN_DAILY_LOG_FILE),
        "latest_run": {
            "status": latest.get("status", ""),
            "finished_at": latest.get("finished_at", ""),
            "run_id": latest.get("run_id", ""),
            "trigger": latest.get("trigger", ""),
        } if latest else {},
        "run_lock": lock_check,
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    table = Table(title="Automation Status")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")

    if cron_error:
        table.add_row("cron", "[red]fail[/red]", cron_error)
    elif managed_job:
        detail = f"Managed schedule active ({schedule_time or 'custom'})."
        table.add_row("cron", "[green]ok[/green]", detail)
    elif unmanaged_jobs:
        detected_time = _cron_schedule_time_from_job_line(unmanaged_jobs[0]) or "custom"
        table.add_row(
            "cron",
            "[yellow]warn[/yellow]",
            f"Unmanaged run-daily cron detected ({detected_time}). Run automation schedule to manage it.",
        )
    else:
        table.add_row(
            "cron",
            "[yellow]warn[/yellow]",
            "No run-daily schedule configured. Run: linkedin-cli automation schedule",
        )

    if env_status.get("exists"):
        has_key = env_status.get("has_anthropic_api_key")
        style = "green" if has_key else "yellow"
        key_status = "has ANTHROPIC_API_KEY" if has_key else "missing ANTHROPIC_API_KEY"
        table.add_row(
            "env_file",
            f"[{style}]{'ok' if has_key else 'warn'}[/{style}]",
            f"{env_status.get('path')} ({key_status}, mode={env_status.get('mode') or 'unknown'})",
        )
    else:
        table.add_row(
            "env_file",
            "[yellow]warn[/yellow]",
            f"{env_status.get('path')} not found.",
        )

    if latest:
        table.add_row(
            "latest_run",
            f"[green]{latest.get('status', 'unknown')}[/green]" if latest.get("status") == "success" else f"[yellow]{latest.get('status', 'unknown')}[/yellow]",
            f"{latest.get('finished_at', '-')[:19]} | trigger={latest.get('trigger', '-')}",
        )
    else:
        table.add_row("latest_run", "[yellow]warn[/yellow]", "No run history yet.")

    lock_status = lock_check.get("status", "unknown")
    style = "green" if lock_status == "ok" else "yellow" if lock_status == "warn" else "red"
    table.add_row("run_lock", f"[{style}]{lock_status}[/{style}]", lock_check.get("detail", "-"))
    console.print(table)


@automation.group("env")
def automation_env():
    """Manage env vars used by cron-managed automation."""
    pass


@automation_env.command("status")
@click.option("--env-file", default=str(_default_automation_env_file()), help="Env file path")
@click.option("--json", "as_json", is_flag=True, help="Output env status as JSON")
def automation_env_status(env_file, as_json):
    """Show env-file readiness for scheduled runs."""
    env_path = Path(env_file).expanduser()
    status = _env_file_status(env_path)
    if as_json:
        click.echo(json.dumps(status, indent=2))
        return

    if not status["exists"]:
        console.print(f"[yellow]Env file not found:[/yellow] {status['path']}")
        console.print("Create one with: linkedin-cli automation env sync")
        return

    style = "green" if status.get("has_anthropic_api_key") else "yellow"
    key_status = "present" if status.get("has_anthropic_api_key") else "missing"
    console.print(f"[bold]Env File:[/bold] {status['path']}")
    console.print(f"[bold]Mode:[/bold] {status.get('mode') or 'unknown'}")
    console.print(f"[bold]Keys:[/bold] {status.get('key_count', 0)}")
    console.print(f"[bold]ANTHROPIC_API_KEY:[/bold] [{style}]{key_status}[/{style}]")


@automation_env.command("sync")
@click.option("--env-file", default=str(_default_automation_env_file()), help="Env file path")
@click.option("--json", "as_json", is_flag=True, help="Output sync result as JSON")
def automation_env_sync(env_file, as_json):
    """Sync supported environment variables from current shell into env file."""
    env_path = Path(env_file).expanduser()
    updates = {}
    for key in AUTOMATION_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            updates[key] = value

    ok, env_vars, error = _write_env_file(env_path, updates)
    synced_keys = sorted([key for key in updates if env_vars.get(key)])
    result = {
        "ok": ok and not bool(error),
        "path": str(env_path),
        "synced_keys": synced_keys,
        "available_shell_keys": sorted(list(updates.keys())),
        "error": error or "",
        "status": _env_file_status(env_path),
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if error:
        console.print(f"[red]Env sync failed:[/red] {error}")
        return

    console.print(f"[green]✓ Env file synced:[/green] {env_path}")
    if synced_keys:
        console.print(f"  Keys synced: {', '.join(synced_keys)}")
    else:
        console.print("  No supported keys found in current shell.")


@automation_env.command("set-anthropic-key")
@click.option("--env-file", default=str(_default_automation_env_file()), help="Env file path")
@click.option("--key", prompt=True, hide_input=True, confirmation_prompt=True, help="Anthropic API key")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON")
def automation_env_set_anthropic_key(env_file, key, as_json):
    """Set ANTHROPIC_API_KEY in the automation env file."""
    env_path = Path(env_file).expanduser()
    ok, _, error = _write_env_file(env_path, {"ANTHROPIC_API_KEY": key})
    result = {
        "ok": ok and not bool(error),
        "path": str(env_path),
        "error": error or "",
        "status": _env_file_status(env_path),
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    if error:
        console.print(f"[red]Failed to set key:[/red] {error}")
        return

    console.print(f"[green]✓ ANTHROPIC_API_KEY updated in {env_path}[/green]")


@automation.command("doctor")
@click.option("--time", "schedule_time", default="09:00", help="Desired daily schedule time (HH:MM)")
@click.option("--fix", is_flag=True, help="Apply safe automatic fixes")
@click.option("--run-smoke", is_flag=True, help="Run a one-shot smoke execution after checks")
@click.option("--json", "as_json", is_flag=True, help="Output doctor report as JSON")
def automation_doctor(schedule_time, fix, run_smoke, as_json):
    """Diagnose automation health and optionally apply fixes."""
    checks: list[dict] = []
    fixes: list[str] = []
    errors: list[str] = []

    try:
        _parse_schedule_time(schedule_time)
        checks.append({"name": "schedule_time", "status": "ok", "detail": schedule_time})
    except ValueError as exc:
        checks.append({"name": "schedule_time", "status": "fail", "detail": str(exc)})
        errors.append(str(exc))

    lock_check = _health_lock_check(lock_ttl_minutes=180)
    checks.append({"name": "run_lock", **lock_check})
    if fix and lock_check.get("status") == "warn" and "Stale lock" in lock_check.get("detail", ""):
        try:
            json_store.RUN_DAILY_LOCK_FILE.unlink(missing_ok=True)
            fixes.append("Cleared stale run lock.")
            checks.append({"name": "run_lock_fix", "status": "ok", "detail": "Stale lock removed."})
        except OSError as exc:
            errors.append(str(exc))
            checks.append({"name": "run_lock_fix", "status": "warn", "detail": f"Failed to remove lock: {exc}"})

    cron_lines, cron_error = _read_user_crontab_lines()
    managed_job = _extract_managed_cron_job_line(cron_lines) if not cron_error else ""
    unmanaged_jobs = _find_unmanaged_run_daily_cron_jobs(cron_lines) if not cron_error else []
    active_job = managed_job or (unmanaged_jobs[0] if unmanaged_jobs else "")
    env_file = _cron_env_file_from_job_line(active_job) or _default_automation_env_file()
    env_status = _env_file_status(env_file)

    if cron_error:
        checks.append({"name": "crontab", "status": "warn", "detail": cron_error})
    elif managed_job:
        checks.append({"name": "crontab", "status": "ok", "detail": "Managed schedule detected."})
    elif unmanaged_jobs:
        checks.append({"name": "crontab", "status": "warn", "detail": "Unmanaged run-daily cron detected."})
    else:
        checks.append({"name": "crontab", "status": "warn", "detail": "No run-daily cron schedule detected."})

    checks.append({
        "name": "env_file",
        "status": "ok" if env_status.get("has_anthropic_api_key") else "warn",
        "detail": (
            f"{env_status.get('path')} "
            f"(exists={env_status.get('exists')}, has_key={env_status.get('has_anthropic_api_key')})"
        ),
    })

    if fix:
        updates = {}
        for key in AUTOMATION_ENV_KEYS:
            value = os.environ.get(key, "").strip()
            if value:
                updates[key] = value
        _, _, env_error = _write_env_file(env_file, updates)
        if env_error:
            checks.append({"name": "env_sync_fix", "status": "warn", "detail": env_error})
            errors.append(env_error)
        else:
            fixes.append(f"Synced automation env file: {env_file}")
            env_status = _env_file_status(env_file)

        if not cron_error and not managed_job:
            runner_tokens = _default_scheduler_runner_tokens()
            run_tokens = _build_scheduled_run_daily_tokens(
                runner_tokens,
                save_recap=True,
                generate_drafts=True,
                save_drafts=True,
                retry_attempts=2,
                retry_backoff_seconds=10.0,
                failure_streak_threshold=3,
                notify_on_recovery=True,
                notify_webhook="",
            )
            cron_command = _build_cron_shell_command(Path.cwd().resolve(), run_tokens, env_file=env_file)
            job_line = _build_managed_cron_job_line(
                schedule_time=schedule_time,
                cron_command=cron_command,
                stdout_log=json_store.DATA_DIR / "run_daily.cron.out.log",
                stderr_log=json_store.DATA_DIR / "run_daily.cron.err.log",
            )

            cleaned_lines, _ = _strip_managed_cron_block(cron_lines)
            cleaned_lines, _ = _strip_unmanaged_run_daily_cron_jobs(cleaned_lines)
            cleaned_lines, _ = _strip_legacy_scheduler_comment_lines(cleaned_lines)
            next_lines = list(cleaned_lines)
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            next_lines.extend(_build_managed_cron_block(job_line))
            write_error = _write_user_crontab_lines(next_lines)
            if write_error:
                checks.append({"name": "schedule_fix", "status": "warn", "detail": write_error})
                errors.append(write_error)
            else:
                fixes.append("Installed managed cron schedule.")
                checks.append({"name": "schedule_fix", "status": "ok", "detail": f"Scheduled at {schedule_time}"})

    smoke_result = {}
    if run_smoke and not errors:
        smoke_result = _execute_run_with_retries(
            retry_attempts=0,
            retry_backoff_seconds=0.0,
            as_json=True,
            trigger="doctor_smoke",
            run_at=datetime.now(),
            idempotency_key=f"doctor-smoke-{datetime.now().date().isoformat()}",
            allow_duplicate=True,
            watch_mode=False,
            schedule_time=schedule_time,
            actions_limit=4,
            postings_limit=3,
            min_posting_score=40,
            save_recap=False,
            recap_dir="",
            generate_drafts=False,
            save_drafts=False,
            notify_webhook="",
            notify_on_success=False,
            failure_streak_threshold=3,
            notify_on_recovery=True,
        )
        checks.append({
            "name": "smoke_run",
            "status": "ok" if smoke_result.get("status") == "success" else "warn",
            "detail": smoke_result.get("status", "unknown"),
        })

    overall = "ok"
    if any(check.get("status") == "fail" for check in checks):
        overall = "fail"
    elif errors or any(check.get("status") == "warn" for check in checks):
        overall = "warn"

    report = {
        "overall_status": overall,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "fixes": fixes,
        "errors": errors,
        "smoke_run": smoke_result,
    }

    if as_json:
        click.echo(json.dumps(report, indent=2))
        return

    table = Table(title="Automation Doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")
    for check in checks:
        status = check.get("status", "unknown")
        style = "green" if status == "ok" else "yellow" if status == "warn" else "red"
        table.add_row(str(check.get("name", "")), f"[{style}]{status}[/{style}]", str(check.get("detail", "")))
    console.print(table)
    if fixes:
        console.print("\n[bold]Fixes Applied[/bold]")
        for item in fixes:
            console.print(f"  - {item}")
    if errors:
        console.print("\n[bold red]Errors[/bold red]")
        for item in errors:
            console.print(f"  - {item}")
    color = "green" if overall == "ok" else "yellow" if overall == "warn" else "red"
    console.print(f"\n[{color}]Overall: {overall}[/{color}]")


@automation.command("schedule")
@click.option("--time", "schedule_time", default="09:00", help="Daily run time in HH:MM (24-hour local)")
@click.option("--runner", default="", help="Command prefix to run CLI (e.g. '/usr/local/bin/uv run linkedin-cli')")
@click.option("--workdir", default="", help="Working directory for scheduled runs (default: current directory)")
@click.option("--save-recap/--no-save-recap", default=True, help="Persist markdown recap for each scheduled run")
@click.option("--generate-drafts/--no-generate-drafts", default=True, help="Generate drafts during scheduled runs")
@click.option("--save-drafts/--no-save-drafts", default=True, help="Persist generated drafts during scheduled runs")
@click.option("--adopt-existing/--no-adopt-existing", default=True, help="Replace unmanaged run-daily cron entries")
@click.option("--env-file", default=str(_default_automation_env_file()), help="Env file sourced by cron before run-daily")
@click.option("--sync-env/--no-sync-env", default=True, help="Sync shell ANTHROPIC_API_KEY into env file when present")
@click.option("--retry-attempts", type=int, default=2, help="Additional retries when a scheduled run fails")
@click.option("--retry-backoff-seconds", type=float, default=10.0, help="Base seconds for retry backoff")
@click.option("--failure-streak-threshold", type=int, default=3, help="Notify when N consecutive scheduled runs fail")
@click.option("--notify-on-recovery/--no-notify-on-recovery", default=True, help="Notify when scheduled runs recover")
@click.option("--notify-webhook", default="", help="Webhook URL for failure notifications")
@click.option("--stdout-log", default=str(json_store.DATA_DIR / "run_daily.cron.out.log"), help="Cron stdout log path")
@click.option("--stderr-log", default=str(json_store.DATA_DIR / "run_daily.cron.err.log"), help="Cron stderr log path")
@click.option("--json", "as_json", is_flag=True, help="Output schedule details as JSON")
def automation_schedule(
    schedule_time,
    runner,
    workdir,
    save_recap,
    generate_drafts,
    save_drafts,
    adopt_existing,
    env_file,
    sync_env,
    retry_attempts,
    retry_backoff_seconds,
    failure_streak_threshold,
    notify_on_recovery,
    notify_webhook,
    stdout_log,
    stderr_log,
    as_json,
):
    """Create or update a managed daily cron schedule for run-daily."""
    if retry_attempts < 0:
        console.print("[red]--retry-attempts must be 0 or greater.[/red]")
        return
    if retry_backoff_seconds < 0:
        console.print("[red]--retry-backoff-seconds must be 0 or greater.[/red]")
        return
    if failure_streak_threshold < 1:
        console.print("[red]--failure-streak-threshold must be at least 1.[/red]")
        return

    try:
        _parse_schedule_time(schedule_time)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if save_drafts:
        generate_drafts = True

    runner_tokens, runner_error = _runner_tokens_from_option(runner)
    if runner_error:
        console.print(f"[red]{runner_error}[/red]")
        return

    workdir_path = Path(workdir).expanduser() if workdir.strip() else Path.cwd()
    workdir_path = workdir_path.resolve()
    if not workdir_path.exists() or not workdir_path.is_dir():
        console.print(f"[red]Invalid --workdir: {workdir_path}[/red]")
        return

    stdout_path = Path(stdout_log).expanduser()
    stderr_path = Path(stderr_log).expanduser()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    env_file_path = Path(env_file).expanduser()

    env_synced_keys: list[str] = []
    env_sync_error = ""
    if sync_env:
        updates = {}
        for key in AUTOMATION_ENV_KEYS:
            value = os.environ.get(key, "").strip()
            if value:
                updates[key] = value
        if updates:
            _, env_vars, env_sync_error = _write_env_file(env_file_path, updates)
            if not env_sync_error:
                env_synced_keys = sorted(k for k in updates if env_vars.get(k))
        elif not env_file_path.exists():
            _, _, env_sync_error = _write_env_file(env_file_path, {})

    run_tokens = _build_scheduled_run_daily_tokens(
        runner_tokens,
        save_recap=save_recap,
        generate_drafts=generate_drafts,
        save_drafts=save_drafts,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        failure_streak_threshold=failure_streak_threshold,
        notify_on_recovery=notify_on_recovery,
        notify_webhook=notify_webhook,
    )
    cron_command = _build_cron_shell_command(workdir_path, run_tokens, env_file=env_file_path)
    cron_job = _build_managed_cron_job_line(
        schedule_time=schedule_time,
        cron_command=cron_command,
        stdout_log=stdout_path,
        stderr_log=stderr_path,
    )

    current_lines, read_error = _read_user_crontab_lines()
    if read_error:
        console.print(f"[red]Could not read crontab: {read_error}[/red]")
        return

    cleaned_lines, _ = _strip_managed_cron_block(current_lines)
    adopted_count = 0
    removed_legacy_comments = 0
    if adopt_existing:
        cleaned_lines, adopted_count = _strip_unmanaged_run_daily_cron_jobs(cleaned_lines)
        cleaned_lines, removed_legacy_comments = _strip_legacy_scheduler_comment_lines(cleaned_lines)

    next_lines = list(cleaned_lines)
    if next_lines and next_lines[-1].strip():
        next_lines.append("")
    next_lines.extend(_build_managed_cron_block(cron_job))

    write_error = _write_user_crontab_lines(next_lines)
    if write_error:
        console.print(f"[red]Could not install schedule: {write_error}[/red]")
        return

    result = {
        "backend": "cron",
        "configured": True,
        "schedule_time": schedule_time,
        "workdir": str(workdir_path),
        "runner": runner_tokens,
        "job_line": cron_job,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "failure_streak_threshold": failure_streak_threshold,
        "notify_on_recovery": notify_on_recovery,
        "env_file": _env_file_status(env_file_path),
        "env_synced_keys": env_synced_keys,
        "env_sync_error": env_sync_error,
        "adopted_existing_jobs": adopted_count,
        "removed_legacy_comments": removed_legacy_comments,
    }

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    console.print("[green]✓ Managed cron schedule installed.[/green]")
    console.print(f"  Time: {schedule_time}")
    console.print(f"  Workdir: {workdir_path}")
    console.print(f"  Command: {shlex.join(run_tokens)}")
    console.print(f"  Logs: {stdout_path} | {stderr_path}")
    console.print(f"  Env file: {env_file_path}")
    if env_synced_keys:
        console.print(f"  Synced keys: {', '.join(env_synced_keys)}")
    if env_sync_error:
        console.print(f"  [yellow]Env sync warning:[/yellow] {env_sync_error}")
    if adopted_count:
        console.print(f"  Replaced unmanaged schedule entries: {adopted_count}")
    if removed_legacy_comments:
        console.print(f"  Removed legacy comment lines: {removed_legacy_comments}")


@automation.command("unschedule")
@click.option("--json", "as_json", is_flag=True, help="Output unschedule details as JSON")
def automation_unschedule(as_json):
    """Remove the managed cron schedule created by automation schedule."""
    current_lines, read_error = _read_user_crontab_lines()
    if read_error:
        console.print(f"[red]Could not read crontab: {read_error}[/red]")
        return

    cleaned_lines, removed = _strip_managed_cron_block(current_lines)
    if not removed:
        result = {"removed": False, "detail": "No managed schedule found."}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            console.print("[yellow]No managed schedule found.[/yellow]")
        return

    write_error = _write_user_crontab_lines(cleaned_lines)
    if write_error:
        console.print(f"[red]Could not remove schedule: {write_error}[/red]")
        return

    result = {"removed": True, "detail": "Managed schedule removed."}
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    console.print("[green]✓ Managed schedule removed.[/green]")


# =============================================================================
# Analytics Commands
# =============================================================================


@cli.group()
def analytics():
    """View outreach analytics and pipeline metrics."""
    pass


@analytics.command("summary")
def analytics_summary():
    """Show analytics summary with key metrics."""
    data = _analytics_svc.get_summary()

    console.print(Panel("[bold]Analytics Summary[/bold]", style="blue"))
    console.print(f"  Total contacts: {data['total_contacts']}")
    console.print(f"  Response rate: {data['response_rate']}")
    console.print(f"  Conversion rate: {data['conversion_rate']}")
    console.print(f"  Outreach velocity: {data['outreach_velocity']}")

    if data["pipeline"]:
        console.print("\n[bold]Pipeline:[/bold]")
        for status, count in data["pipeline"].items():
            bar = "█" * count
            console.print(f"  {status.replace('_', ' ').title():20s} {bar} {count}")

    if data["source_effectiveness"]:
        console.print("\n[bold]Source Effectiveness:[/bold]")
        for source, info in data["source_effectiveness"].items():
            console.print(f"  {source.replace('_', ' '):20s} {info['responded']}/{info['total']} ({info['rate']})")

    if data["draft_type_counts"]:
        console.print("\n[bold]Draft Types:[/bold]")
        for dtype, count in data["draft_type_counts"].items():
            console.print(f"  {dtype.replace('_', ' '):20s} {count}")


@analytics.command("conversion")
def analytics_conversion():
    """Show pipeline conversion funnel."""
    funnel = _analytics_svc.get_conversion_funnel()
    if not funnel:
        console.print("[yellow]No contacts yet. Add contacts to see conversion data.[/yellow]")
        return

    console.print(Panel("[bold]Conversion Funnel[/bold]", style="blue"))
    for stage in funnel:
        bar_width = min(50, stage["remaining"])
        bar = "█" * bar_width
        console.print(f"  {stage['stage']:20s} {bar} {stage['remaining']} ({stage['pct']})")


@analytics.command("velocity")
@click.option("--weeks", default=8, help="Number of weeks to show")
def analytics_velocity(weeks):
    """Show outreach velocity over time."""
    data = _analytics_svc.get_velocity(weeks)

    console.print(Panel("[bold]Outreach Velocity[/bold]", style="blue"))
    max_count = max((d["contacts"] for d in data), default=1) or 1
    for entry in data:
        bar_width = int(entry["contacts"] / max_count * 30) if max_count > 0 else 0
        bar = "█" * bar_width
        console.print(f"  {entry['week']:10s} {bar} {entry['contacts']}")


# =============================================================================
# Market Intelligence Commands
# =============================================================================


@cli.group()
def market():
    """Job market intelligence and salary estimates."""
    pass


@market.command("analyze")
@click.option("--role", default="", help="Target role to analyze")
@click.option("--industry", default="", help="Target industry")
def market_analyze(role, industry):
    """Get AI market analysis for a role/industry."""
    console.print("\n[bold]Analyzing market...[/bold]\n")
    error, result = _market_svc.analyze_market(role, industry)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("salary")
@click.option("--role", default="", help="Target role")
@click.option("--location", default="", help="Location")
def market_salary(role, location):
    """Get AI salary estimates for a role."""
    console.print("\n[bold]Estimating salary...[/bold]\n")
    error, result = _market_svc.estimate_salary(role, location)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("trends")
@click.option("--industry", default="", help="Industry to analyze")
def market_trends(industry):
    """Get AI hiring trend analysis."""
    console.print("\n[bold]Analyzing trends...[/bold]\n")
    error, result = _market_svc.analyze_trends(industry)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("add-posting")
@click.option("--title", "-t", prompt="Job title", help="Role title")
@click.option("--company", "-c", prompt="Company", help="Company name")
@click.option("--location", "-l", default="", help="Location (city/state or remote)")
@click.option("--skills", default="", help="Comma-separated required skills")
@click.option("--url", default="", help="Job posting URL")
@click.option("--source", default="manual", help="Source (manual, linkedin, referral, etc.)")
@click.option("--salary-min", type=int, default=None, help="Minimum base salary")
@click.option("--salary-max", type=int, default=None, help="Maximum base salary")
@click.option("--notes", default="", help="Additional notes")
def market_add_posting(title, company, location, skills, url, source, salary_min, salary_max, notes):
    """Add a job posting to track and score."""
    posting = _market_svc.add_posting({
        "title": title,
        "company": company,
        "location": location,
        "skills_required": skills,
        "url": url,
        "source": source,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "notes": notes,
    })
    console.print(f"[green]✓ Added posting #{posting['id']}: {posting['title']} at {posting['company']}[/green]")


@market.command("import-postings")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing postings instead of replacing")
def market_import_postings(file_path, merge):
    """Import job postings from CSV or JSON."""
    try:
        imported, skipped = _market_svc.import_postings(file_path, merge=merge)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    console.print(f"[green]✓ Imported {imported} posting(s)[/green]")
    if skipped:
        console.print(f"[yellow]Skipped {skipped} duplicate/invalid posting(s)[/yellow]")


@market.command("postings")
@click.option("--limit", "-l", type=int, default=20, help="Max postings to show")
@click.option("--min-score", type=int, default=0, help="Minimum profile-match score (0-100)")
def market_postings(limit, min_score):
    """List tracked postings ranked by profile match."""
    postings = _market_svc.list_postings(limit=limit, min_score=min_score)
    if not postings:
        console.print("[yellow]No postings found. Add one with: linkedin-cli market add-posting[/yellow]")
        return

    table = Table(title=f"Tracked Job Postings ({len(postings)})")
    table.add_column("ID", style="dim")
    table.add_column("Role", style="cyan")
    table.add_column("Company", style="white")
    table.add_column("Location", style="dim")
    table.add_column("Score", style="green")
    table.add_column("Skills", style="yellow")

    for posting in postings:
        skills = posting.get("skills_required", "")
        skill_preview = ", ".join([s.strip() for s in skills.split(",")[:3]]) if skills else "-"
        table.add_row(
            str(posting["id"]),
            posting.get("title", "")[:35],
            posting.get("company", "")[:25],
            posting.get("location", "")[:20] or "-",
            str(posting.get("match_score", 0)),
            skill_preview[:35],
        )

    console.print(table)


# =============================================================================
# Profile Optimizer Commands
# =============================================================================


@cli.group()
def optimize():
    """AI-powered LinkedIn profile optimization."""
    pass


@optimize.command("headline")
def optimize_headline():
    """Generate optimized headline variants."""
    console.print("\n[bold]Generating headline options...[/bold]\n")
    error, result = _optimizer_svc.optimize_headline()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("about")
def optimize_about():
    """Generate optimized About section."""
    console.print("\n[bold]Generating About section...[/bold]\n")
    error, result = _optimizer_svc.optimize_about()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("skills")
def optimize_skills():
    """Analyze and optimize skills."""
    console.print("\n[bold]Analyzing skills...[/bold]\n")
    error, result = _optimizer_svc.optimize_skills()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("full")
def optimize_full():
    """Full profile optimization review."""
    console.print("\n[bold]Running full optimization review...[/bold]\n")
    error, result = _optimizer_svc.optimize_full()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


# =============================================================================
# Template Commands
# =============================================================================


@cli.group()
def templates():
    """Smart message templates with A/B testing."""
    pass


@templates.command("list")
def templates_list():
    """List all saved templates."""
    all_templates = _template_svc.list_templates()
    if not all_templates:
        console.print("[yellow]No templates saved yet. Use 'linkedin-cli templates save' to create one.[/yellow]")
        return

    table = Table(title="Templates")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Variant")
    table.add_column("Uses")
    table.add_column("Rate")

    for t in all_templates:
        table.add_row(
            str(t["id"]),
            t["name"],
            t.get("template_type", ""),
            t.get("variant", "A"),
            str(t.get("usage_count", 0)),
            t.get("response_rate", "0%"),
        )

    console.print(table)


@templates.command("save")
@click.option("--name", required=True, help="Template name")
@click.option("--type", "template_type", required=True, help="Template type (connection, message, follow_up)")
@click.option("--content", required=True, help="Template content with {{name}}, {{company}} placeholders")
@click.option("--variant", default="A", help="A/B variant (A or B)")
def templates_save(name, template_type, content, variant):
    """Save a new message template."""
    template = _template_svc.save_template(name, template_type, content, variant)
    console.print(f"[green]Template '{template['name']}' saved (ID: {template['id']}, variant {variant})[/green]")


@templates.command("use")
@click.argument("template_id", type=int)
@click.argument("contact_id", type=int)
def templates_use(template_id, contact_id):
    """Apply a template for a specific contact."""
    rendered = _template_svc.use_template(template_id, contact_id)
    if not rendered:
        console.print("[red]Template or contact not found.[/red]")
        return
    console.print(Panel(rendered, title="Rendered Template"))


@templates.command("ab-results")
def templates_ab_results():
    """Show A/B test results."""
    results = _template_svc.get_ab_results()
    if not results:
        console.print("[yellow]No A/B tests found. Create templates with the same name but different variants.[/yellow]")
        return

    for result in results:
        sig_marker = " ✓ Significant" if result["significant"] else " (not significant)"
        console.print(f"\n[bold]{result['name']}[/bold] — Best: {result['best_variant']}{sig_marker}")
        for v in result["variants"]:
            console.print(f"  Variant {v['variant']}: {v['usage_count']} uses, {v['response_count']} responses ({v['response_rate']})")


@templates.command("record-response")
@click.argument("template_id", type=int)
@click.option("--count", "-c", type=int, default=1, help="Number of responses to record")
def templates_record_response(template_id, count):
    """Record one or more responses for a template."""
    if count < 1:
        console.print("[red]Count must be at least 1.[/red]")
        return

    if not _template_svc.record_response(template_id, count):
        console.print(f"[red]Template #{template_id} not found.[/red]")
        return

    template = _template_svc.get_template(template_id)
    console.print(
        f"[green]✓ Recorded {count} response(s) for '{template['name']}' "
        f"(total: {template.get('response_count', 0)})[/green]"
    )


@templates.command("suggest-best")
@click.option("--type", "template_type", required=True, help="Template type (connection, message, follow_up)")
def templates_suggest_best(template_type):
    """Suggest the best-performing template for a type."""
    best = _template_svc.suggest_best(template_type)
    if not best:
        console.print(
            f"[yellow]No used templates found for type '{template_type}'. "
            "Use templates first to collect data.[/yellow]"
        )
        return

    console.print(
        f"[green]Best template: #{best['id']} '{best['name']}' "
        f"(variant {best.get('variant', 'A')}, {best.get('response_rate', '0%')} response rate)[/green]"
    )
    console.print(Panel(best.get("content", ""), title="Template Content"))


@templates.command("dashboard")
def templates_dashboard():
    """Show template experiment metrics by type and overall."""
    all_templates = _template_svc.list_templates()
    if not all_templates:
        console.print("[yellow]No templates saved yet.[/yellow]")
        return

    total_uses = sum(t.get("usage_count", 0) for t in all_templates)
    total_responses = sum(t.get("response_count", 0) for t in all_templates)
    overall_rate = (total_responses / total_uses * 100) if total_uses else 0.0
    console.print(
        f"[bold]Template Experiments:[/bold] {len(all_templates)} templates | "
        f"{total_uses} uses | {total_responses} responses | {overall_rate:.1f}% overall response rate"
    )

    by_type: dict[str, dict] = {}
    for template in all_templates:
        template_type = template.get("template_type", "unknown")
        entry = by_type.setdefault(template_type, {"templates": 0, "uses": 0, "responses": 0})
        entry["templates"] += 1
        entry["uses"] += template.get("usage_count", 0)
        entry["responses"] += template.get("response_count", 0)

    type_table = Table(title="By Template Type")
    type_table.add_column("Type", style="cyan")
    type_table.add_column("Templates", style="dim")
    type_table.add_column("Uses", style="dim")
    type_table.add_column("Responses", style="dim")
    type_table.add_column("Response Rate", style="yellow")
    for template_type, stats in sorted(by_type.items()):
        rate = (stats["responses"] / stats["uses"] * 100) if stats["uses"] else 0.0
        type_table.add_row(
            template_type,
            str(stats["templates"]),
            str(stats["uses"]),
            str(stats["responses"]),
            f"{rate:.1f}%",
        )
    console.print(type_table)

    top_templates = sorted(
        all_templates,
        key=lambda t: (
            t.get("usage_count", 0) > 0,
            float(str(t.get("response_rate", "0")).rstrip("%")),
            t.get("usage_count", 0),
        ),
        reverse=True,
    )[:5]
    top_table = Table(title="Top Templates")
    top_table.add_column("ID", style="dim")
    top_table.add_column("Name", style="cyan")
    top_table.add_column("Variant", style="dim")
    top_table.add_column("Uses", style="dim")
    top_table.add_column("Response Rate", style="green")
    for template in top_templates:
        top_table.add_row(
            str(template["id"]),
            template["name"],
            template.get("variant", "A"),
            str(template.get("usage_count", 0)),
            template.get("response_rate", "0%"),
        )
    console.print(top_table)


if __name__ == "__main__":
    cli()
