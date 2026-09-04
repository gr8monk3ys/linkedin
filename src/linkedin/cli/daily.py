import json
import os
from datetime import datetime, timedelta

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.automate import _open_session, _send_due_connections
from linkedin.constants import (
    DASHBOARD_PIPELINE,
    PRIORITY_EMOJI,
    CompanyPriority,
)
from linkedin.services.daily_run import DailyRun, RunConfig, build_plan
from linkedin.services.run_state import (
    acquire_run_lock,
    append_run_log,
    entry_timestamp,
    load_run_history_entries,
    release_run_lock,
)


def _daily_run(config: RunConfig, *, show_drafts: bool = True, as_json: bool = False) -> DailyRun:
    """A DailyRun wired to this process's App and console."""

    def on_draft(entry: dict) -> None:
        console.print(f"\n[bold cyan]Auto Draft for #{entry['contact_id']} ({entry['name']}):[/bold cyan]")
        console.print(Panel(entry["content"], border_style="cyan"))

    def on_draft_failure(contact_id: int, why: str) -> None:
        console.print(f"[yellow]Could not generate draft for contact #{contact_id}: {why}[/yellow]")

    def on_retry(attempt: int, max_attempts: int, backoff: float) -> None:
        console.print(f"[yellow]Run failed (attempt {attempt}/{max_attempts}); retrying in {backoff:.1f}s...[/yellow]")

    def collect_metrics() -> dict:
        urns = [p["urn"] for p in _app.metrics_svc.post_rows()]
        with _open_session(headless=True) as session:
            result = session.metrics(post_urns=urns)
        if not result:
            return {"error": f"{result.status}: {result.reason}"}
        entry = _app.metrics_svc.record(result.data)
        return {"recorded": entry["date"], "missing": [k for k, v in entry.items() if k != "date" and v is None]}

    def send_connections(actions: list[dict]) -> dict:
        with _open_session(headless=True) as session:
            return _send_due_connections(session, actions)

    return DailyRun(
        _app.get(),
        config,
        on_draft=on_draft if show_drafts else None,
        on_draft_failure=on_draft_failure if show_drafts else None,
        on_retry=None if as_json else on_retry,
        metrics_collector=collect_metrics,
        connection_sender=send_connections,
    )


def _render_daily_plan(data: dict) -> None:
    """The terminal view: one Rich table per section, numbering the ones that always show."""
    plan = build_plan(data)
    profile = data.get("profile")
    console.print("\n[bold]📌 Daily Plan[/bold]\n")
    if profile:
        console.print(
            f"[bold]Focus:[/bold] {profile.get('target_role', 'Role not set')} | {profile.get('name', 'Profile')}"
        )
    else:
        console.print("[yellow]Set up profile for better recommendations: linkedin-cli profile setup[/yellow]")

    number = 0
    for section in plan.sections:
        if section.optional and not section.rows:
            continue
        if section.optional:
            console.print(f"\n[bold]{section.title}[/bold]")
        else:
            number += 1
            console.print(f"\n[bold]{number}) {section.title}[/bold]")
        if not section.rows:
            console.print(f"  [dim]{section.empty}[/dim]")
            continue
        table = Table()
        for column in section.columns:
            table.add_column(column)
        for row in section.rows:
            table.add_row(*row)
        console.print(table)
        if section.hint:
            console.print(f"  [dim]{section.hint}[/dim]")


def _render_generated_drafts(draft_summary: dict) -> None:
    drafts = draft_summary.get("drafts", [])
    console.print("\n[bold]Generated Drafts[/bold]")
    if not drafts:
        console.print("  [dim]No drafts generated from current actions.[/dim]")
        return
    for draft in drafts:
        console.print(f"[bold cyan]Auto Draft for #{draft['contact_id']} ({draft.get('name', 'Unknown')}):[/bold cyan]")
        console.print(Panel(draft["content"], border_style="cyan"))
    _print_draft_summary(draft_summary)


def _print_draft_summary(summary: dict) -> None:
    console.print(
        f"\n[green]Generated {summary.get('generated', 0)} draft(s)[/green]"
        + (f", saved {summary['saved']}" if summary.get("saved") else "")
        + (f", failed {summary['failed']}" if summary.get("failed") else "")
    )


def _emit_daily_run_output(data: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(data, indent=2))
        return
    _render_daily_plan(data)
    draft_summary = data.get("drafts", {})
    if draft_summary.get("generated", 0) or draft_summary.get("drafts"):
        _render_generated_drafts(draft_summary)
    if data.get("recap_path"):
        console.print(f"\n[green]✓ Saved recap: {data['recap_path']}[/green]")


def _emit_run_status(result: dict, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    status = result.get("status", "unknown")
    if status == "skipped_duplicate":
        console.print(f"[yellow]Skipped duplicate run for key '{result.get('idempotency_key', '')}'.[/yellow]")
    elif status == "skipped_locked":
        console.print(f"[yellow]{result.get('reason', 'Run skipped due to lock.')}[/yellow]")
    elif status == "no_actions":
        console.print(f"[red]run-daily planned nothing: {result.get('reason', '')}[/red]")
        console.print("[yellow]Try `linkedin-cli contacts repair`, then `contacts next-actions`.[/yellow]")
    elif status == "failed":
        console.print(f"[red]run-daily failed: {result.get('error') or result.get('reason') or 'Unknown error'}[/red]")
        if result.get("notification_error"):
            console.print(f"[yellow]Notification failed: {result['notification_error']}[/yellow]")


def _emit_run_result(result: dict, as_json: bool) -> None:
    if result.get("status") == "success":
        _emit_daily_run_output(result, as_json=as_json)
    else:
        _emit_run_status(result, as_json=as_json)


@cli.command()
def dashboard():
    """Show overview of your job hunt progress."""
    data = _app.dashboard_svc.get_dashboard_data()

    console.print("\n[bold]📊 Job Hunt Dashboard[/bold]\n")

    # Profile status
    if data["profile"]:
        console.print(
            f"[bold]PROFILE:[/bold] {data['profile'].get('name', 'Set up')} → {data['profile'].get('target_role', 'Role TBD')}"
        )
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
    config = RunConfig(
        actions_limit=actions_limit,
        postings_limit=postings_limit,
        min_posting_score=min_posting_score,
        save_recap=save_recap,
        recap_dir=recap_dir,
    )
    _emit_daily_run_output(_daily_run(config).cycle(), as_json=as_json)


@cli.command("run-daily")
@click.option("--actions-limit", type=int, default=8, help="Maximum prioritized actions to show")
@click.option("--postings-limit", type=int, default=5, help="Maximum job postings to show")
@click.option("--min-posting-score", type=int, default=40, help="Minimum posting match score (0-100)")
@click.option("--save-recap", is_flag=True, help="Save each run as a markdown recap")
@click.option("--recap-dir", default="", help="Optional output directory for recap files")
@click.option("--generate-drafts", is_flag=True, help="Generate drafts from prioritized actions on each run")
@click.option("--save-drafts", is_flag=True, help="Save generated drafts on each run")
@click.option(
    "--collect-metrics",
    is_flag=True,
    help="Read the account's metrics (headless browser) before each run; the 14-day baseline",
)
@click.option(
    "--send-connections",
    is_flag=True,
    help="After the plan, send its connection actions (headless browser) up to the daily budget",
)
@click.option("--time", "schedule_time", default="09:00", help="Daily run time in HH:MM (24-hour local)")
@click.option(
    "--trigger",
    type=click.Choice(["manual", "scheduled"]),
    default="manual",
    help="Who started this run. A scheduled run is keyed to its day so a double fire cannot double run.",
)
@click.option("--retry-attempts", type=int, default=1, help="Additional retries when a run fails")
@click.option("--retry-backoff-seconds", type=float, default=5.0, help="Base delay in seconds between retries")
@click.option("--lock-ttl-minutes", type=int, default=180, help="Minutes before an existing lock is treated as stale")
@click.option("--idempotency-key", default="", help="Optional idempotency key to prevent duplicate runs")
@click.option("--allow-duplicate", is_flag=True, help="Ignore idempotency checks and force execution")
@click.option("--notify-webhook", default="", help="Webhook URL for failure notifications")
@click.option("--notify-on-success", is_flag=True, help="Also notify webhook on successful runs")
@click.option("--failure-streak-threshold", type=int, default=3, help="Notify when N consecutive runs fail")
@click.option(
    "--notify-on-recovery/--no-notify-on-recovery", default=True, help="Notify when a streak failure recovers"
)
@click.option("--json", "as_json", is_flag=True, help="Output each run as JSON")
def run_daily(
    actions_limit,
    postings_limit,
    min_posting_score,
    save_recap,
    recap_dir,
    generate_drafts,
    save_drafts,
    collect_metrics,
    send_connections,
    schedule_time,
    trigger,
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
    """Run the daily plan once. Cron or launchd runs this with --trigger scheduled."""
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
    config = RunConfig(
        actions_limit=actions_limit,
        postings_limit=postings_limit,
        min_posting_score=min_posting_score,
        save_recap=save_recap,
        recap_dir=recap_dir,
        generate_drafts=generate_drafts,
        save_drafts=save_drafts,
        schedule_time=schedule_time,
        idempotency_key=idempotency_key,
        allow_duplicate=allow_duplicate,
        notify_webhook=notify_target,
        notify_on_success=notify_on_success,
        failure_streak_threshold=failure_streak_threshold,
        notify_on_recovery=notify_on_recovery,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
        collect_metrics=collect_metrics,
        send_connections=send_connections,
    )
    run = _daily_run(config, show_drafts=False, as_json=as_json)

    lock_acquired, lock_error = acquire_run_lock(_app.data_dir, lock_ttl_minutes=lock_ttl_minutes)
    if not lock_acquired:
        now = datetime.now().isoformat(timespec="seconds")
        skipped = {
            "status": "skipped_locked",
            "trigger": trigger,
            "reason": lock_error,
            "started_at": now,
            "finished_at": now,
        }
        append_run_log(_app.data_dir, skipped)
        _emit_run_status(skipped, as_json=as_json)
        return

    try:
        result = run.execute(trigger, datetime.now(), scheduled=trigger == "scheduled")
        _emit_run_result(result, as_json)
        # A stalled planner and a crashed run must both be visible to whatever
        # scheduled us. Reporting exit 0 is how five months of empty runs hid.
        if result.get("status") in ("no_actions", "failed"):
            raise SystemExit(1)
    finally:
        release_run_lock(_app.data_dir)


@cli.command("run-history")
@click.option("--limit", type=int, default=20, help="Maximum rows to display")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["all", "success", "failed", "skipped_duplicate", "skipped_locked"]),
    default="all",
    help="Filter by run status",
)
@click.option("--trigger", default="", help="Optional trigger filter (manual, scheduled, doctor_smoke)")
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

    entries = load_run_history_entries(_app.data_dir)
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
        filtered = [entry for entry in filtered if (timestamp := entry_timestamp(entry)) and timestamp >= cutoff]

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
