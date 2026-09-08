import json
from datetime import datetime

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.daily import _daily_run, _print_draft_summary
from linkedin.constants import (
    ACTIVITY_EMOJI,
    CONTACT_SOURCES,
    CONTACT_STATUSES,
    PIPELINE_DISPLAY,
    STATUS_EMOJI,
    ContactStatus,
)
from linkedin.services.contact_service import (
    STATUS_RULES,
    parse_iso_date,
)
from linkedin.services.daily_run import RunConfig
from linkedin.services.planner import command_for, label_for


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

    console.print(f"[green]✓ Updated contact #{contact_id}[/green]")


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

    console.print(
        Panel(
            f"""
[bold]{result["name"]}[/bold]
{result["title"]} at {result["company"]}{company_link}

[cyan]LinkedIn:[/cyan] {result["linkedin_url"]}{email_info}
[cyan]Status:[/cyan] {result["status"].replace("_", " ")}{source_info}{referrer_info}
[cyan]Added:[/cyan] {result["created_at"][:10]}
[cyan]Last Contact:[/cyan] {result.get("last_contact", "Never")[:10] if result.get("last_contact") else "Never"}
[cyan]Follow Up:[/cyan] {result.get("follow_up_date", "Not set")}

[bold]Notes:[/bold]
{result.get("notes", "No notes")}
    """,
            title=f"Contact #{contact_id}",
        )
    )


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
            console.print(
                f"  ! {contact.get('name', '')} ({contact.get('company', '')}) - [red]{days_overdue} days overdue[/red]"
            )
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
            console.print(
                f"  - {contact.get('name', '')} ({contact.get('company', '')}) - [dim]in {-days_until} days[/dim]"
            )

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
@click.option(
    "--prefer", type=click.Choice(["primary", "duplicate"]), default="primary", help="Preferred record fields"
)
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
