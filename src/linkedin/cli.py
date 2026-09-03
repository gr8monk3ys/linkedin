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
import shlex
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from linkedin.ai.client import AIResult
from linkedin.app import App
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
from linkedin.data.json_store import load_json, save_json
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
    next_scheduled_run,
    parse_schedule_time,
    runner_tokens_from_option,
    scheduled_run_for_date,
)
from linkedin.services.automation_service import publish_unreviewed
from linkedin.services.contact_service import (
    STATUS_RULES,
    import_scraped_profile,
    import_search_results,
    parse_iso_date,
)
from linkedin.services.daily_run import DailyRun, RunConfig, build_plan
from linkedin.services.diagnostics import diagnostics, overall_status
from linkedin.services.inbox_service import inbound_from_strangers, review_proposals, update_thread_index
from linkedin.services.planner import command_for, label_for
from linkedin.services.resume_service import (
    ResumeRepoError,
    import_autoapply_applications,
    list_variants,
    match_variants,
    merge_into_applications,
    resolve_pdf,
)
from linkedin.services.run_state import (
    acquire_run_lock,
    append_run_log,
    entry_timestamp,
    load_run_history_entries,
    release_run_lock,
)

console = Console()


def _app_version() -> str:
    """Read package version, falling back when running from source without install."""
    try:
        return version("linkedin")
    except PackageNotFoundError:
        return "0.0.0"


class _AppHandle:
    """The App for this process, built from the environment on first use.

    Commands reach services as `_app.contact_svc`. Nothing is built at import,
    so importing the CLI never touches disk, and a test redirects every store
    by setting LINKEDIN_DATA_DIR and calling `_app.reset()`.
    """

    def __init__(self) -> None:
        self._app: App | None = None

    def get(self) -> App:
        if self._app is None:
            self._app = App.from_env()
        return self._app

    def reset(self, app: App | None = None) -> None:
        self._app = app

    def __getattr__(self, name: str):
        return getattr(self.get(), name)


_app = _AppHandle()


def _warn_if_fallback(result: AIResult, used_context: bool = False) -> None:
    """Say out loud when a draft came from the offline template.

    A template is not a draft: it knows nothing about the conversation and
    cannot use --context. Passing one back silently is how a --context of
    instructions ended up as the message body. The API key commonly lives in
    ~/.linkedin-cli/cron.env, which only cron sources — so scheduled runs get
    real drafts while interactive ones quietly degrade.
    """
    if not result.was_fallback:
        return
    console.print(f"[yellow]⚠ AI unavailable ({result.error}) — this is an offline template, not a draft.[/yellow]")
    if used_context:
        console.print("[yellow]  Your --context was NOT used. Edit before sending.[/yellow]")
    console.print(
        "[dim]  Set ANTHROPIC_API_KEY (one may already be in ~/.linkedin-cli/cron.env).[/dim]"
    )


def load_inbox_proposals() -> list[dict]:
    """Proposed pipeline transitions awaiting confirmation."""
    return load_json(_app.data_dir.inbox_proposals, [])


def save_inbox_proposals(proposals: list[dict]) -> None:
    save_json(_app.data_dir.inbox_proposals, proposals)


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

    return DailyRun(
        _app.get(),
        config,
        on_draft=on_draft if show_drafts else None,
        on_draft_failure=on_draft_failure if show_drafts else None,
        on_retry=None if as_json else on_retry,
        metrics_collector=collect_metrics,
    )


def _render_daily_plan(data: dict) -> None:
    """The terminal view: one Rich table per section, numbering the ones that always show."""
    plan = build_plan(data)
    profile = data.get("profile")
    console.print("\n[bold]📌 Daily Plan[/bold]\n")
    if profile:
        console.print(f"[bold]Focus:[/bold] {profile.get('target_role', 'Role not set')} | {profile.get('name', 'Profile')}")
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
@click.option("--resume-file", "-r", default="", help="Load resume text from a .txt file instead of typing")
def profile_setup(resume_file):
    """Set up your profile for personalized drafts."""
    console.print("\n[bold]Profile Setup[/bold]")
    console.print("This info helps AI generate personalized outreach.\n")

    existing = _app.profile_svc.get_profile()

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

    # Resume text
    current_resume = existing.get("resume_text", "") if existing else ""
    if resume_file:
        try:
            with open(resume_file) as fh:
                resume_text = fh.read()
            console.print(f"[green]Loaded resume from {resume_file}[/green]")
        except OSError as e:
            console.print(f"[yellow]Warning: could not read {resume_file}: {e}. Keeping existing.[/yellow]")
            resume_text = current_resume
    else:
        has_resume = bool(current_resume)
        update_resume = click.confirm(
            f"{'Update' if has_resume else 'Add'} resume text? "
            f"{'(currently set — press N to keep)' if has_resume else '(used for AI resume tailoring, cover letters, skills gap)'}",
            default=not has_resume,
        )
        if update_resume:
            console.print("[dim]Paste your resume text below. Enter a blank line then press Enter to finish.[/dim]")
            lines = []
            prev_blank = False
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line == "" and prev_blank:
                    break
                prev_blank = line == ""
                lines.append(line)
            resume_text = "\n".join(lines).rstrip()
        else:
            resume_text = current_resume
    data["resume_text"] = resume_text

    _app.profile_svc.save_profile(data)
    console.print("\n[green]✓ Profile saved![/green]")


@profile.command("show")
def profile_show():
    """Display your saved profile."""
    data = _app.profile_svc.get_profile()

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
    if data.get("copy_source"):
        console.print(f"[dim]Headline and About come from the {data['copy_source']} (docs/linkedin-copy.md); the local copy is a fallback.[/dim]")


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
    company = _app.company_svc.add_company(name, industry, size, linkedin, website, why, priority)
    console.print(f"\n[green]✓ Added company: {name} ({industry})[/green]")
    console.print(f"  ID: #{company['id']} | Priority: {priority}")


@companies.command("list")
@click.option("--priority", "-p", type=click.Choice(COMPANY_PRIORITIES + ["all"]), default="all", help="Filter by priority")
@click.option("--industry", "-i", default=None, help="Filter by industry")
def companies_list_cmd(priority, industry):
    """List all target companies."""
    result = _app.company_svc.list_companies(priority, industry)

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
    result = _app.company_svc.get_company(company_id)
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
    result = _app.company_svc.update_company(company_id, priority, notes, add_role, linkedin, website)
    if not result:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Updated company #{company_id}[/green]")


@companies.command("delete")
@click.argument("company_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to delete this company?")
def companies_delete(company_id):
    """Delete a company."""
    result = _app.company_svc.delete_company(company_id)
    if not result:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Deleted company #{company_id}: {result['name']}[/green]")


@companies.command("contacts")
@click.argument("company_id", type=int)
def companies_contacts(company_id):
    """List contacts at a company."""
    company, company_contacts = _app.company_svc.get_company_contacts(company_id)

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
    result = _app.contact_svc.add_contact(name, title, company, linkedin, notes, company_id, email, source, referral_id)

    if isinstance(result, str):
        console.print(f"[red]{result}[/red]")
        return

    console.print(f"\n[green]✓ Added: {name} ({title} at {result['company']})[/green]")
    console.print(f"  ID: #{result['id']}")
    if company_id:
        console.print(f"  Linked to company #{company_id}")


@contacts.command("delete")
@click.argument("contact_id", type=int)
@click.confirmation_option(prompt="Delete this contact? Their drafts and history stay behind.")
def contacts_delete(contact_id):
    """Delete a contact."""
    contact = _app.contact_svc.contacts.get(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    _app.contact_svc.delete_contact(contact_id)
    console.print(f"[green]Deleted {contact.get('name', 'contact')} (#{contact_id}).[/green]")


@contacts.command("list")
@click.option("--status", "-s", type=click.Choice(CONTACT_STATUSES + ["all"]), default="all")
@click.option("--company", "-c", default=None, help="Filter by company name")
@click.option("--company-id", type=int, default=None, help="Filter by company ID")
@click.option("--source", type=click.Choice(CONTACT_SOURCES + ["all"]), default="all", help="Filter by source")
def contacts_list(status, company, company_id, source):
    """List all contacts."""
    from datetime import datetime

    filtered = _app.contact_svc.list_contacts(status, company, company_id, source)

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
        follow_up_date = parse_iso_date(follow_up)
        if follow_up_date is not None and follow_up_date < datetime.now().date():
            follow_up = f"[red]⚠ {follow_up}[/red]"
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
    result = _app.contact_svc.update_contact(contact_id, status, notes, follow_up, email)
    if not result:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    feedback = None
    if status:
        feedback = _app.template_svc.auto_record_outcome(contact_id, status)

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
    result = _app.contact_svc.view_contact(contact_id)
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
    stats = _app.contact_svc.get_stats()

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
    contact = _app.contact_svc.get_contact(contact_id)
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
    error = _app.contact_svc.link_company(contact_id, company_id)
    if error:
        console.print(f"[red]{error}[/red]")
        return

    contact = _app.contact_svc.get_contact(contact_id)
    company = _app.company_svc.companies.get(company_id)
    console.print(f"[green]✓ Linked {contact['name']} to {company['name']}[/green]")


@contacts.command("due")
@click.option("--days", "-d", type=int, default=0, help="Show follow-ups due within N days (0 = overdue only)")
def contacts_due(days):
    """Show contacts with overdue or upcoming follow-ups."""
    all_contacts = _app.contact_svc.list_contacts()
    if not all_contacts:
        console.print("[yellow]No contacts yet[/yellow]")
        return

    due_data = _app.contact_svc.get_due_contacts(days)

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
            console.print(f"  ! {contact.get('name', '')} ({contact.get('company', '')}) - [red]{days_overdue} days overdue[/red]")
            console.print(f"    Status: {contact.get('status', '').replace('_', ' ')}")
            console.print(f"    → linkedin-cli drafts follow-up {contact['id']}\n")

    if due_today:
        console.print("\n[bold yellow]📅 Due Today[/bold yellow]\n")
        for contact, follow_date, _ in due_today:
            console.print(f"  ! {contact.get('name', '')} ({contact.get('company', '')})")
            console.print(f"    Status: {contact.get('status', '').replace('_', ' ')}")
            console.print(f"    → linkedin-cli drafts follow-up {contact['id']}\n")

    if upcoming:
        console.print("\n[bold cyan]📆 Upcoming Follow-ups[/bold cyan]\n")
        for contact, follow_date, days_until in upcoming:
            console.print(f"  - {contact.get('name', '')} ({contact.get('company', '')}) - [dim]in {-days_until} days[/dim]")

    if stale:
        stale_after = STATUS_RULES["connection_sent"]["after_days"]
        console.print(f"\n[bold yellow]📤 Stale Connection Requests (>{stale_after} days)[/bold yellow]\n")
        for contact, days_since in stale:
            console.print(f"  ! {contact.get('name', '')} ({contact.get('company', '')}) - {days_since} days ago")
            console.print("    → Consider sending a follow-up or finding another contact\n")


@contacts.command("next-actions")
@click.option("--limit", "-l", type=int, default=10, help="Maximum number of actions to show")
@click.option("--generate-drafts", is_flag=True, help="Generate draft messages for shown actions")
@click.option("--save-drafts", is_flag=True, help="Save generated drafts automatically")
def contacts_next_actions(limit, generate_drafts, save_drafts):
    """Show prioritized next actions for your outreach pipeline."""
    if save_drafts:
        generate_drafts = True

    actions = _app.contact_svc.get_next_actions(limit=limit, scores=_app.ranking_svc.scores())
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
        table.add_row(
            str(action["priority"]),
            display_name,
            label_for(action["action"]),
            action["reason"],
            command_for(action["action"], contact_id),
        )

    console.print(table)

    if not generate_drafts:
        return

    summary = _daily_run(RunConfig(save_drafts=save_drafts)).draft_for_actions(actions, save=save_drafts)
    _print_draft_summary(summary)


@contacts.command("dedupe")
@click.option("--min-score", type=float, default=0.65, help="Minimum duplicate confidence score (0.0-1.0)")
@click.option("--limit", type=int, default=20, help="Maximum duplicate pairs to show")
def contacts_dedupe(min_score, limit):
    """Find likely duplicate contacts."""
    candidates = _app.contact_svc.find_duplicate_candidates(min_score=min_score, limit=limit)
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
    result = _app.contact_svc.merge_contacts(primary_id, duplicate_id, prefer=prefer)
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
    follow_up_date = _app.contact_svc.set_reminder(contact_id, days, date)
    if not follow_up_date:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    contact = _app.contact_svc.get_contact(contact_id)
    console.print(f"[green]✓ Reminder set for {contact['name']}: {follow_up_date}[/green]")


@contacts.command("rank")
@click.option("--limit", "-l", type=int, default=20, help="Rows to show")
@click.option("--bottom", is_flag=True, help="Show the lowest-ranked contacts instead (never the pinned ones)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def contacts_rank(limit, bottom, as_json):
    """Rank contacts by how much they matter for your target role.

    The daily connection budget goes to the top of this list. Pinned contacts
    are exempt: always first, never in --bottom. Pin with: contacts pin ID
    """
    rows = _app.ranking_svc.bottom(limit) if bottom else _app.ranking_svc.rank()[:limit]
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[dim]No contacts to rank.[/dim]")
        return
    table = Table(title="Lowest-ranked contacts (unpinned)" if bottom else "Contacts by career priority")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Contact", style="cyan")
    table.add_column("Title")
    table.add_column("Company")
    table.add_column("Status", style="dim")
    table.add_column("Why", style="dim")
    for r in rows:
        name = f"★ {r['name']}" if r["pinned"] else r["name"]
        table.add_row(str(r["score"]), name, r["title"], r["company"], r["status"], "; ".join(r["reasons"]))
    console.print(table)
    if not bottom:
        console.print("[dim]★ pinned — exempt from ranking. `contacts pin ID` / `contacts pin ID --unpin`.[/dim]")


@contacts.command("pin")
@click.argument("contact_id", type=int)
@click.option("--unpin", is_flag=True, help="Remove the pin")
def contacts_pin(contact_id, unpin):
    """Pin a contact: exempt from ranking, always followed (`automate engage --pinned`)."""
    contact = _app.contact_svc.set_pinned(contact_id, not unpin)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    console.print(f"[green]{'Unpinned' if unpin else 'Pinned'} #{contact_id} {contact['name']}.[/green]")


@contacts.command("repair")
@click.option("--dry-run", is_flag=True, help="Show what would be fixed without writing")
def contacts_repair(dry_run):
    """Backfill missing timestamps and follow-up dates so contacts become actionable."""
    result = _app.contact_svc.repair_contacts(dry_run=dry_run)
    if not result["total"]:
        console.print("[green]All contacts already have timestamps and follow-up dates.[/green]")
        return

    table = Table(title=f"{'Would repair' if dry_run else 'Repaired'} {result['total']} contact(s)")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Fixed")
    table.add_column("Follow-up")
    for row in result["repaired"]:
        table.add_row(
            str(row["contact_id"]),
            row["name"],
            row["status"].replace("_", " "),
            ", ".join(row["fixes"]),
            row["follow_up_date"] or "-",
        )
    console.print(table)
    if dry_run:
        console.print("[yellow]Dry run — nothing written. Re-run without --dry-run to apply.[/yellow]")


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
    result = _app.contact_svc.enroll_campaign(
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
        status = _app.contact_svc.campaign_status(contact_id)
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

    rows = _app.contact_svc.list_campaign_contacts(active_only=active_only, campaign_name=campaign_name)
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
    due = _app.contact_svc.get_due_campaign_steps(limit=limit)
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
    result = _app.contact_svc.advance_campaign(contact_id, complete=complete)
    if result is None:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return
    if isinstance(result, str):
        console.print(f"[yellow]{result}[/yellow]")
        return

    status = _app.contact_svc.campaign_status(contact_id) or {}
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
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating connection request for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_connection(contact_id)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Connection Request Draft", border_style="green"))
    _warn_if_fallback(result, used_context=False)
    console.print(f"\n[dim]Characters: {len(draft)}/300[/dim]")

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "connection", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("message")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="Additional context for the message")
def drafts_message(contact_id, context):
    """Generate a personalized follow-up message."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating message for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_message(contact_id, context)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Message Draft", border_style="blue"))
    _warn_if_fallback(result, used_context=True)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "message", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("intro-request")
@click.argument("contact_id", type=int)
@click.option("--to", "target_id", type=int, required=True, help="Contact ID to be introduced to")
def drafts_intro_request(contact_id, target_id):
    """Generate a message asking for an introduction to another contact."""
    console.print("\n[bold]Generating intro request...[/bold]\n")

    result = _app.draft_svc.generate_intro_request(contact_id, target_id)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Introduction Request Draft", border_style="magenta"))
    _warn_if_fallback(result, used_context=False)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "intro_request", draft, source=result.source, target_contact_id=target_id)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("thank-you")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="What to thank them for")
def drafts_thank_you(contact_id, context):
    """Generate a thank you message after a call or meeting."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating thank you note for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_thank_you(contact_id, context)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Thank You Note Draft", border_style="green"))
    _warn_if_fallback(result, used_context=True)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "thank_you", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("follow-up")
@click.argument("contact_id", type=int)
@click.option("--attempt", "-a", type=int, default=1, help="Which follow-up attempt (1, 2, or 3)")
def drafts_follow_up(contact_id, attempt):
    """Generate a follow-up message after no response."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating follow-up #{attempt} for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_follow_up(contact_id, attempt)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title=f"Follow-up #{attempt} Draft", border_style="yellow"))
    _warn_if_fallback(result)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, f"follow_up_{attempt}", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("batch-connections")
@click.option("--limit", "-l", type=int, default=5, help="Max number of drafts to generate")
@click.option("--save-all", is_flag=True, help="Save all drafts without prompting")
def drafts_batch_connections(limit, save_all):
    """Generate connection requests for all not_contacted contacts."""
    error, results = _app.draft_svc.generate_batch_connections(limit)

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    if not results:
        console.print("[green]✓ All contacts have been contacted![/green]")
        return

    console.print(f"\n[bold]Generating connection requests for {len(results)} contacts...[/bold]\n")

    generated = 0
    for contact, result in results:
        draft = result.text
        console.print(f"\n[cyan]{contact['name']}[/cyan] ({contact['title']} at {contact['company']}):")
        console.print(Panel(draft, border_style="green"))
        _warn_if_fallback(result)
        console.print(f"[dim]Characters: {len(draft)}/300[/dim]\n")

        if save_all or click.confirm("Save this draft?"):
            _app.draft_svc.save_draft(contact["id"], "connection", draft, source=result.source)
            generated += 1

    console.print(f"\n[green]✓ Generated and saved {generated} drafts![/green]")


@drafts.command("delete")
@click.argument("draft_id", type=int)
@click.confirmation_option(prompt="Delete this draft?")
def drafts_delete(draft_id):
    """Delete a saved draft."""
    if _app.draft_svc.delete_draft(draft_id):
        console.print(f"[green]Deleted draft #{draft_id}.[/green]")
    else:
        console.print(f"[red]Draft #{draft_id} not found.[/red]")
        raise SystemExit(1)


@drafts.command("list")
def drafts_list_cmd():
    """List all saved drafts."""
    result = _app.draft_svc.list_drafts()

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
    draft = _app.draft_svc.get_draft(draft_id)
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
    error, suggestions = _app.discover_svc.discover_contacts(company, role)

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
    error, suggestions = _app.discover_svc.discover_companies()

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
    content = _app.research_svc.get_engagement_strategies()
    console.print(Markdown(content))


@research.command("ideas")
@click.option("--topic", "-t", default=None, help="Topic to generate ideas for")
def research_ideas(topic):
    """Generate post ideas based on your profile."""
    focus, result = _app.research_svc.generate_ideas(topic)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    ideas = result.text

    console.print(f"\n[bold]Generating post ideas for: {focus}...[/bold]\n")
    console.print(Panel(ideas, title="Post Ideas", border_style="green"))

    if click.confirm("\nSave these ideas?"):
        _app.research_svc.save_ideas(focus, ideas)
        console.print("[green]✓ Ideas saved![/green]")


@research.command("draft-post")
@click.argument("topic")
@click.option("--style", "-s", type=click.Choice(["story", "listicle", "contrarian", "how-to"]), default="story")
def research_draft_post(topic, style):
    """Generate a full post draft."""
    console.print(f"\n[bold]Generating {style} post about: {topic}...[/bold]\n")

    result = _app.research_svc.generate_post_draft(topic, style)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text
    console.print(Panel(draft, title=f"Post Draft ({style})", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _app.research_svc.save_post_draft(topic, style, draft)
        console.print("[green]✓ Post draft saved![/green]")


@research.command("hashtags")
@click.argument("topic")
def research_hashtags(topic):
    """Get hashtag recommendations for a topic."""
    console.print(f"\n[bold]Finding hashtags for: {topic}...[/bold]\n")

    result = _app.research_svc.generate_hashtags(topic)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    hashtags = result.text
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
        count, out_file = _app.data_svc.export_contacts(output, fmt)
        if count:
            console.print(f"[green]✓ Exported {count} contacts to {out_file}[/green]")
        else:
            console.print("[yellow]No contacts to export[/yellow]")

    if data_type in ("companies", "all"):
        comp_output = output
        if data_type == "all" and output:
            out_path = Path(output)
            if "contacts" in out_path.stem:
                comp_output = str(out_path.with_name(out_path.name.replace("contacts", "companies", 1)))
            else:
                comp_output = str(out_path.with_name(f"{out_path.stem}_companies{out_path.suffix}"))
        count, out_file = _app.data_svc.export_companies(comp_output, fmt)
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
        count = _app.data_svc.import_contacts(file_path, merge)
        console.print(f"[green]✓ Imported {count} contacts[/green]")
    else:
        count = _app.data_svc.import_companies(file_path, merge)
        console.print(f"[green]✓ Imported {count} companies[/green]")


@data.command("backup")
@click.option("--output", "-o", default=None, help="Output backup file path")
@click.option("--verify", is_flag=True, help="Verify backup integrity after creation")
def data_backup(output, verify):
    """Create a backup of all data files."""
    backup_name, backed_up = _app.data_svc.create_backup(output)
    console.print(f"[green]✓ Backup created: {backup_name}[/green]")
    console.print(f"  Backed up {backed_up} files")
    if verify:
        report = _app.data_svc.verify_backup(backup_name)
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

    restored = _app.data_svc.restore_backup(backup_file, dry_run=dry_run)
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
    report = _app.data_svc.verify_backup(backup_file)
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
    backups = _app.data_svc.list_backups()

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
    data = _app.dashboard_svc.get_dashboard_data()

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
    config = RunConfig(actions_limit=actions_limit, postings_limit=postings_limit, min_posting_score=min_posting_score, save_recap=save_recap, recap_dir=recap_dir)
    _emit_daily_run_output(_daily_run(config).cycle(), as_json=as_json)


@cli.command("run-daily")
@click.option("--actions-limit", type=int, default=8, help="Maximum prioritized actions to show")
@click.option("--postings-limit", type=int, default=5, help="Maximum job postings to show")
@click.option("--min-posting-score", type=int, default=40, help="Minimum posting match score (0-100)")
@click.option("--save-recap", is_flag=True, help="Save each run as a markdown recap")
@click.option("--recap-dir", default="", help="Optional output directory for recap files")
@click.option("--generate-drafts", is_flag=True, help="Generate drafts from prioritized actions on each run")
@click.option("--save-drafts", is_flag=True, help="Save generated drafts on each run")
@click.option("--collect-metrics", is_flag=True, help="Read the account's metrics (headless browser) before each run; the 14-day baseline")
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
    collect_metrics,
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
    config = RunConfig(
        actions_limit=actions_limit, postings_limit=postings_limit, min_posting_score=min_posting_score,
        save_recap=save_recap, recap_dir=recap_dir, generate_drafts=generate_drafts, save_drafts=save_drafts,
        schedule_time=schedule_time, idempotency_key=idempotency_key, allow_duplicate=allow_duplicate,
        notify_webhook=notify_target, notify_on_success=notify_on_success,
        failure_streak_threshold=failure_streak_threshold, notify_on_recovery=notify_on_recovery,
        retry_attempts=retry_attempts, retry_backoff_seconds=retry_backoff_seconds, collect_metrics=collect_metrics,
    )
    run = _daily_run(config, show_drafts=False, as_json=as_json)

    lock_acquired, lock_error = acquire_run_lock(_app.data_dir, lock_ttl_minutes=lock_ttl_minutes)
    if not lock_acquired:
        now = datetime.now().isoformat(timespec="seconds")
        skipped = {"status": "skipped_locked", "trigger": "startup", "reason": lock_error, "started_at": now, "finished_at": now}
        append_run_log(_app.data_dir, skipped)
        _emit_run_status(skipped, as_json=as_json)
        return

    try:
        if not watch:
            result = run.execute("manual", datetime.now())
            _emit_run_result(result, as_json)
            # A stalled planner and a crashed run must both be visible to whatever
            # scheduled us. Reporting exit 0 is how five months of empty runs hid.
            if result.get("status") in ("no_actions", "failed"):
                raise SystemExit(1)
            return

        try:
            next_scheduled_run(schedule_time)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
            return

        runs_completed = 0
        if not as_json:
            console.print(f"[bold]Daily runner started[/bold] (time={schedule_time}, max_runs={'unlimited' if max_runs == 0 else max_runs})")

        if catch_up_missed and not run_now:
            now = datetime.now()
            scheduled_today = scheduled_run_for_date(schedule_time, now.date())
            if now >= scheduled_today:
                _emit_run_result(run.execute("watch_catch_up", scheduled_today, watch_mode=True), as_json)
                runs_completed += 1
                if max_runs and runs_completed >= max_runs:
                    return

        if run_now:
            _emit_run_result(run.execute("watch_run_now", datetime.now(), watch_mode=True), as_json)
            runs_completed += 1
            if max_runs and runs_completed >= max_runs:
                return

        while True:
            next_run = next_scheduled_run(schedule_time)
            wait_seconds = max(1, int((next_run - datetime.now()).total_seconds()))
            if not as_json:
                console.print(f"\n[dim]Next run at {next_run.strftime('%Y-%m-%d %H:%M:%S')} (in {wait_seconds} sec)[/dim]")
            time.sleep(wait_seconds)
            _emit_run_result(run.execute("watch_scheduled", next_run, watch_mode=True), as_json)
            runs_completed += 1
            if max_runs and runs_completed >= max_runs:
                if not as_json:
                    console.print(f"\n[green]Reached max runs ({max_runs}). Stopping.[/green]")
                return
    except KeyboardInterrupt:
        if not as_json:
            console.print("\n[yellow]Stopped run-daily.[/yellow]")
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
        filtered = [
            entry for entry in filtered
            if (timestamp := entry_timestamp(entry)) and timestamp >= cutoff
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
        shown.append({"name": "latest_run", "status": latest.get("status", "unknown"), "detail": f"{str(latest.get('finished_at', '-'))[:19]} | trigger={latest.get('trigger', '-')}"})
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
@click.option("--probe-ai", is_flag=True, help="Make one tiny API call to prove the key works (presence is not validity)")
@click.option("--json", "as_json", is_flag=True, help="Output doctor report as JSON")
def automation_doctor(schedule_time, lock_ttl_minutes, webhook_url, fix, run_smoke, probe_ai, as_json):
    """Diagnose daily-run health and optionally apply fixes. The one check list; `health` was a second copy."""
    fixes: list[str] = []
    errors: list[str] = []
    cron_lines, cron_error = read_user_crontab_lines()
    checks, facts = diagnostics(
        _app.get(), cron_lines=cron_lines, cron_error=cron_error,
        schedule_time=schedule_time, lock_ttl_minutes=lock_ttl_minutes, webhook_url=webhook_url, probe_ai=probe_ai,
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
                default_scheduler_runner_tokens(), save_recap=True, generate_drafts=True, save_drafts=True, collect_metrics=True,
                retry_attempts=2, retry_backoff_seconds=10.0, failure_streak_threshold=3, notify_on_recovery=True, notify_webhook="",
            )
            cron_command = build_cron_shell_command(Path.cwd().resolve(), run_tokens, env_file=env_file)
            job_line = build_managed_cron_job_line(
                schedule_time=schedule_time, cron_command=cron_command,
                stdout_log=_app.data_dir.cron_out_log, stderr_log=_app.data_dir.cron_err_log,
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
            RunConfig(actions_limit=4, postings_limit=3, schedule_time=schedule_time,
                      idempotency_key=f"doctor-smoke-{datetime.now().date().isoformat()}", allow_duplicate=True,
                      retry_attempts=0, retry_backoff_seconds=0.0),
            show_drafts=False, as_json=True,
        )
        smoke_result = smoke.execute("doctor_smoke", datetime.now())
        checks.append({"name": "smoke_run", "status": "ok" if smoke_result.get("status") == "success" else "warn", "detail": smoke_result.get("status", "unknown")})

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
@click.option("--collect-metrics/--no-collect-metrics", default=True, help="Read account metrics (headless browser) on each scheduled run")
@click.option("--adopt-existing/--no-adopt-existing", default=True, help="Replace unmanaged run-daily cron entries")
@click.option("--env-file", default=str(default_automation_env_file(_app.data_dir)), help="Env file sourced by cron before run-daily")
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
    data = _app.analytics_svc.get_summary()

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
    funnel = _app.analytics_svc.get_conversion_funnel()
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
    data = _app.analytics_svc.get_velocity(weeks)

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
    error, result = _app.market_svc.analyze_market(role, industry)
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
    error, result = _app.market_svc.estimate_salary(role, location)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("trends")
@click.option("--industry", default="", help="Industry to analyze")
def market_trends(industry):
    """Get AI hiring trend analysis."""
    console.print("\n[bold]Analyzing trends...[/bold]\n")
    error, result = _app.market_svc.analyze_trends(industry)
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
    posting = _app.market_svc.add_posting({
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
        imported, skipped = _app.market_svc.import_postings(file_path, merge=merge)
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
    postings = _app.market_svc.list_postings(limit=limit, min_score=min_score)
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
    error, result = _app.optimizer_svc.optimize_headline()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("about")
def optimize_about():
    """Generate optimized About section."""
    console.print("\n[bold]Generating About section...[/bold]\n")
    error, result = _app.optimizer_svc.optimize_about()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("skills")
def optimize_skills():
    """Analyze and optimize skills."""
    console.print("\n[bold]Analyzing skills...[/bold]\n")
    error, result = _app.optimizer_svc.optimize_skills()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("full")
def optimize_full():
    """Full profile optimization review."""
    console.print("\n[bold]Running full optimization review...[/bold]\n")
    error, result = _app.optimizer_svc.optimize_full()
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
    all_templates = _app.template_svc.list_templates()
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
    template = _app.template_svc.save_template(name, template_type, content, variant)
    console.print(f"[green]Template '{template['name']}' saved (ID: {template['id']}, variant {variant})[/green]")


@templates.command("use")
@click.argument("template_id", type=int)
@click.argument("contact_id", type=int)
def templates_use(template_id, contact_id):
    """Apply a template for a specific contact."""
    rendered = _app.template_svc.use_template(template_id, contact_id)
    if not rendered:
        console.print("[red]Template or contact not found.[/red]")
        return
    console.print(Panel(rendered, title="Rendered Template"))


@templates.command("ab-results")
def templates_ab_results():
    """Show A/B test results."""
    results = _app.template_svc.get_ab_results()
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

    if not _app.template_svc.record_response(template_id, count):
        console.print(f"[red]Template #{template_id} not found.[/red]")
        return

    template = _app.template_svc.get_template(template_id)
    console.print(
        f"[green]✓ Recorded {count} response(s) for '{template['name']}' "
        f"(total: {template.get('response_count', 0)})[/green]"
    )


@templates.command("suggest-best")
@click.option("--type", "template_type", required=True, help="Template type (connection, message, follow_up)")
def templates_suggest_best(template_type):
    """Suggest the best-performing template for a type."""
    best = _app.template_svc.suggest_best(template_type)
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
    all_templates = _app.template_svc.list_templates()
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


# =============================================================================
# applications
# =============================================================================


@cli.group()
def applications():
    """Track job applications through their lifecycle."""


@applications.command("add")
@click.option("--company", "-c", required=True, help="Company name")
@click.option("--title", "-t", required=True, help="Job title")
@click.option("--url", "-u", default="", help="Job posting URL")
@click.option("--jd", default="", help="Job description text")
@click.option("--notes", "-n", default="", help="Notes")
def applications_add(company, title, url, jd, notes):
    """Add a new job application."""
    app = _app.application_svc.add_application(company, title, url=url, jd_text=jd, notes=notes)
    console.print(f"[green]Added application #{app['id']}:[/green] {title} at {company}")


@applications.command("list")
@click.option("--status", default="all", help="Filter by status (saved/applied/phone_screen/…)")
@click.option("--company", default="", help="Filter by company name")
def applications_list(status, company):
    """List job applications."""
    apps = _app.application_svc.list_applications(status=status, company=company)
    if not apps:
        console.print("[dim]No applications found.[/dim]")
        return
    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Company", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Applied", style="dim")
    for a in apps:
        table.add_row(
            str(a["id"]),
            a.get("company", ""),
            a.get("title", ""),
            a.get("status", ""),
            (a.get("applied_date") or "—")[:10],
        )
    console.print(table)


@applications.command("view")
@click.argument("application_id", type=int)
def applications_view(application_id):
    """View application details and history."""
    app = _app.application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    console.print(
        Panel(
            f"[bold]{app.get('title')}[/bold] at [cyan]{app.get('company')}[/cyan]\n"
            f"Status: [yellow]{app.get('status')}[/yellow]  |  "
            f"Applied: {(app.get('applied_date') or 'Not yet')[:10]}\n"
            f"URL: {app.get('url') or '—'}\n"
            f"Notes: {app.get('notes') or '—'}\n"
            f"JD: {(app.get('jd_text') or '—')[:200]}"
            f"{'…' if len(app.get('jd_text') or '') > 200 else ''}",
            title=f"Application #{application_id}",
        )
    )
    history = app.get("history") or []
    if history:
        console.print("\n[bold]History:[/bold]")
        for event in history:
            console.print(
                f"  {(event.get('date') or '')[:10]}  {event.get('status')}  {event.get('notes') or ''}"
            )


@applications.command("advance")
@click.argument("application_id", type=int)
@click.option("--status", "-s", required=True, help="New status")
@click.option("--notes", "-n", default="", help="Notes for this stage")
def applications_advance(application_id, status, notes):
    """Advance application to next status."""
    error, app = _app.application_svc.advance(application_id, status, notes=notes)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Advanced #{application_id} to:[/green] {status}")


@applications.command("tailor-resume")
@click.argument("application_id", type=int)
@click.option("--resume-file", "-r", default="", help="Path to resume .txt file (overrides profile resume)")
def applications_tailor_resume(application_id, resume_file):
    """AI-tailor your resume bullets to this job's description."""
    resume_text = ""
    if resume_file:
        try:
            with open(resume_file) as f:
                resume_text = f.read()
        except OSError as e:
            console.print(f"[red]Cannot read file: {e}[/red]")
            raise SystemExit(1)
    error, result = _app.application_svc.tailor_resume(application_id, resume_override=resume_text)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Panel(result, title="Tailored Resume Bullets"))


@applications.command("cover-letter")
@click.argument("application_id", type=int)
def applications_cover_letter(application_id):
    """AI-generate a cover letter for this application."""
    error, result = _app.application_svc.cover_letter(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Panel(result, title="Cover Letter"))


@applications.command("skills-gap")
@click.argument("application_id", type=int)
def applications_skills_gap(application_id):
    """AI skills gap analysis vs the job description."""
    error, result = _app.application_svc.skills_gap(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@applications.command("stats")
def applications_stats():
    """Application funnel statistics."""
    stats = _app.application_svc.get_stats()
    console.print(f"\n[bold]Application Stats[/bold]  (total: {stats['total']})\n")
    for status, count in sorted(stats["by_status"].items()):
        console.print(f"  {status:<20} {count}")


@applications.command("delete")
@click.argument("application_id", type=int)
@click.confirmation_option(prompt="Delete this application?")
def applications_delete(application_id):
    """Delete an application."""
    if not _app.application_svc.delete(application_id):
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Deleted application #{application_id}.[/green]")


# =============================================================================
# interview
# =============================================================================


@cli.group()
def interview():
    """Interview preparation tools."""


@interview.command("prep")
@click.argument("application_id", type=int)
def interview_prep_cmd(application_id):
    """Generate interview questions and model STAR answers (saved for later)."""
    error, result = _app.interview_svc.prep(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("research")
@click.argument("application_id", type=int)
def interview_research(application_id):
    """Generate company research briefing for the interview."""
    error, result = _app.interview_svc.research(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("star")
@click.argument("application_id", type=int)
def interview_star(application_id):
    """Generate STAR method answer scaffolds for top behavioral questions."""
    error, result = _app.interview_svc.star(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("questions")
@click.argument("application_id", type=int)
def interview_questions(application_id):
    """Generate smart questions to ask the interviewer."""
    error, result = _app.interview_svc.questions_to_ask(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("view")
@click.argument("application_id", type=int)
def interview_view(application_id):
    """Show all saved prep for an application."""
    prep = _app.interview_svc.get_prep(application_id)
    if not prep:
        console.print("[dim]No prep saved yet. Run `interview prep <id>` first.[/dim]")
        return
    if prep.get("questions"):
        console.print(Panel("\n".join(prep["questions"]), title="Questions & STAR Answers"))
    if prep.get("star_answers"):
        console.print(Panel("\n".join(prep["star_answers"]), title="STAR Answer Scaffolds"))
    if prep.get("company_research"):
        console.print(Panel(prep["company_research"], title="Company Research"))
    if prep.get("questions_to_ask"):
        console.print(Panel("\n".join(prep["questions_to_ask"]), title="Questions to Ask"))


# =============================================================================
# conversations
# =============================================================================


@cli.group()
def conversations():
    """Log and view LinkedIn message threads with contacts."""


@conversations.command("log")
@click.argument("contact_id", type=int)
@click.option("--from", "sender", required=True, type=click.Choice(["me", "them"]), help="Who sent this message")
@click.option("--text", "-t", required=True, help="Message text")
@click.option("--at", "timestamp", default="", help="Timestamp override (ISO format)")
def conversations_log(contact_id, sender, text, timestamp):
    """Log a message in a contact's conversation thread."""
    try:
        _app.conversation_svc.log(contact_id, sender=sender, text=text, timestamp=timestamp)
        console.print(f"[green]Logged message from {sender}.[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@conversations.command("view")
@click.argument("contact_id", type=int)
def conversations_view(contact_id):
    """View conversation thread with a contact."""
    thread = _app.conversation_svc.get_thread(contact_id)
    if not thread:
        console.print("[dim]No messages logged yet. Use `conversations log` to add messages.[/dim]")
        return
    console.print(f"\n[bold]Conversation — Contact #{contact_id}[/bold]\n")
    for msg in thread.get("messages") or []:
        prefix = "[bold cyan][Me][/bold cyan]" if msg["sender"] == "me" else "[bold yellow][Them][/bold yellow]"
        ts = (msg.get("timestamp") or "")[:16]
        console.print(f"  {prefix}  ({ts})  {msg['text']}")


@conversations.command("export")
@click.argument("contact_id", type=int)
def conversations_export(contact_id):
    """Export conversation thread as plain text."""
    text = _app.conversation_svc.export(contact_id)
    if not text:
        console.print("[dim]No messages logged.[/dim]")
        return
    console.print(text)


# =============================================================================
# calendar
# =============================================================================


@cli.group()
def calendar():
    """Content calendar — schedule and track LinkedIn posts."""


@calendar.command("add")
@click.option("--title", "-t", required=True, help="Post title or topic")
@click.option("--date", "-d", required=True, help="Scheduled date (YYYY-MM-DD)")
@click.option("--draft-id", type=int, default=None, help="Link to a saved draft ID")
@click.option("--platform", default="linkedin", help="Platform (default: linkedin)")
def calendar_add(title, date, draft_id, platform):
    """Add a post to the content calendar."""
    post = _app.calendar_svc.add(title=title, scheduled_date=date, draft_id=draft_id, platform=platform)
    console.print(f"[green]Scheduled post #{post['id']}:[/green] {title} on {date}")


@calendar.command("list")
@click.option("--week", is_flag=True, help="Show upcoming 7 days only")
@click.option("--month", is_flag=True, help="Show upcoming 30 days only")
def calendar_list(week, month):
    """List content calendar."""
    if week:
        posts = _app.calendar_svc.list_upcoming(days=7)
    elif month:
        posts = _app.calendar_svc.list_upcoming(days=30)
    else:
        posts = _app.calendar_svc.list_all()
    if not posts:
        console.print("[dim]No posts scheduled.[/dim]")
        return
    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Draft", style="dim")
    for p in posts:
        table.add_row(
            str(p["id"]),
            p.get("scheduled_date", ""),
            p.get("title", ""),
            p.get("status", ""),
            str(p.get("draft_id") or "—"),
        )
    console.print(table)


@calendar.command("mark-posted")
@click.argument("post_id", type=int)
@click.option("--date", default="", help="Actual posted date (YYYY-MM-DD, defaults to today)")
def calendar_mark_posted(post_id, date):
    """Mark a scheduled post as posted."""
    post = _app.calendar_svc.mark_posted(post_id, posted_date=date)
    if not post:
        console.print(f"[red]Post #{post_id} not found.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Marked post #{post_id} as posted.[/green]")


@calendar.command("stats")
def calendar_stats():
    """Content calendar statistics."""
    stats = _app.calendar_svc.get_stats()
    console.print("\n[bold]Content Calendar Stats[/bold]")
    console.print(f"  Total:     {stats['total']}")
    console.print(f"  Scheduled: {stats['scheduled']}")
    console.print(f"  Posted:    {stats['posted']}")
    console.print(f"  Skipped:   {stats['skipped']}")


# ---------------------------------------------------------------------------
# Resume repo integration (applications group additions)
# ---------------------------------------------------------------------------


@applications.command("suggest-resume")
@click.argument("application_id", type=int)
@click.option("--resume-repo", default="", help="Path to resume repo checkout (or set LINKEDIN_RESUME_REPO)")
def applications_suggest_resume(application_id, resume_repo):
    """Rank resume variants from the resume repo against this job's description."""
    app = _app.application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    try:
        ranked = match_variants(app.get("jd_text", ""), repo_root=resume_repo, title=app.get("title", ""))
    except ResumeRepoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
    if not ranked:
        console.print("[dim]No variants found in the resume repo.[/dim]")
        return
    table = Table(title=f"Resume variants for: {app.get('title', '')} at {app.get('company', '')}")
    table.add_column("Variant")
    table.add_column("Score", justify="right")
    table.add_column("Matched skills")
    for row in ranked:
        matched = ", ".join(row["matched_skills"][:8])
        if len(row["matched_skills"]) > 8:
            matched += ", …"
        table.add_row(row["variant"], str(row["score"]), matched)
    console.print(table)
    console.print(f"\nAttach with: linkedin-cli applications attach-resume {application_id} --variant {ranked[0]['variant']}")


@applications.command("attach-resume")
@click.argument("application_id", type=int)
@click.option("--variant", default="", help="Variant slug (defaults to best match against the JD)")
@click.option("--resume-repo", default="", help="Path to resume repo checkout (or set LINKEDIN_RESUME_REPO)")
def applications_attach_resume(application_id, variant, resume_repo):
    """Attach a resume variant (and its built PDFs) from the resume repo to this application."""
    app = _app.application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    try:
        if not variant:
            ranked = match_variants(app.get("jd_text", ""), repo_root=resume_repo, title=app.get("title", ""))
            if not ranked:
                console.print("[red]No variants found in the resume repo.[/red]")
                raise SystemExit(1)
            variant = ranked[0]["variant"]
            console.print(f"Best match: [bold]{variant}[/bold] (score {ranked[0]['score']})")
        elif variant not in list_variants(resume_repo):
            console.print(f"[red]Unknown variant '{variant}'. Available: {', '.join(list_variants(resume_repo))}[/red]")
            raise SystemExit(1)
        resume_pdf = resolve_pdf(variant, "resume", repo_root=resume_repo)
        cover_pdf = resolve_pdf(variant, "cover_letter", repo_root=resume_repo)
    except ResumeRepoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
    if not resume_pdf:
        console.print(f"[yellow]No built PDF for '{variant}' (run ./build.sh in the resume repo). Recording variant only.[/yellow]")
    error, _ = _app.application_svc.attach_resume(
        application_id,
        variant,
        resume_path=str(resume_pdf) if resume_pdf else "",
        cover_letter_path=str(cover_pdf) if cover_pdf else "",
    )
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Attached resume variant '{variant}' to application #{application_id}.[/green]")
    if resume_pdf:
        console.print(f"  Resume: {resume_pdf}")
    if cover_pdf:
        console.print(f"  Cover letter: {cover_pdf}")


@applications.command("import-autoapply")
@click.option("--resume-repo", default="", help="Path to resume repo checkout (or set LINKEDIN_RESUME_REPO)")
@click.option("--include-queued", is_flag=True, help="Also import queued (not yet applied) jobs as 'saved'")
def applications_import_autoapply(resume_repo, include_queued):
    """Import applications tracked by the resume repo's autoapply pipeline."""
    try:
        entries = import_autoapply_applications(repo_root=resume_repo, include_queued=include_queued)
    except ResumeRepoError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)
    added, skipped = merge_into_applications(entries, _app.application_repo)
    console.print(f"[green]Imported {len(added)} application(s)[/green] ({skipped} already tracked).")
    for app in added:
        console.print(f"  #{app['id']} {app['title']} at {app['company']} [{app['status']}]")


# ---------------------------------------------------------------------------
# Browser automation (automate group) — requires `uv sync --extra automation`
# ---------------------------------------------------------------------------



class _SessionUnavailable(SystemExit):
    pass


def _pause_for_manual_login(page) -> bool:
    """Hand the window to the person: automatic login failed, they finish it."""
    console.print(
        "[yellow]Automatic login failed — complete the login (and any checkpoint) in the browser window.[/yellow]\n"
        "[dim]No credentials are stored unless you ran `linkedin-cli automate setup`; logging in by hand here is fine "
        "and the session is saved afterwards.[/dim]"
    )
    click.pause("Press any key once you are logged in...")
    return page.is_logged_in()


@contextmanager
def _open_session(headless: bool = False, dry_run: bool = False):
    """A logged-in LinkedInSession, or a clear exit. Prints the selector-health report on close.

    A LinkedIn markup change makes every verb come back skipped, which reads as
    "nothing to do". Naming the selectors that matched nothing turns that
    silence into something a person can act on.
    """
    from linkedin.automation.session import AutomationUnavailable, LinkedInSession, LoginFailed

    session = None
    try:
        with LinkedInSession.open(
            _app.data_dir, headless=headless, dry_run=dry_run, on_login_needed=None if headless else _pause_for_manual_login
        ) as session:
            yield session
    except AutomationUnavailable:
        console.print("[red]Browser automation requires extras:[/red] uv sync --extra automation && uv run playwright install chromium")
        raise SystemExit(1)
    except LoginFailed:
        console.print("[red]Not logged in.[/red] Run: linkedin-cli automate login (headful) first, or store credentials with: linkedin-cli automate setup")
        raise SystemExit(1)
    finally:
        if session is not None:
            _report_selector_health(session.selector_health())


def _report_selector_health(report: dict) -> None:
    if report.get("healthy", True):
        return
    console.print(
        "[yellow]Warning: LinkedIn markup may have changed — "
        f"{len(report['misses'])} selector(s) matched nothing.[/yellow]"
    )
    for name, selector in report["selectors"].items():
        console.print(f"  [dim]{name}: {selector}[/dim]")
    console.print("  [dim]Update src/linkedin/automation/selectors.py[/dim]")


def _budget():
    from linkedin.automation.budget import Budget

    return Budget.load(_app.data_dir)


def _load_ai_draft(draft_id: int) -> str:
    """The text of a draft that is known to be the model's, or exit.

    A template, or a row saved before provenance was recorded, is refused:
    nobody knows it is fit to go out under the user's name.
    """
    draft = _app.draft_repo.get(draft_id)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found.[/red]")
        raise SystemExit(1)
    source = draft.get("source")
    if source != "ai":
        what = "an offline template" if source == "template" else "of unknown provenance"
        console.print(f"[red]Refusing to use draft #{draft_id}: it is {what}, not an AI draft.[/red]")
        console.print("[dim]  Regenerate it with AI available, or pass the text explicitly with --text.[/dim]")
        raise SystemExit(1)
    return draft.get("content", "")


def _exit_unless_ok(result, *, dry_run_message: str, failure_prefix: str) -> None:
    """Common tail: say what happened; exit nonzero unless the verb succeeded."""
    if result.dry_run:
        console.print(f"[cyan]Dry run:[/cyan] {dry_run_message}")
        raise SystemExit(0)
    if not result:
        console.print(f"[red]{failure_prefix} ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)


@cli.group("automate")
def automate():
    """Drive LinkedIn in a real browser: search, connect, message, post, engage, apply.

    Uses your own logged-in session with daily budgets and human-like pacing.
    Note: browser automation is against LinkedIn's Terms of Service — use
    deliberately and at your own risk.
    """


@automate.command("setup")
@click.option("--email", prompt=True, help="LinkedIn login email")
@click.option("--password", prompt=True, hide_input=True, help="LinkedIn password")
def automate_setup(email, password):
    """Store LinkedIn credentials in the system keyring."""
    from linkedin.automation.session import setup_credentials

    setup_credentials(email, password)
    console.print("[green]Credentials stored in system keyring.[/green] Next: linkedin-cli automate login")


@automate.command("login")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_login(headless):
    """Log in to LinkedIn and save the session for later commands."""
    with _open_session(headless=headless):
        pass
    console.print(f"[green]Logged in. Session saved to {_app.data_dir.li_session}.[/green]")


@automate.group("limits", invoke_without_command=True)
@click.pass_context
def automate_limits(ctx):
    """Show today's usage against the daily budget (caps live in limits.json)."""
    if ctx.invoked_subcommand is not None:
        return
    table = Table(title="Today's automation budget")
    table.add_column("Kind")
    table.add_column("Used", justify="right")
    table.add_column("Cap", justify="right")
    table.add_column("Remaining", justify="right")
    for kind, row in _budget().summary().items():
        table.add_row(kind, str(row["used"]), str(row["cap"]), str(row["remaining"]))
    console.print(table)
    # soft_wrap: a path must survive copy-paste, and a narrow CI terminal split this one mid-name.
    console.print(f"[dim]Caps: {_app.data_dir.limits}[/dim]", soft_wrap=True)


@automate_limits.command("set")
@click.argument("kind")
@click.argument("cap", type=int)
def automate_limits_set(kind, cap):
    """Set a daily cap, e.g. `automate limits set reaction 10`. Step up only when metrics are clean."""
    from linkedin.automation.budget import KINDS, UnknownKind

    try:
        budget = _budget()
        budget.set_cap(kind, cap)
    except UnknownKind:
        console.print(f"[red]Unknown kind {kind!r}. One of: {', '.join(KINDS)}[/red]")
        raise SystemExit(1)
    console.print(f"[green]{kind}: cap is now {budget.caps[kind]} per day.[/green]")


@automate.command("search")
@click.option("--query", "-q", required=True, help="People search keywords")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_search(query, limit, headless):
    """Preview LinkedIn people search results (no import)."""
    with _open_session(headless=headless) as session:
        result = session.search(query, limit=limit)
    if not result or not result.data:
        console.print(f"[dim]No results ({result.reason or 'empty page'}).[/dim]")
        return
    table = Table(title=f"Search: {query}")
    table.add_column("Name")
    table.add_column("Headline")
    table.add_column("URL")
    for r in result.data:
        table.add_row(r.get("name", ""), r.get("headline", ""), r.get("linkedin_url", ""))
    console.print(table)


@automate.command("import-search")
@click.option("--query", "-q", required=True, help="People search keywords")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_import_search(query, limit, headless):
    """Run a people search and import results into the CRM."""
    with _open_session(headless=headless) as session:
        result = session.search(query, limit=limit)
    if not result:
        console.print(f"[red]Search did not run ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    added, skipped = import_search_results(result.data, _app.contact_repo)
    console.print(f"[green]Imported {len(added)} contact(s)[/green] ({len(skipped)} already in CRM).")
    for c in added:
        console.print(f"  #{c['id']} {c['name']} — {c.get('title', '')}")


@automate.command("profile")
@click.argument("url")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_profile(url, headless):
    """Scrape a single LinkedIn profile into the CRM."""
    with _open_session(headless=headless) as session:
        result = session.scrape(url)
    contact = import_scraped_profile(result.data, url, _app.contact_repo) if result else None
    if not contact:
        console.print(f"[red]Could not scrape that profile ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    console.print(f"[green]Imported contact #{contact['id']}:[/green] {contact['name']} — {contact.get('title', '')}")


@automate.command("connect")
@click.argument("contact_id", type=int)
@click.option("--note", default="", help="Connection note text")
@click.option("--draft-id", type=int, default=None, help="Use a saved draft as the note")
@click.option("--dry-run", is_flag=True, help="Navigate but do not send")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_connect(contact_id, note, draft_id, dry_run, headless):
    """Send a connection request to a CRM contact (uses their linkedin_url)."""
    contact = _app.contact_repo.get(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    if not contact.get("linkedin_url"):
        console.print(f"[red]Contact #{contact_id} has no linkedin_url. Set one with: contacts update {contact_id} --linkedin-url …[/red]")
        raise SystemExit(1)
    if draft_id is not None:
        note = _load_ai_draft(draft_id)
    if len(note) > 300:
        console.print(f"[yellow]Note is {len(note)} chars; LinkedIn caps notes at 300. Truncating.[/yellow]")
        note = note[:300]

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.connect(contact["linkedin_url"], note=note)
    _exit_unless_ok(result, dry_run_message=f"would send connection request to {contact['name']}.", failure_prefix="Could not send the connection request")
    _app.contact_svc.update_contact(contact_id, status="connection_sent")
    console.print(f"[green]Connection request sent to {contact['name']}.[/green] Status → connection_sent")


@automate.command("message")
@click.argument("contact_id", type=int)
@click.option("--text", default="", help="Message text")
@click.option("--draft-id", type=int, default=None, help="Use a saved draft as the message")
@click.option("--dry-run", is_flag=True, help="Navigate but do not send")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_message(contact_id, text, draft_id, dry_run, headless):
    """Send a LinkedIn message to a connected CRM contact."""
    contact = _app.contact_repo.get(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found.[/red]")
        raise SystemExit(1)
    if not contact.get("linkedin_url"):
        console.print(f"[red]Contact #{contact_id} has no linkedin_url.[/red]")
        raise SystemExit(1)
    if draft_id is not None:
        text = _load_ai_draft(draft_id)
    if not text.strip():
        console.print("[red]Nothing to send — pass --text or --draft-id.[/red]")
        raise SystemExit(1)

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.message(contact["linkedin_url"], text)
    _exit_unless_ok(result, dry_run_message=f"would message {contact['name']}.", failure_prefix="Could not send the message")
    _app.contact_svc.update_contact(contact_id, status="messaged")
    console.print(f"[green]Message sent to {contact['name']}.[/green] Status → messaged")


@automate.command("post")
@click.option("--text", default="", help="Post content")
@click.option("--draft-id", type=int, default=None, help="Post a saved draft's content")
@click.option("--calendar-id", type=int, default=None, help="Post a scheduled calendar entry (marks it posted)")
@click.option("--dry-run", is_flag=True, help="Do everything except publish")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_post(text, draft_id, calendar_id, dry_run, headless):
    """Publish a post to your LinkedIn feed (from text, a draft, or the content calendar)."""
    calendar_entry = None
    if calendar_id is not None:
        calendar_entry = _app.calendar_repo.get(calendar_id)
        if not calendar_entry:
            console.print(f"[red]Calendar entry #{calendar_id} not found.[/red]")
            raise SystemExit(1)
        if calendar_entry.get("draft_id") is not None:
            draft_id = calendar_entry["draft_id"]
        elif not text:
            console.print(f"[red]Calendar entry #{calendar_id} has no linked draft — pass --text as well.[/red]")
            raise SystemExit(1)
    if draft_id is not None:
        text = _load_ai_draft(draft_id)
    if not text.strip():
        console.print("[red]Nothing to post — pass --text, --draft-id, or --calendar-id.[/red]")
        raise SystemExit(1)

    console.print(Panel(text, title="Post preview"))
    if not dry_run and not click.confirm("Publish this post to LinkedIn?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.post(text)
    _exit_unless_ok(result, dry_run_message="post not published.", failure_prefix="Post failed")
    urn = result.data or ""
    record = _app.post_svc.record_published(text, urn, draft_id=draft_id, calendar_id=calendar_id)
    if urn:
        console.print(f"[green]Post published.[/green] {urn} (post #{record['id']})")
    else:
        console.print(f"[yellow]Post published, but its ID could not be read back ({result.reason}).[/yellow]")
        console.print("[dim]  It is live on LinkedIn and recorded as post "
                      f"#{record['id']}, but nothing can join it to its metrics.[/dim]")
    if calendar_entry is not None:
        _app.calendar_svc.mark_posted(calendar_id)
        console.print(f"Calendar entry #{calendar_id} marked posted.")


@cli.group("posts")
def posts():
    """Posts that went out through this tool, with the IDs that join them to metrics."""


@posts.command("list")
def posts_list():
    """List published posts, newest first."""
    rows = _app.post_svc.list_posts()
    if not rows:
        console.print("[dim]No posts published through this tool yet.[/dim]")
        return
    table = Table(title="Published posts")
    table.add_column("#", justify="right")
    table.add_column("Posted", style="dim")
    table.add_column("URN")
    table.add_column("Text")
    for p in rows:
        text = p.get("text", "")
        table.add_row(str(p["id"]), p.get("posted_at", "")[:16], p.get("urn") or "[red]unreadable[/red]", text if len(text) <= 60 else text[:57] + "...")
    console.print(table)
    missing = _app.post_svc.unmeasurable()
    if missing:
        console.print(f"[yellow]{len(missing)} post(s) have no URN and cannot be joined to metrics.[/yellow]")


def _review_feed_comment(post: dict, comment_text: str) -> bool:
    """Show a generated comment and ask before publishing it under the user's name."""
    author = post.get("author") or "Unknown"
    content = str(post.get("content", ""))
    preview = content if len(content) <= 280 else content[:277] + "..."

    console.print(f"\n[bold]Post by {author}[/bold]")
    console.print(f"[dim]{preview}[/dim]")
    console.print(f"[cyan]Proposed comment:[/cyan] {comment_text}")
    return click.confirm("Publish this comment?", default=False)


@automate.command("engage")
@click.option("--contact-id", "contact_ids", type=int, multiple=True, help="Like recent posts of this contact (repeatable)")
@click.option("--pinned", is_flag=True, help="Like recent posts of every pinned contact (the people you keep following)")
@click.option("--feed", is_flag=True, help="Like posts on your home feed instead")
@click.option("--likes", default=2, help="Likes per target (default 2)")
@click.option("--comments", default=0, help="With --feed: also leave up to N AI-personalized comments")
@click.option("--dry-run", is_flag=True, help="Navigate but do not click Like")
@click.option("--yes", "-y", is_flag=True, help="Publish AI comments without reviewing each one (not recommended)")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_engage(contact_ids, pinned, feed, likes, comments, dry_run, yes, headless):
    """Warm up target contacts by liking their recent posts (or engage your feed).

    With --feed --comments N, browses the feed and leaves short AI-generated
    comments tailored to each post and your profile, on top of liking.

    \b
    Every AI comment is shown for approval before it is published, because the
    text is generated from a stranger's post and goes out under your own name.
    Pass --yes to skip the review (it will not prompt, and it will post).
    """
    if pinned:
        contact_ids = tuple(contact_ids) + tuple(c["id"] for c in _app.contact_svc.pinned_contacts() if c["id"] not in contact_ids)
        if not contact_ids and not feed:
            console.print("[yellow]No pinned contacts yet. Pin with: linkedin-cli contacts pin ID[/yellow]")
            raise SystemExit(1)
    if not contact_ids and not feed:
        console.print("[red]Pass --contact-id (repeatable), --pinned, and/or --feed.[/red]")
        raise SystemExit(1)
    if comments and not feed:
        console.print("[red]--comments requires --feed (comments run on the feed pipeline).[/red]")
        raise SystemExit(1)
    if comments and yes and not dry_run:
        console.print("[yellow]--yes: AI comments will be published unreviewed under your name.[/yellow]")
    targets = []
    for cid in contact_ids:
        contact = _app.contact_repo.get(cid)
        if not contact:
            console.print(f"[red]Contact #{cid} not found.[/red]")
            raise SystemExit(1)
        if not contact.get("linkedin_url"):
            console.print(f"[yellow]Skipping #{cid} {contact.get('name', '')} — no linkedin_url.[/yellow]")
            continue
        targets.append(contact)

    verb = "would like" if dry_run else "liked"
    total = 0
    with _open_session(headless=headless, dry_run=dry_run) as session:
        for contact in targets:
            result = session.react(likes, profile_url=contact["linkedin_url"])
            liked = int(result.data or 0)
            total += liked
            console.print(f"  {contact['name']}: {verb} {liked} post(s)" + ("" if result else f" [dim]({result.reason})[/dim]"))
        if feed and comments:
            results = _app.automation_svc.engage_feed(
                session,
                limit=max(likes, comments),
                comment_count=comments,
                approve_comment=publish_unreviewed if yes else _review_feed_comment,
            )
            liked = sum(1 for r in results if r["liked"])
            commented = sum(1 for r in results if r["commented"])
            total += liked
            for r in results:
                marks = ("👍" if r["liked"] else "—") + (" 💬" if r["commented"] else "")
                console.print(f"  {marks} {r['author']}: {r['content_preview']}")
                if r["comment_text"]:
                    console.print(f"      [dim]{r['comment_text']}[/dim]")
                elif r.get("skipped_reason"):
                    console.print(f"      [dim]no comment — {r['skipped_reason']}[/dim]")
            console.print(f"  Feed: {verb} {liked}, {'would comment' if dry_run else 'commented'} {commented}")
        elif feed:
            result = session.react(likes)
            liked = int(result.data or 0)
            total += liked
            console.print(f"  Feed: {verb} {liked} post(s)" + ("" if result else f" [dim]({result.reason})[/dim]"))
    console.print(f"[green]{'Dry run — would react' if dry_run else 'Reacted'} to {total} post(s) total.[/green]")


@automate.command("sync-profile")
@click.option("--headline", default="", help="New headline text")
@click.option("--headline-from-profile", is_flag=True, help="Use the headline from your profile (the resume repo's copy when it is on this machine)")
@click.option("--about-from-profile", is_flag=True, help="Use the About text from your profile (resume repo copy)")
@click.option("--about", default="", help="New About section text")
@click.option("--about-file", type=click.Path(exists=True), default=None, help="Read About text from a file")
@click.option("--dry-run", is_flag=True, help="Show what would change without editing")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_sync_profile(headline, headline_from_profile, about, about_from_profile, about_file, dry_run, headless):
    """Push your headline/About to LinkedIn (pairs with `optimizer` output)."""
    if headline_from_profile:
        profile = _app.profile_repo.get()
        if not profile or not profile.get("headline"):
            console.print("[red]No local profile headline found. Run: linkedin-cli profile setup[/red]")
            raise SystemExit(1)
        headline = profile["headline"]
    if about_from_profile:
        profile = _app.profile_repo.get() and _app.profile_svc.get_profile()
        if not profile or not profile.get("about"):
            console.print("[red]No About text in your profile. Put the resume repo on this machine (LINKEDIN_RESUME_REPO) or pass --about-file.[/red]")
            raise SystemExit(1)
        about = profile["about"]
    if about_file:
        about = Path(about_file).read_text()
    if headline_from_profile or about_from_profile:
        source = (_app.profile_svc.get_profile() or {}).get("copy_source", "local profile file")
        console.print(f"[dim]Copy source: {source}[/dim]")
    if not headline and not about:
        console.print("[red]Nothing to sync — pass --headline/--headline-from-profile and/or --about/--about-from-profile/--about-file.[/red]")
        raise SystemExit(1)

    if headline:
        console.print(Panel(headline, title="New headline"))
    if about:
        console.print(Panel(about, title="New About"))
    if not dry_run and not click.confirm("Apply these changes to your LinkedIn profile?"):
        console.print("[dim]Cancelled.[/dim]")
        return

    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.sync_profile(headline=headline, about=about)
    for field_name, status in (result.data or {}).items():
        color = {"updated": "green", "dry_run": "cyan"}.get(status, "red")
        console.print(f"  {field_name}: [{color}]{status}[/{color}]")
    if not result and not result.dry_run:
        console.print("[yellow]LinkedIn's profile editor changes often — update the selectors in selectors.py or edit manually.[/yellow]")
        raise SystemExit(1)


@automate.command("easy-apply")
@click.argument("application_id", type=int)
@click.option("--submit", is_flag=True, help="Actually submit (default stops at the review step)")
@click.option("--resume-repo", default="", help="Path to resume repo checkout (or set LINKEDIN_RESUME_REPO)")
@click.option("--dry-run", is_flag=True, help="Do not open the job page at all")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def automate_easy_apply(application_id, submit, resume_repo, dry_run, headless):
    """Run LinkedIn Easy Apply for a tracked application, using its attached resume PDF."""
    app = _app.application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    if not app.get("url"):
        console.print(f"[red]Application #{application_id} has no job URL.[/red]")
        raise SystemExit(1)

    resume_path = app.get("resume_path", "")
    if not resume_path:
        # Fall back to matching a variant from the resume repo on the fly
        try:
            ranked = match_variants(app.get("jd_text", ""), repo_root=resume_repo, title=app.get("title", ""))
            if ranked:
                pdf = resolve_pdf(ranked[0]["variant"], "resume", repo_root=resume_repo)
                if pdf:
                    resume_path = str(pdf)
                    console.print(f"Using best-match variant [bold]{ranked[0]['variant']}[/bold]: {pdf}")
        except ResumeRepoError:
            console.print("[yellow]No resume attached and no resume repo configured — applying with your LinkedIn default resume.[/yellow]")
    elif not Path(resume_path).exists():
        console.print(f"[yellow]Attached resume {resume_path} no longer exists — applying with your LinkedIn default resume.[/yellow]")
        resume_path = ""

    if dry_run:
        console.print(f"[cyan]Dry run:[/cyan] would Easy Apply to {app['url']} with resume: {resume_path or '(LinkedIn default)'}")
        return
    with _open_session(headless=headless) as session:
        result = session.easy_apply(app["url"], resume_path=resume_path, submit=submit)
        if result.reason == "ready_to_submit" and not headless:
            console.print("[yellow]Stopped at the review step. Review the application in the browser window.[/yellow]")
            if click.confirm("Submit it now?"):
                result = session.record_easy_apply_outcome(session.page.easy_apply(resume_path="", submit=True, max_steps=2))
        elif result.reason == "needs_manual_input" and not headless:
            # The automation never invents an answer, so a wizard that asks a
            # question stops here -- which is most of them. With a person at
            # the window that is a hand-off, not a failure: they finish the
            # form and press Submit themselves, and only their word records it.
            console.print(f"[yellow]{(result.data or {}).get('detail', '')}[/yellow]")
            console.print("[yellow]Finish the remaining questions in the browser window and submit it yourself.[/yellow]")
            click.pause("Press any key once you are done (or have closed the form)...")
            if click.confirm("Did you submit the application?"):
                result = session.record_easy_apply_outcome({"status": "submitted", "detail": "Submitted by hand after automated fill"})
            else:
                result = session.record_easy_apply_outcome({"status": "ready_to_submit", "detail": "Left unsubmitted; still saved in the CRM"})

    detail = (result.data or {}).get("detail", result.reason)
    if result:
        _app.application_svc.advance(application_id, "applied", notes="Submitted via LinkedIn Easy Apply")
        console.print(f"[green]Submitted![/green] Application #{application_id} → applied")
    elif result.reason == "ready_to_submit":
        console.print(f"[yellow]{detail}[/yellow]")
    elif result.reason == "no_easy_apply":
        console.print(f"[yellow]{detail}. This job needs an external application — the resume repo's autoapply pipeline may cover it.[/yellow]")
    else:
        console.print(f"[red]Easy Apply did not complete: {detail}[/red]")
        raise SystemExit(1)


@automate.command("jobs")
@click.option("--query", "-q", required=True, help="Job search keywords")
@click.option("--location", "-L", default="", help="Location filter")
@click.option("--limit", "-l", default=25, help="Max postings to read")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
@click.option("--dry-run", is_flag=True, help="Show results without importing")
def automate_jobs(query, location, limit, headless, dry_run):
    """Search LinkedIn jobs and import the results as scored postings.

    Read-only against LinkedIn. This is what fills the daily plan's
    opportunities section, which reported "No postings above threshold" every
    morning because nothing had ever imported a posting.
    """
    with _open_session(headless=headless, dry_run=dry_run) as session:
        result = session.jobs(query, location=location, limit=limit)
    results = result.data or []
    if not results:
        console.print(f"[dim]No job results ({result.reason or 'empty page'}).[/dim]")
        return

    table = Table(title=f"Jobs: {query}")
    table.add_column("Title", style="cyan")
    table.add_column("Company")
    table.add_column("Location", style="dim")
    table.add_column("Easy Apply", justify="center")
    for job in results:
        table.add_row(job["title"], job["company"], job["location"], "✓" if job["easy_apply"] else "")
    console.print(table)

    if dry_run:
        console.print(f"[yellow]Dry run — {len(results)} posting(s) not imported.[/yellow]")
        return

    added, skipped = _app.market_svc.import_job_results(results)
    console.print(f"[green]Imported {len(added)} posting(s)[/green]" + (f", skipped {skipped} duplicate(s)" if skipped else ""))


@cli.group("metrics")
def metrics():
    """The account's own numbers over time — the measurement the growth goal is judged by."""


@metrics.command("collect")
@click.option("--posts/--no-posts", default=True, help="Also read impressions for each recorded post")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def metrics_collect(posts, headless):
    """Read followers, connections, profile views, impressions, search appearances, SSI. Read-only."""
    urns = [p["urn"] for p in _app.metrics_svc.post_rows()] if posts else []
    with _open_session(headless=headless) as session:
        result = session.metrics(post_urns=urns)
    if not result:
        console.print(f"[red]Metrics not read ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    entry = _app.metrics_svc.record(result.data)
    unread = [k for k, v in entry.items() if k != "date" and v is None]
    console.print(f"[green]Recorded metrics for {entry['date']}.[/green]")
    _render_metrics(_app.metrics_svc.summary())
    if unread:
        console.print(f"[yellow]Could not read: {', '.join(unread)} — recorded as missing, not zero.[/yellow]")


@metrics.command("show")
@click.option("--days", default=7, help="Delta window in days")
def metrics_show(days):
    """Latest metrics and their change over the window."""
    summary = _app.metrics_svc.summary(days=days)
    if not summary:
        console.print("[dim]No metrics yet. Run: linkedin-cli metrics collect[/dim]")
        return
    console.print(f"[dim]Latest: {_app.metrics_svc.latest()['date']}[/dim]")
    _render_metrics(summary, days=days)
    posts = [p for p in _app.metrics_svc.post_rows() if p.get("impressions") is not None]
    if posts:
        table = Table(title="Post impressions")
        table.add_column("#", justify="right")
        table.add_column("Posted", style="dim")
        table.add_column("Impressions", justify="right")
        table.add_column("Text")
        for p in posts:
            text = p.get("text", "")
            table.add_row(str(p["id"]), p.get("posted_at", "")[:10], str(p["impressions"]), text if len(text) <= 50 else text[:47] + "...")
        console.print(table)


def _render_metrics(summary: list[dict], days: int = 7) -> None:
    table = Table()
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column(f"Δ{days}d", justify="right")
    for m in summary:
        value = "[red]—[/red]" if m["value"] is None else str(m["value"])
        delta = "—" if m["delta"] is None else f"{m['delta']:+d}"
        table.add_row(m["metric"], value, delta)
    console.print(table)


@cli.group("inbox")
def inbox():
    """Read replies and accepted invitations, and confirm what they imply.

    Every other automation action is outbound, so a contact stays at the status
    it was created with until a human retypes it. These commands are the inbound
    edge — and they only ever *propose* a change.
    """


@inbox.command("sync")
@click.option("--limit", "-l", default=25, help="Max message threads to read")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def inbox_sync(limit, headless):
    """Read LinkedIn messaging and sent invitations; save proposed transitions."""
    with _open_session(headless=headless) as session:
        result = session.inbox(thread_limit=limit)
    signals = result.data or {"threads": [], "pending_invitations": None}
    if not result:
        console.print(f"[yellow]Inbox not read ({result.status}: {result.reason}).[/yellow]")

    pending = signals["pending_invitations"]
    if pending is None:
        console.print(
            "[yellow]Could not read the sent-invitation list — skipping acceptance checks.[/yellow]\n"
            "[dim]An empty list would mean 'every invitation was accepted', so it is not assumed.[/dim]"
        )

    contacts = _app.contact_repo.list_all()
    proposals = _app.inbox_svc.propose_transitions(signals["threads"], pending, contacts)
    save_inbox_proposals(proposals)
    index = update_thread_index(load_json(_app.data_dir.thread_index, []), signals["threads"], contacts)
    save_json(_app.data_dir.thread_index, index)

    strangers = inbound_from_strangers(index, datetime.now().date() - timedelta(days=30))
    console.print(f"[dim]Read {len(signals['threads'])} thread(s); {len(strangers)} inbound from strangers in the last 30 days.[/dim]")
    if not proposals:
        console.print("[green]No pipeline changes to propose.[/green]")
        return
    _render_proposals(proposals)
    console.print("\n[dim]Apply with: linkedin-cli inbox review[/dim]")


@inbox.command("list")
def inbox_list():
    """Show proposed transitions awaiting confirmation."""
    proposals = load_inbox_proposals()
    if not proposals:
        console.print("[dim]No pending proposals. Run: linkedin-cli inbox sync[/dim]")
        return
    _render_proposals(proposals)


@inbox.command("review")
@click.option("--yes", is_flag=True, help="Apply every high-confidence proposal without prompting")
def inbox_review(yes):
    """Confirm proposed transitions one at a time and apply them.

    `--yes` applies high-confidence proposals only. A low-confidence proposal
    matched a contact by display name alone, so it is always asked about.
    """
    proposals = load_inbox_proposals()
    if not proposals:
        console.print("[dim]No pending proposals. Run: linkedin-cli inbox sync[/dim]")
        return

    def confirm(proposal: dict, low: bool) -> bool:
        console.print(
            f"\n[bold cyan]{proposal.get('name')}[/bold cyan] "
            f"{proposal.get('from_status')} → {proposal.get('to_status')}"
            + (" [red](matched by name only)[/red]" if low else "")
        )
        console.print(f"  [dim]{proposal.get('evidence', '')}[/dim]")
        return click.confirm("  Apply?", default=not low)

    review = review_proposals(proposals, _app.contact_repo.list_all(), confirm=confirm, yes=yes)
    for proposal, why in review.dropped:
        console.print(f"[yellow]{proposal.get('name')} — dropping this proposal: {why}.[/yellow]")
    for proposal in review.apply:
        _app.contact_svc.update_contact(proposal["contact_id"], status=proposal["to_status"])
    save_inbox_proposals(review.kept)
    console.print(f"\n[green]Applied {len(review.apply)}[/green]" + (f", kept {len(review.kept)} for later" if review.kept else ""))


@inbox.command("strangers")
@click.option("--days", default=30, help="Window in days (default 30)")
def inbox_strangers(days):
    """People who are not contacts and wrote to you in the window — the inbound metric."""
    index = load_json(_app.data_dir.thread_index, [])
    rows = inbound_from_strangers(index, datetime.now().date() - timedelta(days=days))
    console.print(f"[bold]{len(rows)}[/bold] inbound from strangers in the last {days} days" + ("." if rows else " (run: linkedin-cli inbox sync)."))
    if not rows:
        return
    table = Table()
    table.add_column("Name", style="cyan")
    table.add_column("Last wrote", style="dim")
    table.add_column("Profile", style="dim")
    for row in rows:
        table.add_row(row.get("name", ""), row.get("last_message_at", ""), row.get("url", ""))
    console.print(table)


def _render_proposals(proposals: list[dict]) -> None:
    table = Table(title="Proposed pipeline changes")
    table.add_column("Contact", style="cyan")
    table.add_column("Transition", style="yellow")
    table.add_column("Source", style="dim")
    table.add_column("Evidence", style="dim")
    for proposal in proposals:
        marker = " [red](low)[/red]" if proposal.get("confidence") == "low" else ""
        table.add_row(
            proposal.get("name", "Unknown"),
            f"{proposal.get('from_status', '')} → {proposal.get('to_status', '')}{marker}",
            proposal.get("source", ""),
            proposal.get("evidence", ""),
        )
    console.print(table)


if __name__ == "__main__":
    cli()
