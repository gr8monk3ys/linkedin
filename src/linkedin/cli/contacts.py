"""Contacts commands."""

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli import _company_svc, _contact_svc, cli, console
from linkedin.constants import (
    ACTIVITY_EMOJI,
    CONTACT_SOURCES,
    CONTACT_STATUSES,
    PIPELINE_DISPLAY,
    STATUS_EMOJI,
    ContactStatus,
)


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

    if not result.ok:
        console.print(f"[red]{result.error}[/red]")
        return

    contact = result.data
    console.print(f"\n[green]✓ Added: {name} ({title} at {contact['company']})[/green]")
    console.print(f"  ID: #{contact['id']}")
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
        console.print("[yellow]No contacts yet. Run: linkedin contacts add[/yellow]")
        return

    table = Table(title=f"Contacts ({len(filtered)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Company", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Follow Up", style="dim")

    for c in filtered:
        status_value = c.get("status", "not_contacted")
        emoji = STATUS_EMOJI.get(ContactStatus(status_value), "")
        follow_up = c.get("follow_up_date", "")
        if follow_up:
            try:
                follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
                if follow_up_date < datetime.now().date():
                    follow_up = f"[red]⚠ {follow_up}[/red]"
            except (ValueError, AttributeError):
                pass
        table.add_row(
            str(c.get("id", "")),
            c.get("name", ""),
            c.get("title", "")[:30],
            c.get("company", ""),
            f"{emoji} {status_value.replace('_', ' ')}",
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
    if not result.ok:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return
    console.print(f"[green]✓ Updated contact #{contact_id}[/green]")


@contacts.command("view")
@click.argument("contact_id", type=int)
def contacts_view(contact_id):
    """View detailed info for a contact."""
    result = _contact_svc.view_contact(contact_id)
    if not result.ok:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    contact = result.data
    company_link = ""
    if contact.get("company_id"):
        company_link = f" (Company #{contact['company_id']})"

    referrer_info = ""
    referrer = contact.get("referrer")
    if referrer:
        referrer_info = f"\n[cyan]Referred by:[/cyan] {referrer['name']}"

    email_info = f"\n[cyan]Email:[/cyan] {contact.get('email')}" if contact.get("email") else ""
    source_info = f"\n[cyan]Source:[/cyan] {contact.get('source', 'unknown').replace('_', ' ')}"

    console.print(Panel(f"""
[bold]{contact.get('name', '')}[/bold]
{contact.get('title', 'Title not set')} at {contact.get('company', 'Company not set')}{company_link}

[cyan]LinkedIn:[/cyan] {contact.get('linkedin_url') or 'Not set'}{email_info}
[cyan]Status:[/cyan] {contact.get('status', 'not_contacted').replace('_', ' ')}{source_info}{referrer_info}
[cyan]Added:[/cyan] {contact.get('created_at', 'Unknown')[:10]}
[cyan]Last Contact:[/cyan] {contact.get('last_contact', 'Never')[:10] if contact.get('last_contact') else 'Never'}
[cyan]Follow Up:[/cyan] {contact.get('follow_up_date', 'Not set')}

[bold]Notes:[/bold]
{contact.get('notes', 'No notes')}
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
    result = _contact_svc.link_company(contact_id, company_id)
    if not result.ok:
        console.print(f"[red]{result.error}[/red]")
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
            console.print(f"    → linkedin drafts follow-up {contact['id']}\n")

    if due_today:
        console.print("\n[bold yellow]📅 Due Today[/bold yellow]\n")
        for contact, follow_date, _ in due_today:
            console.print(f"  ! {contact['name']} ({contact['company']})")
            console.print(f"    Status: {contact['status'].replace('_', ' ')}")
            console.print(f"    → linkedin drafts follow-up {contact['id']}\n")

    if upcoming:
        console.print("\n[bold cyan]📆 Upcoming Follow-ups[/bold cyan]\n")
        for contact, follow_date, days_until in upcoming:
            console.print(f"  - {contact['name']} ({contact['company']}) - [dim]in {-days_until} days[/dim]")

    if stale:
        console.print("\n[bold yellow]📤 Stale Connection Requests (>14 days)[/bold yellow]\n")
        for contact, days_since in stale:
            console.print(f"  ! {contact['name']} ({contact['company']}) - {days_since} days ago")
            console.print("    → Consider sending a follow-up or finding another contact\n")


@contacts.command("remind")
@click.argument("contact_id", type=int)
@click.option("--days", "-d", type=int, default=7, help="Set reminder for N days from now")
@click.option("--date", help="Set specific follow-up date (YYYY-MM-DD)")
def contacts_remind(contact_id, days, date):
    """Set a follow-up reminder for a contact."""
    result = _contact_svc.set_reminder(contact_id, days, date)
    if not result.ok:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    contact = _contact_svc.get_contact(contact_id)
    console.print(f"[green]✓ Reminder set for {contact['name']}: {result.data}[/green]")
