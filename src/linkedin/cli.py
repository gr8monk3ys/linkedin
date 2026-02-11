#!/usr/bin/env python3
"""
LinkedIn Job Hunt Assistant - CRM + AI Drafts + Content Research

A local tool to accelerate your job search:
- Track contacts and outreach status
- Generate personalized connection/message drafts with AI
- Research high-engagement content strategies
- Manage your LinkedIn presence strategically
"""

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

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
from linkedin.data.json_store import (
    JsonCompanyRepo,
    JsonContactRepo,
    JsonDraftRepo,
    JsonProfileRepo,
    JsonResearchRepo,
    ensure_dirs,
)
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

# Repositories
_contact_repo = JsonContactRepo()
_company_repo = JsonCompanyRepo()
_profile_repo = JsonProfileRepo()
_draft_repo = JsonDraftRepo()
_research_repo = JsonResearchRepo()

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


# =============================================================================
# CLI Setup
# =============================================================================

@click.group()
@click.version_option(version="3.0.0", prog_name="linkedin-cli")
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
      3. linkedin-cli drafts generate   # AI writes your outreach
    """
    ensure_dirs()


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
    console.print(f"[green]✓ Updated contact #{contact_id}[/green]")


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
    focus, ideas = _research_svc.generate_ideas(topic)

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

    draft = _research_svc.generate_post_draft(topic, style)
    console.print(Panel(draft, title=f"Post Draft ({style})", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _research_svc.save_post_draft(topic, style, draft)
        console.print("[green]✓ Post draft saved![/green]")


@research.command("hashtags")
@click.argument("topic")
def research_hashtags(topic):
    """Get hashtag recommendations for a topic."""
    console.print(f"\n[bold]Finding hashtags for: {topic}...[/bold]\n")

    hashtags = _research_svc.generate_hashtags(topic)
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
def data_backup(output):
    """Create a backup of all data files."""
    backup_name, backed_up = _data_svc.create_backup(output)
    console.print(f"[green]✓ Backup created: {backup_name}[/green]")
    console.print(f"  Backed up {backed_up} files")


@data.command("restore")
@click.argument("backup_file", type=click.Path(exists=True))
@click.confirmation_option(prompt="This will overwrite your current data. Continue?")
def data_restore(backup_file):
    """Restore data from a backup file."""
    restored = _data_svc.restore_backup(backup_file)
    if restored is None:
        console.print("[red]Not a valid backup file (must be a zip file)[/red]")
        return
    console.print(f"[green]✓ Restored {restored} files from backup[/green]")


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
        console.print("[yellow]No templates saved yet. Use 'linkedin templates save' to create one.[/yellow]")
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


if __name__ == "__main__":
    cli()
