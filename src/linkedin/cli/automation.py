import json
import os
import shlex
from datetime import datetime
from pathlib import Path

import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.daily import _daily_run
from linkedin.scheduling import install
from linkedin.scheduling.crontab import (
    AUTOMATION_ENV_KEYS,
    default_automation_env_file,
    env_file_status,
    write_env_file,
)
from linkedin.scheduling.schedule import (
    default_scheduler_runner_tokens,
    runner_tokens_from_option,
)
from linkedin.services.daily_run import RunConfig
from linkedin.services.diagnostics import diagnostics, overall_status


@cli.group("automation")
def automation():
    """Manage unattended run-daily scheduling."""
    pass


def _env_path(option: str) -> Path:
    """The cron env file: the option if given, else the data dir's. Resolved at call time, never at import."""
    return Path(option).expanduser() if option.strip() else default_automation_env_file(_app.data_dir)


def _render_checks(title: str, checks: list[dict]) -> None:
    table = Table(title=title)
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Detail", style="dim")
    for c in checks:
        status = c.get("status", "unknown")
        style = "green" if status in ("ok", "success") else "yellow" if status == "warn" else "red"
        table.add_row(str(c.get("name", "")), f"[{style}]{status}[/{style}]", str(c.get("detail", "")))
    console.print(table)


@automation.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output schedule status as JSON")
def automation_status(as_json):
    """Show managed schedule status and latest run health."""
    cron_lines, cron_error = install.read_user_crontab_lines()
    checks, facts = diagnostics(_app.get(), cron_lines=cron_lines, cron_error=cron_error)
    latest = facts["latest_run"]
    result = {
        "backend": "cron",
        "configured": bool(facts["active_job"]),
        "managed": bool(facts["managed_job"]),
        "schedule_time": facts["schedule_time"],
        "job_line": facts["active_job"],
        "unmanaged_jobs": facts["unmanaged_jobs"],
        "env_file": facts["env_status"],
        "crontab_error": facts["cron_error"],
        "run_log_file": str(_app.data_dir.run_daily_log),
        "latest_run": {k: latest.get(k, "") for k in ("status", "finished_at", "run_id", "trigger")} if latest else {},
        "run_lock": next(c for c in checks if c["name"] == "run_lock"),
        "checks": checks,
    }
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    shown = [c for c in checks if c["name"] in ("crontab", "env_file", "run_lock")]
    if latest:
        shown.append(
            {
                "name": "latest_run",
                "status": latest.get("status", "unknown"),
                "detail": f"{str(latest.get('finished_at', '-'))[:19]} | trigger={latest.get('trigger', '-')}",
            }
        )
    else:
        shown.append({"name": "latest_run", "status": "warn", "detail": "No run history yet."})
    _render_checks("Automation Status", shown)


@automation.group("env")
def automation_env():
    """Manage env vars used by cron-managed automation."""
    pass


@automation_env.command("status")
@click.option("--env-file", default="", help="Env file path (default: cron.env in the data dir)")
@click.option("--json", "as_json", is_flag=True, help="Output env status as JSON")
def automation_env_status(env_file, as_json):
    """Show env-file readiness for scheduled runs."""
    env_path = _env_path(env_file)
    status = env_file_status(env_path)
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
@click.option("--env-file", default="", help="Env file path (default: cron.env in the data dir)")
@click.option("--json", "as_json", is_flag=True, help="Output sync result as JSON")
def automation_env_sync(env_file, as_json):
    """Sync supported environment variables from current shell into env file."""
    env_path = _env_path(env_file)
    updates = {}
    for key in AUTOMATION_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            updates[key] = value

    ok, env_vars, error = write_env_file(env_path, updates)
    synced_keys = sorted([key for key in updates if env_vars.get(key)])
    result = {
        "ok": ok and not bool(error),
        "path": str(env_path),
        "synced_keys": synced_keys,
        "available_shell_keys": sorted(list(updates.keys())),
        "error": error or "",
        "status": env_file_status(env_path),
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
@click.option("--env-file", default="", help="Env file path (default: cron.env in the data dir)")
@click.option("--key", prompt=True, hide_input=True, confirmation_prompt=True, help="Anthropic API key")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON")
def automation_env_set_anthropic_key(env_file, key, as_json):
    """Set ANTHROPIC_API_KEY in the automation env file."""
    env_path = _env_path(env_file)
    ok, _, error = write_env_file(env_path, {"ANTHROPIC_API_KEY": key})
    result = {
        "ok": ok and not bool(error),
        "path": str(env_path),
        "error": error or "",
        "status": env_file_status(env_path),
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
@click.option("--lock-ttl-minutes", type=int, default=180, help="Minutes before a lock is considered stale")
@click.option("--webhook", "webhook_url", default="", help="Optional webhook URL to validate")
@click.option("--fix", is_flag=True, help="Apply safe automatic fixes")
@click.option("--run-smoke", is_flag=True, help="Run a one-shot smoke execution after checks")
@click.option(
    "--probe-ai", is_flag=True, help="Make one tiny API call to prove the key works (presence is not validity)"
)
@click.option("--json", "as_json", is_flag=True, help="Output doctor report as JSON")
def automation_doctor(schedule_time, lock_ttl_minutes, webhook_url, fix, run_smoke, probe_ai, as_json):
    """Diagnose daily-run health and optionally apply fixes. The one check list; `health` was a second copy."""
    fixes: list[str] = []
    errors: list[str] = []
    cron_lines, cron_error = install.read_user_crontab_lines()
    checks, facts = diagnostics(
        _app.get(),
        cron_lines=cron_lines,
        cron_error=cron_error,
        schedule_time=schedule_time,
        lock_ttl_minutes=lock_ttl_minutes,
        webhook_url=webhook_url,
        probe_ai=probe_ai,
    )
    by_name = {c["name"]: c for c in checks}
    if by_name["schedule_time"]["status"] == "fail":
        errors.append(by_name["schedule_time"]["detail"])

    if fix:
        lock = by_name["run_lock"]
        if lock.get("status") == "warn" and "Stale lock" in lock.get("detail", ""):
            try:
                _app.data_dir.run_daily_lock.unlink(missing_ok=True)
                fixes.append("Cleared stale run lock.")
                checks.append({"name": "run_lock_fix", "status": "ok", "detail": "Stale lock removed."})
            except OSError as exc:
                errors.append(str(exc))
                checks.append({"name": "run_lock_fix", "status": "warn", "detail": f"Failed to remove lock: {exc}"})

        env_file = facts["env_file"]
        _, env_error = install.sync_env_from_environ(env_file)
        if env_error:
            checks.append({"name": "env_sync_fix", "status": "warn", "detail": env_error})
            errors.append(env_error)
        else:
            fixes.append(f"Synced automation env file: {env_file}")

        if not facts["cron_error"] and not facts["managed_job"]:
            spec = install.ScheduleSpec(
                schedule_time=schedule_time,
                runner_tokens=default_scheduler_runner_tokens(),
                workdir=Path.cwd().resolve(),
                env_file=env_file,
                stdout_log=_app.data_dir.cron_out_log,
                stderr_log=_app.data_dir.cron_err_log,
            )
            installed = install.install_schedule(spec, sync_env=False)
            if installed.error:
                checks.append({"name": "schedule_fix", "status": "warn", "detail": installed.error})
                errors.append(installed.error)
            else:
                fixes.append("Installed managed cron schedule.")
                checks.append({"name": "schedule_fix", "status": "ok", "detail": f"Scheduled at {schedule_time}"})

    smoke_result: dict = {}
    if run_smoke and not errors:
        smoke = _daily_run(
            RunConfig(
                actions_limit=4,
                postings_limit=3,
                schedule_time=schedule_time,
                idempotency_key=f"doctor-smoke-{datetime.now().date().isoformat()}",
                allow_duplicate=True,
                retry_attempts=0,
                retry_backoff_seconds=0.0,
            ),
            show_drafts=False,
            as_json=True,
        )
        smoke_result = smoke.execute("doctor_smoke", datetime.now())
        checks.append(
            {
                "name": "smoke_run",
                "status": "ok" if smoke_result.get("status") == "success" else "warn",
                "detail": smoke_result.get("status", "unknown"),
            }
        )

    overall = overall_status(checks, errors)
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
    _render_checks("Automation Doctor", checks)
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
@click.option(
    "--collect-metrics/--no-collect-metrics",
    default=True,
    help="Read account metrics (headless browser) on each scheduled run",
)
@click.option(
    "--send-connections/--no-send-connections",
    default=True,
    help="After the plan, send its connection actions up to the daily budget",
)
@click.option("--adopt-existing/--no-adopt-existing", default=True, help="Replace unmanaged run-daily cron entries")
@click.option(
    "--env-file", default="", help="Env file sourced by cron before run-daily (default: cron.env in the data dir)"
)
@click.option("--sync-env/--no-sync-env", default=True, help="Sync shell ANTHROPIC_API_KEY into env file when present")
@click.option("--retry-attempts", type=int, default=2, help="Additional retries when a scheduled run fails")
@click.option("--retry-backoff-seconds", type=float, default=10.0, help="Base seconds for retry backoff")
@click.option("--failure-streak-threshold", type=int, default=3, help="Notify when N consecutive scheduled runs fail")
@click.option("--notify-on-recovery/--no-notify-on-recovery", default=True, help="Notify when scheduled runs recover")
@click.option("--notify-webhook", default="", help="Webhook URL for failure notifications")
@click.option("--stdout-log", default=None, help="Cron stdout log path (default: <data dir>/run_daily.cron.out.log)")
@click.option("--stderr-log", default=None, help="Cron stderr log path (default: <data dir>/run_daily.cron.err.log)")
@click.option("--json", "as_json", is_flag=True, help="Output schedule details as JSON")
def automation_schedule(
    schedule_time,
    runner,
    workdir,
    save_recap,
    generate_drafts,
    save_drafts,
    collect_metrics,
    send_connections,
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
    runner_tokens, runner_error = runner_tokens_from_option(runner)
    if runner_error:
        console.print(f"[red]{runner_error}[/red]")
        return
    workdir_path = (Path(workdir).expanduser() if workdir.strip() else Path.cwd()).resolve()
    spec = install.ScheduleSpec(
        schedule_time=schedule_time,
        runner_tokens=runner_tokens,
        workdir=workdir_path,
        env_file=_env_path(env_file),
        stdout_log=Path(stdout_log).expanduser() if stdout_log else _app.data_dir.cron_out_log,
        stderr_log=Path(stderr_log).expanduser() if stderr_log else _app.data_dir.cron_err_log,
        save_recap=save_recap,
        generate_drafts=generate_drafts,
        save_drafts=save_drafts,
        collect_metrics=collect_metrics,
        send_connections=send_connections,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        failure_streak_threshold=failure_streak_threshold,
        notify_on_recovery=notify_on_recovery,
        notify_webhook=notify_webhook,
        adopt_existing=adopt_existing,
    )
    installed = install.install_schedule(spec, sync_env=sync_env)
    if installed.error:
        console.print(f"[red]{installed.error}[/red]")
        return
    if as_json:
        click.echo(json.dumps(installed.as_dict(spec), indent=2))
        return

    console.print("[green]✓ Managed cron schedule installed.[/green]")
    console.print(f"  Time: {schedule_time}")
    console.print(f"  Workdir: {workdir_path}")
    console.print(f"  Command: {shlex.join(spec.run_tokens())}")
    console.print(f"  Logs: {spec.stdout_log} | {spec.stderr_log}")
    console.print(f"  Env file: {spec.env_file}")
    if installed.env_synced_keys:
        console.print(f"  Synced keys: {', '.join(installed.env_synced_keys)}")
    if installed.env_sync_error:
        console.print(f"  [yellow]Env sync warning:[/yellow] {installed.env_sync_error}")
    if installed.adopted_existing_jobs:
        console.print(f"  Replaced unmanaged schedule entries: {installed.adopted_existing_jobs}")
    if installed.removed_legacy_comments:
        console.print(f"  Removed legacy comment lines: {installed.removed_legacy_comments}")


@automation.command("unschedule")
@click.option("--json", "as_json", is_flag=True, help="Output unschedule details as JSON")
def automation_unschedule(as_json):
    """Remove the managed cron schedule created by automation schedule."""
    removed, error = install.remove_schedule()
    if error:
        console.print(f"[red]{error}[/red]")
        return
    result = {"removed": removed, "detail": "Managed schedule removed." if removed else "No managed schedule found."}
    if as_json:
        click.echo(json.dumps(result, indent=2))
    elif removed:
        console.print("[green]✓ Managed schedule removed.[/green]")
    else:
        console.print("[yellow]No managed schedule found.[/yellow]")
