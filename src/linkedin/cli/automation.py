import json
import os
import shlex
from datetime import datetime
from pathlib import Path

import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.daily import _daily_run
from linkedin.scheduling.crontab import (
    AUTOMATION_ENV_KEYS,
    build_cron_shell_command,
    build_managed_cron_block,
    build_managed_cron_job_line,
    default_automation_env_file,
    env_file_status,
    read_user_crontab_lines,
    strip_legacy_scheduler_comment_lines,
    strip_managed_cron_block,
    strip_unmanaged_run_daily_cron_jobs,
    write_env_file,
    write_user_crontab_lines,
)
from linkedin.scheduling.schedule import (
    build_scheduled_run_daily_tokens,
    default_scheduler_runner_tokens,
    parse_schedule_time,
    runner_tokens_from_option,
)
from linkedin.services.daily_run import RunConfig
from linkedin.services.diagnostics import diagnostics, overall_status


@cli.group("automation")
def automation():
    """Manage unattended run-daily scheduling."""
    pass


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
    cron_lines, cron_error = read_user_crontab_lines()
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
@click.option("--env-file", default=str(default_automation_env_file(_app.data_dir)), help="Env file path")
@click.option("--json", "as_json", is_flag=True, help="Output env status as JSON")
def automation_env_status(env_file, as_json):
    """Show env-file readiness for scheduled runs."""
    env_path = Path(env_file).expanduser()
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
@click.option("--env-file", default=str(default_automation_env_file(_app.data_dir)), help="Env file path")
@click.option("--json", "as_json", is_flag=True, help="Output sync result as JSON")
def automation_env_sync(env_file, as_json):
    """Sync supported environment variables from current shell into env file."""
    env_path = Path(env_file).expanduser()
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
@click.option("--env-file", default=str(default_automation_env_file(_app.data_dir)), help="Env file path")
@click.option("--key", prompt=True, hide_input=True, confirmation_prompt=True, help="Anthropic API key")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON")
def automation_env_set_anthropic_key(env_file, key, as_json):
    """Set ANTHROPIC_API_KEY in the automation env file."""
    env_path = Path(env_file).expanduser()
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
    cron_lines, cron_error = read_user_crontab_lines()
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
        updates = {key: os.environ[key].strip() for key in AUTOMATION_ENV_KEYS if os.environ.get(key, "").strip()}
        _, _, env_error = write_env_file(env_file, updates)
        if env_error:
            checks.append({"name": "env_sync_fix", "status": "warn", "detail": env_error})
            errors.append(env_error)
        else:
            fixes.append(f"Synced automation env file: {env_file}")

        if not facts["cron_error"] and not facts["managed_job"]:
            run_tokens = build_scheduled_run_daily_tokens(
                default_scheduler_runner_tokens(),
                save_recap=True,
                generate_drafts=True,
                save_drafts=True,
                collect_metrics=True,
                retry_attempts=2,
                retry_backoff_seconds=10.0,
                failure_streak_threshold=3,
                notify_on_recovery=True,
                notify_webhook="",
            )
            cron_command = build_cron_shell_command(Path.cwd().resolve(), run_tokens, env_file=env_file)
            job_line = build_managed_cron_job_line(
                schedule_time=schedule_time,
                cron_command=cron_command,
                stdout_log=_app.data_dir.cron_out_log,
                stderr_log=_app.data_dir.cron_err_log,
            )
            cleaned, _ = strip_managed_cron_block(cron_lines)
            cleaned, _ = strip_unmanaged_run_daily_cron_jobs(cleaned)
            cleaned, _ = strip_legacy_scheduler_comment_lines(cleaned)
            next_lines = list(cleaned)
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            next_lines.extend(build_managed_cron_block(job_line))
            write_error = write_user_crontab_lines(next_lines)
            if write_error:
                checks.append({"name": "schedule_fix", "status": "warn", "detail": write_error})
                errors.append(write_error)
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
@click.option("--adopt-existing/--no-adopt-existing", default=True, help="Replace unmanaged run-daily cron entries")
@click.option(
    "--env-file",
    default=str(default_automation_env_file(_app.data_dir)),
    help="Env file sourced by cron before run-daily",
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
        parse_schedule_time(schedule_time)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if save_drafts:
        generate_drafts = True

    runner_tokens, runner_error = runner_tokens_from_option(runner)
    if runner_error:
        console.print(f"[red]{runner_error}[/red]")
        return

    workdir_path = Path(workdir).expanduser() if workdir.strip() else Path.cwd()
    workdir_path = workdir_path.resolve()
    if not workdir_path.exists() or not workdir_path.is_dir():
        console.print(f"[red]Invalid --workdir: {workdir_path}[/red]")
        return

    stdout_path = Path(stdout_log).expanduser() if stdout_log else _app.data_dir.cron_out_log
    stderr_path = Path(stderr_log).expanduser() if stderr_log else _app.data_dir.cron_err_log
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
            _, env_vars, env_sync_error = write_env_file(env_file_path, updates)
            if not env_sync_error:
                env_synced_keys = sorted(k for k in updates if env_vars.get(k))
        elif not env_file_path.exists():
            _, _, env_sync_error = write_env_file(env_file_path, {})

    run_tokens = build_scheduled_run_daily_tokens(
        runner_tokens,
        save_recap=save_recap,
        generate_drafts=generate_drafts,
        save_drafts=save_drafts,
        collect_metrics=collect_metrics,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        failure_streak_threshold=failure_streak_threshold,
        notify_on_recovery=notify_on_recovery,
        notify_webhook=notify_webhook,
    )
    cron_command = build_cron_shell_command(workdir_path, run_tokens, env_file=env_file_path)
    cron_job = build_managed_cron_job_line(
        schedule_time=schedule_time,
        cron_command=cron_command,
        stdout_log=stdout_path,
        stderr_log=stderr_path,
    )

    current_lines, read_error = read_user_crontab_lines()
    if read_error:
        console.print(f"[red]Could not read crontab: {read_error}[/red]")
        return

    cleaned_lines, _ = strip_managed_cron_block(current_lines)
    adopted_count = 0
    removed_legacy_comments = 0
    if adopt_existing:
        cleaned_lines, adopted_count = strip_unmanaged_run_daily_cron_jobs(cleaned_lines)
        cleaned_lines, removed_legacy_comments = strip_legacy_scheduler_comment_lines(cleaned_lines)

    next_lines = list(cleaned_lines)
    if next_lines and next_lines[-1].strip():
        next_lines.append("")
    next_lines.extend(build_managed_cron_block(cron_job))

    write_error = write_user_crontab_lines(next_lines)
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
        "env_file": env_file_status(env_file_path),
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
    current_lines, read_error = read_user_crontab_lines()
    if read_error:
        console.print(f"[red]Could not read crontab: {read_error}[/red]")
        return

    cleaned_lines, removed = strip_managed_cron_block(current_lines)
    if not removed:
        result = {"removed": False, "detail": "No managed schedule found."}
        if as_json:
            click.echo(json.dumps(result, indent=2))
        else:
            console.print("[yellow]No managed schedule found.[/yellow]")
        return

    write_error = write_user_crontab_lines(cleaned_lines)
    if write_error:
        console.print(f"[red]Could not remove schedule: {write_error}[/red]")
        return

    result = {"removed": True, "detail": "Managed schedule removed."}
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    console.print("[green]✓ Managed schedule removed.[/green]")
