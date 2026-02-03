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
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

console = Console()

# =============================================================================
# Data Storage
# =============================================================================

DATA_DIR = Path.home() / ".linkedin-cli"
PROFILE_FILE = DATA_DIR / "my_profile.json"
CONTACTS_FILE = DATA_DIR / "contacts.json"
COMPANIES_FILE = DATA_DIR / "companies.json"
DRAFTS_FILE = DATA_DIR / "drafts.json"
RESEARCH_FILE = DATA_DIR / "research.json"
BACKUPS_DIR = DATA_DIR / "backups"


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default=None):
    if default is None:
        default = []
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data):
    ensure_dirs()
    path.write_text(json.dumps(data, indent=2, default=str))


# =============================================================================
# AI Draft Generation (Claude API)
# =============================================================================

def generate_with_ai(prompt: str, max_tokens: int = 500) -> str:
    """Generate text using Claude API."""
    try:
        import anthropic

        client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text
    except Exception as e:
        return f"[AI generation failed: {e}. Make sure ANTHROPIC_API_KEY is set.]"


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
    • Track contacts and outreach status
    • Generate personalized drafts with AI
    • Research high-engagement content
    • Plan your LinkedIn strategy

    \b
    Quick Start:
      1. linkedin-cli profile setup     # Add your info
      2. linkedin-cli contacts add      # Add target contacts
      3. linkedin-cli drafts generate   # AI writes your outreach
    """
    ensure_dirs()


# =============================================================================
# Profile Commands - Your Info for Personalization
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

    existing = load_json(PROFILE_FILE, {})

    data = {
        "name": click.prompt("Your name", default=existing.get("name", "")),
        "headline": click.prompt("Your headline/title", default=existing.get("headline", "")),
        "target_role": click.prompt("Target role you're seeking", default=existing.get("target_role", "")),
        "skills": click.prompt("Key skills (comma-separated)", default=existing.get("skills", "")),
        "experience_summary": click.prompt("Brief experience summary", default=existing.get("experience_summary", "")),
        "unique_value": click.prompt("What makes you unique?", default=existing.get("unique_value", "")),
        "industries": click.prompt("Target industries (comma-separated)", default=existing.get("industries", "")),
        "location": click.prompt("Your location", default=existing.get("location", "")),
        "updated_at": datetime.now().isoformat(),
    }

    save_json(PROFILE_FILE, data)
    console.print("\n[green]✓ Profile saved![/green]")


@profile.command("show")
def profile_show():
    """Display your saved profile."""
    data = load_json(PROFILE_FILE, {})

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
# Companies Module - Track Target Companies for Networking
# =============================================================================

COMPANY_PRIORITIES = ["high", "medium", "low"]
COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5000+"]


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
    companies_list = load_json(COMPANIES_FILE)

    company = {
        "id": len(companies_list) + 1,
        "name": name,
        "industry": industry,
        "size": size,
        "linkedin_url": linkedin,
        "website": website,
        "why_target": why,
        "key_people_to_find": [],
        "priority": priority,
        "notes": "",
        "created_at": datetime.now().isoformat(),
    }

    companies_list.append(company)
    save_json(COMPANIES_FILE, companies_list)

    console.print(f"\n[green]✓ Added company: {name} ({industry})[/green]")
    console.print(f"  ID: #{company['id']} | Priority: {priority}")


@companies.command("list")
@click.option("--priority", "-p", type=click.Choice(COMPANY_PRIORITIES + ["all"]), default="all", help="Filter by priority")
@click.option("--industry", "-i", default=None, help="Filter by industry")
def companies_list_cmd(priority, industry):
    """List all target companies."""
    companies_list = load_json(COMPANIES_FILE)

    if not companies_list:
        console.print("[yellow]No companies yet. Run: linkedin-cli companies add[/yellow]")
        return

    # Filter
    filtered = companies_list
    if priority != "all":
        filtered = [c for c in filtered if c.get("priority") == priority]
    if industry:
        filtered = [c for c in filtered if industry.lower() in c.get("industry", "").lower()]

    # Get contact counts per company
    contacts_list = load_json(CONTACTS_FILE)
    contact_counts = {}
    for contact in contacts_list:
        company_id = contact.get("company_id")
        if company_id:
            contact_counts[company_id] = contact_counts.get(company_id, 0) + 1

    table = Table(title=f"Target Companies ({len(filtered)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Industry", style="white")
    table.add_column("Size", style="dim")
    table.add_column("Priority", style="yellow")
    table.add_column("Contacts", style="green")

    priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}

    for c in filtered:
        emoji = priority_emoji.get(c.get("priority", "medium"), "")
        num_contacts = contact_counts.get(c["id"], 0)
        table.add_row(
            str(c["id"]),
            c["name"],
            c.get("industry", ""),
            c.get("size", ""),
            f"{emoji} {c.get('priority', 'medium')}",
            str(num_contacts) if num_contacts else "-"
        )

    console.print(table)


@companies.command("view")
@click.argument("company_id", type=int)
def companies_view(company_id):
    """View detailed info for a company."""
    companies_list = load_json(COMPANIES_FILE)

    company = next((c for c in companies_list if c["id"] == company_id), None)
    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    # Get contacts at this company
    contacts_list = load_json(CONTACTS_FILE)
    company_contacts = [c for c in contacts_list if c.get("company_id") == company_id]

    key_people = company.get("key_people_to_find", [])
    key_people_str = ", ".join(key_people) if key_people else "Not specified"

    console.print(Panel(f"""
[bold]{company['name']}[/bold]
{company.get('industry', 'Industry not set')} | {company.get('size', 'Size not set')} employees

[cyan]LinkedIn:[/cyan] {company.get('linkedin_url') or 'Not set'}
[cyan]Website:[/cyan] {company.get('website') or 'Not set'}
[cyan]Priority:[/cyan] {company.get('priority', 'medium')}
[cyan]Added:[/cyan] {company['created_at'][:10]}

[bold]Why Target:[/bold]
{company.get('why_target', 'Not specified')}

[bold]Key People to Find:[/bold]
{key_people_str}

[bold]Notes:[/bold]
{company.get('notes') or 'No notes'}

[bold]Contacts ({len(company_contacts)}):[/bold]
{chr(10).join([f"  • {c['name']} - {c['title']}" for c in company_contacts]) if company_contacts else '  None yet'}
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
    companies_list = load_json(COMPANIES_FILE)

    company = next((c for c in companies_list if c["id"] == company_id), None)
    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    if priority:
        company["priority"] = priority
    if notes:
        company["notes"] = (company.get("notes", "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}").strip()
    if add_role:
        if "key_people_to_find" not in company:
            company["key_people_to_find"] = []
        company["key_people_to_find"].append(add_role)
    if linkedin:
        company["linkedin_url"] = linkedin
    if website:
        company["website"] = website

    save_json(COMPANIES_FILE, companies_list)
    console.print(f"[green]✓ Updated company #{company_id}[/green]")


@companies.command("delete")
@click.argument("company_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to delete this company?")
def companies_delete(company_id):
    """Delete a company."""
    companies_list = load_json(COMPANIES_FILE)

    company = next((c for c in companies_list if c["id"] == company_id), None)
    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    companies_list = [c for c in companies_list if c["id"] != company_id]
    save_json(COMPANIES_FILE, companies_list)
    console.print(f"[green]✓ Deleted company #{company_id}: {company['name']}[/green]")


@companies.command("contacts")
@click.argument("company_id", type=int)
def companies_contacts(company_id):
    """List contacts at a company."""
    companies_list = load_json(COMPANIES_FILE)
    contacts_list = load_json(CONTACTS_FILE)

    company = next((c for c in companies_list if c["id"] == company_id), None)
    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    company_contacts = [c for c in contacts_list if c.get("company_id") == company_id]

    if not company_contacts:
        console.print(f"[yellow]No contacts at {company['name']} yet.[/yellow]")
        console.print(f"Add one with: linkedin-cli contacts add --company-id {company_id}")
        return

    table = Table(title=f"Contacts at {company['name']} ({len(company_contacts)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")

    status_emoji = {
        "not_contacted": "⚪",
        "connection_sent": "📤",
        "connected": "🤝",
        "messaged": "💬",
        "responded": "✉️",
        "call_scheduled": "📅",
        "rejected": "❌",
        "hired": "🎉",
    }

    for c in company_contacts:
        emoji = status_emoji.get(c["status"], "")
        table.add_row(
            str(c["id"]),
            c["name"],
            c["title"][:30],
            f"{emoji} {c['status'].replace('_', ' ')}"
        )

    console.print(table)


# =============================================================================
# Contacts CRM - Track People to Reach Out To
# =============================================================================

@cli.group()
def contacts():
    """CRM for tracking target contacts and outreach status."""
    pass


CONTACT_STATUSES = [
    "not_contacted",
    "connection_sent",
    "connected",
    "messaged",
    "responded",
    "call_scheduled",
    "rejected",
    "hired",  # 🎉
]


CONTACT_SOURCES = ["linkedin_search", "referral", "event", "inmail", "other"]


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
    contacts_list = load_json(CONTACTS_FILE)

    # Validate company_id if provided
    if company_id:
        companies_list = load_json(COMPANIES_FILE)
        company_obj = next((c for c in companies_list if c["id"] == company_id), None)
        if not company_obj:
            console.print(f"[red]Company #{company_id} not found. Use 'companies list' to see available companies.[/red]")
            return
        # Use company name from the linked company
        company = company_obj["name"]

    # Validate referral_id if provided
    if referral_id:
        referrer = next((c for c in contacts_list if c["id"] == referral_id), None)
        if not referrer:
            console.print(f"[red]Referral contact #{referral_id} not found.[/red]")
            return

    contact = {
        "id": len(contacts_list) + 1,
        "name": name,
        "title": title,
        "company": company,
        "linkedin_url": linkedin,
        "notes": notes,
        "status": "not_contacted",
        "created_at": datetime.now().isoformat(),
        "last_contact": None,
        "follow_up_date": None,
        "company_id": company_id,
        "email": email,
        "source": source,
        "referral_contact_id": referral_id,
        "activities": [],
    }

    contacts_list.append(contact)
    save_json(CONTACTS_FILE, contacts_list)

    console.print(f"\n[green]✓ Added: {name} ({title} at {company})[/green]")
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
    all_contacts = load_json(CONTACTS_FILE)

    if not all_contacts:
        console.print("[yellow]No contacts yet. Run: linkedin-cli contacts add[/yellow]")
        return

    # Filter
    filtered = all_contacts
    if status != "all":
        filtered = [c for c in filtered if c["status"] == status]
    if company:
        filtered = [c for c in filtered if company.lower() in c["company"].lower()]
    if company_id:
        filtered = [c for c in filtered if c.get("company_id") == company_id]
    if source != "all":
        filtered = [c for c in filtered if c.get("source") == source]

    table = Table(title=f"Contacts ({len(filtered)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Company", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Follow Up", style="dim")

    status_emoji = {
        "not_contacted": "⚪",
        "connection_sent": "📤",
        "connected": "🤝",
        "messaged": "💬",
        "responded": "✉️",
        "call_scheduled": "📅",
        "rejected": "❌",
        "hired": "🎉",
    }

    for c in filtered:
        emoji = status_emoji.get(c["status"], "")
        follow_up = c.get("follow_up_date", "")
        if follow_up:
            # Check if overdue
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
            follow_up or "-"
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
    all_contacts = load_json(CONTACTS_FILE)

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    # Ensure activities list exists
    if "activities" not in contact:
        contact["activities"] = []

    if status:
        old_status = contact.get("status", "not_contacted")
        contact["status"] = status
        contact["last_contact"] = datetime.now().isoformat()
        # Log the status change as an activity
        contact["activities"].append({
            "date": datetime.now().isoformat(),
            "type": status,
            "note": f"Status changed from {old_status.replace('_', ' ')}"
        })
    if notes:
        contact["notes"] = (contact.get("notes", "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}").strip()
        contact["activities"].append({
            "date": datetime.now().isoformat(),
            "type": "note_added",
            "note": notes
        })
    if follow_up:
        contact["follow_up_date"] = follow_up
    if email:
        contact["email"] = email

    save_json(CONTACTS_FILE, all_contacts)
    console.print(f"[green]✓ Updated contact #{contact_id}[/green]")


@contacts.command("view")
@click.argument("contact_id", type=int)
def contacts_view(contact_id):
    """View detailed info for a contact."""
    all_contacts = load_json(CONTACTS_FILE)
    companies_list = load_json(COMPANIES_FILE)

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    # Get linked company name if any
    company_link = ""
    if contact.get("company_id"):
        linked_company = next((c for c in companies_list if c["id"] == contact.get("company_id")), None)
        if linked_company:
            company_link = f" (Company #{contact['company_id']})"

    # Get referrer name if any
    referrer_info = ""
    if contact.get("referral_contact_id"):
        referrer = next((c for c in all_contacts if c["id"] == contact.get("referral_contact_id")), None)
        if referrer:
            referrer_info = f"\n[cyan]Referred by:[/cyan] {referrer['name']}"

    email_info = f"\n[cyan]Email:[/cyan] {contact.get('email')}" if contact.get("email") else ""
    source_info = f"\n[cyan]Source:[/cyan] {contact.get('source', 'unknown').replace('_', ' ')}"

    console.print(Panel(f"""
[bold]{contact['name']}[/bold]
{contact['title']} at {contact['company']}{company_link}

[cyan]LinkedIn:[/cyan] {contact['linkedin_url']}{email_info}
[cyan]Status:[/cyan] {contact['status'].replace('_', ' ')}{source_info}{referrer_info}
[cyan]Added:[/cyan] {contact['created_at'][:10]}
[cyan]Last Contact:[/cyan] {contact.get('last_contact', 'Never')[:10] if contact.get('last_contact') else 'Never'}
[cyan]Follow Up:[/cyan] {contact.get('follow_up_date', 'Not set')}

[bold]Notes:[/bold]
{contact.get('notes', 'No notes')}
    """, title=f"Contact #{contact_id}"))


@contacts.command("stats")
def contacts_stats():
    """Show outreach statistics."""
    contacts_list = load_json(CONTACTS_FILE)

    if not contacts_list:
        console.print("[yellow]No contacts yet[/yellow]")
        return

    # Count by status
    status_counts = {}
    for c in contacts_list:
        status = c["status"]
        status_counts[status] = status_counts.get(status, 0) + 1

    console.print("\n[bold]Outreach Pipeline[/bold]\n")

    pipeline = [
        ("not_contacted", "⚪ Not Contacted"),
        ("connection_sent", "📤 Connection Sent"),
        ("connected", "🤝 Connected"),
        ("messaged", "💬 Messaged"),
        ("responded", "✉️ Responded"),
        ("call_scheduled", "📅 Call Scheduled"),
        ("hired", "🎉 Hired!"),
    ]

    total = len(contacts_list)
    for status, label in pipeline:
        count = status_counts.get(status, 0)
        bar = "█" * (count * 20 // total) if total > 0 else ""
        console.print(f"  {label:25} {bar} {count}")

    # Conversion rates
    console.print("\n[bold]Conversion Rates[/bold]")
    if status_counts.get("connection_sent", 0) > 0:
        rate = status_counts.get("connected", 0) / status_counts["connection_sent"] * 100
        console.print(f"  Connection acceptance: {rate:.0f}%")
    if status_counts.get("messaged", 0) > 0:
        rate = status_counts.get("responded", 0) / status_counts["messaged"] * 100
        console.print(f"  Message response rate: {rate:.0f}%")


@contacts.command("activity")
@click.argument("contact_id", type=int)
def contacts_activity(contact_id):
    """View activity log for a contact."""
    all_contacts = load_json(CONTACTS_FILE)

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    activities = contact.get("activities", [])

    console.print(f"\n[bold]Activity Log for {contact['name']}[/bold]\n")

    if not activities:
        console.print("[dim]No activities recorded yet.[/dim]")
        console.print("\nActivities are logged when you update contact status.")
        return

    activity_emoji = {
        "connection_sent": "📤",
        "connected": "🤝",
        "messaged": "💬",
        "responded": "✉️",
        "call_scheduled": "📅",
        "note_added": "📝",
    }

    for activity in reversed(activities):  # Show most recent first
        emoji = activity_emoji.get(activity.get("type", ""), "•")
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
    all_contacts = load_json(CONTACTS_FILE)
    companies_list = load_json(COMPANIES_FILE)

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    company = next((c for c in companies_list if c["id"] == company_id), None)
    if not company:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    contact["company_id"] = company_id
    contact["company"] = company["name"]  # Update company name to match

    save_json(CONTACTS_FILE, all_contacts)
    console.print(f"[green]✓ Linked {contact['name']} to {company['name']}[/green]")


@contacts.command("due")
@click.option("--days", "-d", type=int, default=0, help="Show follow-ups due within N days (0 = overdue only)")
def contacts_due(days):
    """Show contacts with overdue or upcoming follow-ups."""
    all_contacts = load_json(CONTACTS_FILE)

    if not all_contacts:
        console.print("[yellow]No contacts yet[/yellow]")
        return

    today = datetime.now().date()
    threshold = today + __import__("datetime").timedelta(days=days)

    due_contacts = []
    for contact in all_contacts:
        follow_up = contact.get("follow_up_date")
        if not follow_up:
            continue
        try:
            follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
            if follow_up_date <= threshold:
                days_overdue = (today - follow_up_date).days
                due_contacts.append((contact, follow_up_date, days_overdue))
        except (ValueError, AttributeError):
            continue

    # Also check for stale connections (connection sent > 14 days, no response)
    stale_connections = []
    for contact in all_contacts:
        if contact["status"] == "connection_sent":
            last_contact = contact.get("last_contact")
            if last_contact:
                try:
                    last_date = datetime.fromisoformat(last_contact.replace("Z", "+00:00")).date()
                    days_since = (today - last_date).days
                    if days_since >= 14:
                        stale_connections.append((contact, days_since))
                except (ValueError, AttributeError):
                    continue

    if not due_contacts and not stale_connections:
        console.print("[green]✓ No overdue follow-ups![/green]")
        return

    # Split into overdue and upcoming
    overdue = [(c, d, days) for c, d, days in due_contacts if days > 0]
    due_today = [(c, d, days) for c, d, days in due_contacts if days == 0]
    upcoming = [(c, d, days) for c, d, days in due_contacts if days < 0]

    if overdue:
        console.print("\n[bold red]⚠️  Overdue Follow-ups[/bold red]\n")
        overdue.sort(key=lambda x: x[2], reverse=True)  # Most overdue first
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
        upcoming.sort(key=lambda x: x[2], reverse=True)  # Soonest first
        for contact, follow_date, days_until in upcoming:
            console.print(f"  • {contact['name']} ({contact['company']}) - [dim]in {-days_until} days[/dim]")

    if stale_connections:
        console.print("\n[bold yellow]📤 Stale Connection Requests (>14 days)[/bold yellow]\n")
        for contact, days_since in stale_connections:
            console.print(f"  ! {contact['name']} ({contact['company']}) - {days_since} days ago")
            console.print("    → Consider sending a follow-up or finding another contact\n")


@contacts.command("remind")
@click.argument("contact_id", type=int)
@click.option("--days", "-d", type=int, default=7, help="Set reminder for N days from now")
@click.option("--date", help="Set specific follow-up date (YYYY-MM-DD)")
def contacts_remind(contact_id, days, date):
    """Set a follow-up reminder for a contact."""
    all_contacts = load_json(CONTACTS_FILE)

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    if date:
        follow_up_date = date
    else:
        follow_up_date = (datetime.now() + __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")

    contact["follow_up_date"] = follow_up_date

    save_json(CONTACTS_FILE, all_contacts)
    console.print(f"[green]✓ Reminder set for {contact['name']}: {follow_up_date}[/green]")


# =============================================================================
# Drafts - AI-Generated Personalized Outreach
# =============================================================================

@cli.group()
def drafts():
    """Generate and manage AI-powered outreach drafts."""
    pass


@drafts.command("connection")
@click.argument("contact_id", type=int)
def drafts_connection(contact_id):
    """Generate a personalized connection request for a contact."""
    my_profile = load_json(PROFILE_FILE, {})
    contacts_list = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    contact = next((c for c in contacts_list if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating connection request for {contact['name']}...[/bold]\n")

    prompt = f"""Write a LinkedIn connection request message (max 300 characters) from me to this person.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Current Role: {my_profile.get('headline', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Key Skills: {my_profile.get('skills', 'N/A')}
- What Makes Me Unique: {my_profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Why I want to connect: {contact.get('notes', 'Interested in their work')}

Write a warm, personalized connection request that:
1. Shows I've looked at their profile
2. Mentions something specific about them or their company
3. Briefly explains why connecting would be mutually valuable
4. Is under 300 characters (LinkedIn limit)
5. Sounds natural, not salesy

Just write the message, no explanations."""

    draft = generate_with_ai(prompt, max_tokens=200)

    console.print(Panel(draft, title="Connection Request Draft", border_style="green"))
    console.print(f"\n[dim]Characters: {len(draft)}/300[/dim]")

    # Save draft
    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": contact_id,
            "type": "connection",
            "content": draft,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("message")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="Additional context for the message")
def drafts_message(contact_id, context):
    """Generate a personalized follow-up message."""
    my_profile = load_json(PROFILE_FILE, {})
    contacts_list = load_json(CONTACTS_FILE)

    contact = next((c for c in contacts_list if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating message for {contact['name']}...[/bold]\n")

    prompt = f"""Write a LinkedIn message from me to this person we're already connected with.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Experience: {my_profile.get('experience_summary', 'N/A')}
- Key Skills: {my_profile.get('skills', 'N/A')}
- Unique Value: {my_profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our history: {contact.get('notes', 'Just connected')}
- Current status: {contact['status']}

ADDITIONAL CONTEXT: {context if context else 'None provided'}

Write a professional but warm message that:
1. References our connection or something about them
2. Clearly states what I'm looking for (job opportunity, advice, referral)
3. Makes it easy for them to help (specific ask)
4. Is respectful of their time
5. Ends with a clear next step

Keep it under 500 words. Sound human, not like a template."""

    draft = generate_with_ai(prompt, max_tokens=400)

    console.print(Panel(draft, title="Message Draft", border_style="blue"))

    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": contact_id,
            "type": "message",
            "content": draft,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("intro-request")
@click.argument("contact_id", type=int)
@click.option("--to", "target_id", type=int, required=True, help="Contact ID to be introduced to")
def drafts_intro_request(contact_id, target_id):
    """Generate a message asking for an introduction to another contact."""
    my_profile = load_json(PROFILE_FILE, {})
    all_contacts = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    target = next((c for c in all_contacts if c["id"] == target_id), None)
    if not target:
        console.print(f"[red]Target contact #{target_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating intro request to {contact['name']} for intro to {target['name']}...[/bold]\n")

    prompt = f"""Write a LinkedIn message asking someone to introduce me to another person.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Key Skills: {my_profile.get('skills', 'N/A')}

ASKING (the person I'm messaging):
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our relationship: {contact.get('notes', 'We are connected on LinkedIn')}

BEING INTRODUCED TO:
- Name: {target['name']}
- Title: {target['title']}
- Company: {target['company']}
- Why I want to meet them: {target.get('notes', 'Interested in their work')}

Write a message that:
1. Acknowledges my relationship with the person I'm asking
2. Explains who I want to be introduced to and why
3. Makes it easy for them to say yes (provides context they can forward)
4. Offers to provide more info or a brief intro paragraph
5. Is respectful and not pushy
6. Under 300 words

Just write the message, no explanations."""

    draft = generate_with_ai(prompt, max_tokens=400)

    console.print(Panel(draft, title="Introduction Request Draft", border_style="magenta"))

    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": contact_id,
            "target_contact_id": target_id,
            "type": "intro_request",
            "content": draft,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("thank-you")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="What to thank them for (e.g., 'the call yesterday')")
def drafts_thank_you(contact_id, context):
    """Generate a thank you message after a call or meeting."""
    my_profile = load_json(PROFILE_FILE, {})
    all_contacts = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating thank you note for {contact['name']}...[/bold]\n")

    prompt = f"""Write a LinkedIn thank you message after a networking call or meeting.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our history: {contact.get('notes', 'Had a call')}

CONTEXT: {context if context else 'A networking call to discuss career opportunities'}

Write a thank you message that:
1. Thanks them specifically for their time
2. References something specific from our conversation (make a reasonable assumption)
3. Mentions a key takeaway or insight I gained
4. Proposes a way to stay in touch or follow up
5. Offers to help them with something if possible
6. Is warm but professional
7. Under 150 words

Just write the message, no explanations."""

    draft = generate_with_ai(prompt, max_tokens=250)

    console.print(Panel(draft, title="Thank You Note Draft", border_style="green"))

    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": contact_id,
            "type": "thank_you",
            "content": draft,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("follow-up")
@click.argument("contact_id", type=int)
@click.option("--attempt", "-a", type=int, default=1, help="Which follow-up attempt (1, 2, or 3)")
def drafts_follow_up(contact_id, attempt):
    """Generate a follow-up message after no response."""
    my_profile = load_json(PROFILE_FILE, {})
    all_contacts = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    contact = next((c for c in all_contacts if c["id"] == contact_id), None)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating follow-up #{attempt} for {contact['name']}...[/bold]\n")

    attempt_guidance = {
        1: "This is a gentle first follow-up. Be casual and add value if possible.",
        2: "This is a second follow-up. Be shorter and offer an easy out.",
        3: "This is a final follow-up. Be very brief, suggest reconnecting in the future, and close the loop gracefully."
    }

    prompt = f"""Write a LinkedIn follow-up message after not hearing back.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Our status: {contact['status'].replace('_', ' ')}
- Previous interaction: {contact.get('notes', 'Reached out previously')}

FOLLOW-UP CONTEXT:
{attempt_guidance.get(attempt, attempt_guidance[1])}

Write a follow-up message that:
1. Acknowledges they're busy without being passive-aggressive
2. Adds new value or a fresh angle (not just "checking in")
3. Makes it easy to respond with a simple yes/no
4. Is under {150 if attempt == 1 else 100 if attempt == 2 else 50} words
5. Sounds confident but not desperate

Just write the message, no explanations."""

    draft = generate_with_ai(prompt, max_tokens=200)

    console.print(Panel(draft, title=f"Follow-up #{attempt} Draft", border_style="yellow"))

    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": contact_id,
            "type": f"follow_up_{attempt}",
            "content": draft,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("batch-connections")
@click.option("--limit", "-l", type=int, default=5, help="Max number of drafts to generate")
@click.option("--save-all", is_flag=True, help="Save all drafts without prompting")
def drafts_batch_connections(limit, save_all):
    """Generate connection requests for all not_contacted contacts."""
    my_profile = load_json(PROFILE_FILE, {})
    all_contacts = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    # Find not_contacted contacts
    not_contacted = [c for c in all_contacts if c["status"] == "not_contacted"]

    if not not_contacted:
        console.print("[green]✓ All contacts have been contacted![/green]")
        return

    to_generate = not_contacted[:limit]
    console.print(f"\n[bold]Generating connection requests for {len(to_generate)} contacts...[/bold]\n")

    drafts_list = load_json(DRAFTS_FILE)
    generated = 0

    for contact in to_generate:
        console.print(f"[dim]Generating for {contact['name']}...[/dim]")

        prompt = f"""Write a LinkedIn connection request message (max 300 characters) from me to this person.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Current Role: {my_profile.get('headline', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Key Skills: {my_profile.get('skills', 'N/A')}

THEIR PROFILE:
- Name: {contact['name']}
- Title: {contact['title']}
- Company: {contact['company']}
- Why I want to connect: {contact.get('notes', 'Interested in their work')}

Write a warm, personalized connection request under 300 characters that shows I've looked at their profile.
Just write the message, no explanations."""

        draft = generate_with_ai(prompt, max_tokens=200)

        console.print(f"\n[cyan]{contact['name']}[/cyan] ({contact['title']} at {contact['company']}):")
        console.print(Panel(draft, border_style="green"))
        console.print(f"[dim]Characters: {len(draft)}/300[/dim]\n")

        if save_all or click.confirm("Save this draft?"):
            drafts_list.append({
                "id": len(drafts_list) + 1,
                "contact_id": contact["id"],
                "type": "connection",
                "content": draft,
                "created_at": datetime.now().isoformat(),
            })
            generated += 1

    save_json(DRAFTS_FILE, drafts_list)
    console.print(f"\n[green]✓ Generated and saved {generated} drafts![/green]")


@drafts.command("list")
def drafts_list_cmd():
    """List all saved drafts."""
    drafts_list = load_json(DRAFTS_FILE)
    contacts_list = load_json(CONTACTS_FILE)

    if not drafts_list:
        console.print("[yellow]No drafts yet. Generate one with: linkedin-cli drafts connection <id>[/yellow]")
        return

    table = Table(title="Saved Drafts")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("For", style="green")
    table.add_column("Preview", style="white")
    table.add_column("Created", style="dim")

    for d in drafts_list:
        contact = next((c for c in contacts_list if c["id"] == d["contact_id"]), {})
        preview = d["content"][:50] + "..." if len(d["content"]) > 50 else d["content"]
        table.add_row(
            str(d["id"]),
            d["type"],
            contact.get("name", "Unknown"),
            preview,
            d["created_at"][:10]
        )

    console.print(table)


@drafts.command("view")
@click.argument("draft_id", type=int)
def drafts_view(draft_id):
    """View a saved draft."""
    drafts_list = load_json(DRAFTS_FILE)

    draft = next((d for d in drafts_list if d["id"] == draft_id), None)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found[/red]")
        return

    console.print(Panel(draft["content"], title=f"Draft #{draft_id} ({draft['type']})", border_style="blue"))


# =============================================================================
# Discovery - AI-Powered Networking Suggestions
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
    my_profile = load_json(PROFILE_FILE, {})
    companies_list = load_json(COMPANIES_FILE)
    all_contacts = load_json(CONTACTS_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    if not company and not role:
        console.print("[yellow]Specify --company or --role to get suggestions[/yellow]")
        console.print("Examples:")
        console.print("  linkedin-cli discover contacts --company 'LangChain'")
        console.print("  linkedin-cli discover contacts --role 'Engineering Manager'")
        return

    # Get existing contacts for context
    existing_titles = list(set([c["title"] for c in all_contacts]))[:10]

    if company:
        # Find if we have this company tracked
        tracked_company = next((c for c in companies_list if company.lower() in c["name"].lower()), None)
        company_context = ""
        if tracked_company:
            company_context = f"""
COMPANY WE'RE TRACKING:
- Name: {tracked_company['name']}
- Industry: {tracked_company.get('industry', 'Unknown')}
- Size: {tracked_company.get('size', 'Unknown')}
- Why targeting: {tracked_company.get('why_target', 'General interest')}
- Roles to find: {', '.join(tracked_company.get('key_people_to_find', [])) or 'Not specified'}
"""

        console.print(f"\n[bold]Finding who to connect with at {company}...[/bold]\n")

        prompt = f"""I'm job hunting and want to network at {company}. Suggest specific types of people I should find and connect with on LinkedIn.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Skills: {my_profile.get('skills', 'N/A')}
- Industries: {my_profile.get('industries', 'N/A')}
{company_context}
EXISTING CONTACTS I'VE FOUND (for reference):
{', '.join(existing_titles) if existing_titles else 'None yet'}

Provide a prioritized list of:
1. **Job titles to search for** (specific LinkedIn search terms)
2. **Why each is valuable** (what they can offer: referral, advice, intel)
3. **How to find them** (LinkedIn search tips, filters to use)
4. **What to look for in profiles** (signals they'd be receptive)
5. **Connection angle** (what to mention when reaching out)

Format as a clear, actionable list. Focus on 4-6 specific titles/roles."""

    else:  # role specified
        console.print(f"\n[bold]Finding where to find {role} roles...[/bold]\n")

        prompt = f"""I'm looking to connect with people in {role} positions for my job search. Suggest how to find and approach them.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Skills: {my_profile.get('skills', 'N/A')}
- Industries: {my_profile.get('industries', 'N/A')}

COMPANIES I'M TRACKING:
{', '.join([c['name'] for c in companies_list]) if companies_list else 'None yet'}

Provide:
1. **LinkedIn search strategy** - exact search terms and filters
2. **Profile signals** - what to look for that suggests they'd be receptive
3. **Connection angles** - different ways to approach based on their background
4. **Companies where this role has influence** - types of orgs where this role matters
5. **Related titles** - similar roles I should also search for
6. **Red flags** - profiles to avoid or approaches that won't work

Be specific and actionable."""

    suggestions = generate_with_ai(prompt, max_tokens=800)

    console.print(Panel(suggestions, title="Contact Discovery Suggestions", border_style="cyan"))


@discover.command("companies")
def discover_companies():
    """Get AI suggestions for companies to target."""
    my_profile = load_json(PROFILE_FILE, {})
    companies_list = load_json(COMPANIES_FILE)

    if not my_profile:
        console.print("[yellow]Set up your profile first: linkedin-cli profile setup[/yellow]")
        return

    console.print("\n[bold]Discovering companies to target...[/bold]\n")

    existing_companies = [c["name"] for c in companies_list]

    prompt = f"""Suggest companies I should target for networking based on my profile.

MY PROFILE:
- Name: {my_profile.get('name', 'N/A')}
- Target Role: {my_profile.get('target_role', 'N/A')}
- Skills: {my_profile.get('skills', 'N/A')}
- Experience: {my_profile.get('experience_summary', 'N/A')}
- Target Industries: {my_profile.get('industries', 'N/A')}
- Location: {my_profile.get('location', 'N/A')}

COMPANIES I'M ALREADY TRACKING:
{', '.join(existing_companies) if existing_companies else 'None yet'}

Suggest 8-10 companies I should consider, including:

1. **Company Name** and brief description
2. **Why it's a good fit** for my background
3. **What roles they likely have** matching my target
4. **How to research them** (what to look for)
5. **Networking angle** (why someone there would talk to me)

Include a mix of:
- Well-known companies in my target space
- Growing startups that might be hiring
- Companies using technologies I know
- Companies where my background would be valued

Don't just suggest FAANG - be specific to my skills and target role."""

    suggestions = generate_with_ai(prompt, max_tokens=1000)

    console.print(Panel(suggestions, title="Company Discovery Suggestions", border_style="green"))

    if click.confirm("\nWould you like to add any of these companies?"):
        console.print("[dim]Use 'linkedin-cli companies add' to add companies[/dim]")


# =============================================================================
# Research - Content Strategy & Post Ideas
# =============================================================================

@cli.group()
def research():
    """Research content strategies and post ideas."""
    pass


@research.command("engagement")
def research_engagement():
    """Show high-engagement content strategies for LinkedIn."""
    content = """
# LinkedIn Engagement Strategies 📈

## Post Formats That Work

### 1. Personal Stories (Highest Engagement)
- Share failures and lessons learned
- Career transition stories
- "What I learned from X years doing Y"
- Vulnerability + insight = engagement

### 2. Contrarian Takes
- "Unpopular opinion: [hot take on industry topic]"
- Challenge conventional wisdom
- Back up with experience/data

### 3. Listicles
- "5 things I wish I knew about X"
- "10 tools every [role] should use"
- Easy to read and share

### 4. Behind-the-Scenes
- Day in the life
- Project breakdowns
- Company culture insights

### 5. Carousels/Documents
- Step-by-step guides
- Visual frameworks
- Cheat sheets

## Optimal Posting

| Day | Best Time | Why |
|-----|-----------|-----|
| Tuesday | 10am-12pm | Peak professional browsing |
| Wednesday | 10am-12pm | Midweek engagement |
| Thursday | 10am, 2pm | Pre-weekend planning |

**Avoid**: Weekends, late evenings, early mornings

## Formatting Tips

- **First line is everything** (hook them!)
- Use line breaks liberally
- Emojis: 1-3 max, use strategically
- Hashtags: 3-5, mix popular + niche
- End with a question to drive comments

## Engagement Tactics

1. Reply to EVERY comment within 1 hour
2. Comment on others' posts before posting yours
3. Tag relevant people (sparingly)
4. Post consistently (2-3x per week minimum)
    """

    console.print(Markdown(content))


@research.command("ideas")
@click.option("--topic", "-t", default=None, help="Topic to generate ideas for")
def research_ideas(topic):
    """Generate post ideas based on your profile."""
    my_profile = load_json(PROFILE_FILE, {})

    if topic:
        focus = topic
    elif my_profile:
        focus = f"{my_profile.get('target_role', '')} in {my_profile.get('industries', 'tech')}"
    else:
        focus = "professional growth"

    console.print(f"\n[bold]Generating post ideas for: {focus}...[/bold]\n")

    prompt = f"""Generate 10 LinkedIn post ideas for someone looking for a job in: {focus}

Their background: {my_profile.get('experience_summary', 'Tech professional')}
Their skills: {my_profile.get('skills', 'Various technical skills')}

For each idea, provide:
1. A catchy hook (first line of the post)
2. What the post is about (1 sentence)
3. Why it would get engagement

Focus on posts that:
- Showcase expertise without being salesy
- Tell stories or share insights
- Could go viral or get lots of engagement
- Position them as a thought leader

Format as a numbered list."""

    ideas = generate_with_ai(prompt, max_tokens=800)

    console.print(Panel(ideas, title="Post Ideas", border_style="green"))

    if click.confirm("\nSave these ideas?"):
        research_data = load_json(RESEARCH_FILE, {"ideas": []})
        research_data["ideas"].append({
            "topic": focus,
            "ideas": ideas,
            "created_at": datetime.now().isoformat(),
        })
        save_json(RESEARCH_FILE, research_data)
        console.print("[green]✓ Ideas saved![/green]")


@research.command("draft-post")
@click.argument("topic")
@click.option("--style", "-s", type=click.Choice(["story", "listicle", "contrarian", "how-to"]), default="story")
def research_draft_post(topic, style):
    """Generate a full post draft."""
    my_profile = load_json(PROFILE_FILE, {})

    console.print(f"\n[bold]Generating {style} post about: {topic}...[/bold]\n")

    style_instructions = {
        "story": "Write as a personal story with a lesson. Start with a hook, build tension, reveal insight.",
        "listicle": "Write as a numbered list (5-7 items). Each item should be actionable and valuable.",
        "contrarian": "Take an unpopular stance on the topic. Be bold but back it up with reasoning.",
        "how-to": "Write as a practical guide. Step-by-step, actionable, clear.",
    }

    prompt = f"""Write a LinkedIn post about: {topic}

Style: {style_instructions[style]}

Author background:
- Role: {my_profile.get('headline', 'Professional')}
- Experience: {my_profile.get('experience_summary', 'Years of experience')}
- Target audience: People in {my_profile.get('industries', 'tech')}

Requirements:
- Start with a compelling hook (first 2 lines are crucial)
- Use short paragraphs and line breaks
- Include 1-2 relevant emojis (not too many)
- End with a question or call to action
- Keep it 150-250 words
- Sound authentic, not like ChatGPT
- Add 3-5 relevant hashtags at the end

Write the post now:"""

    draft = generate_with_ai(prompt, max_tokens=500)

    console.print(Panel(draft, title=f"Post Draft ({style})", border_style="green"))

    if click.confirm("\nSave this draft?"):
        drafts_list = load_json(DRAFTS_FILE)
        drafts_list.append({
            "id": len(drafts_list) + 1,
            "contact_id": None,
            "type": f"post_{style}",
            "content": draft,
            "topic": topic,
            "created_at": datetime.now().isoformat(),
        })
        save_json(DRAFTS_FILE, drafts_list)
        console.print("[green]✓ Post draft saved![/green]")


@research.command("hashtags")
@click.argument("topic")
def research_hashtags(topic):
    """Get hashtag recommendations for a topic."""
    console.print(f"\n[bold]Finding hashtags for: {topic}...[/bold]\n")

    prompt = f"""Suggest the best LinkedIn hashtags for a post about: {topic}

Provide:
1. 5 high-volume hashtags (popular, broad reach)
2. 5 niche hashtags (smaller but engaged audience)
3. 3 trending hashtags (if relevant)

For each, briefly explain why it's good.

Format as a clean list."""

    hashtags = generate_with_ai(prompt, max_tokens=300)

    console.print(Panel(hashtags, title="Hashtag Recommendations", border_style="cyan"))


# =============================================================================
# Data Management - Import/Export/Backup
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
    import csv

    if data_type == "contacts" or data_type == "all":
        contacts = load_json(CONTACTS_FILE)
        if fmt == "csv":
            output_file = output or "contacts_export.csv"
            if contacts:
                fieldnames = ["id", "name", "title", "company", "linkedin_url", "email", "status",
                              "source", "notes", "follow_up_date", "created_at", "company_id"]
                with open(output_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(contacts)
                console.print(f"[green]✓ Exported {len(contacts)} contacts to {output_file}[/green]")
            else:
                console.print("[yellow]No contacts to export[/yellow]")
        else:
            output_file = output or "contacts_export.json"
            save_json(Path(output_file), contacts)
            console.print(f"[green]✓ Exported {len(contacts)} contacts to {output_file}[/green]")

    if data_type == "companies" or data_type == "all":
        companies = load_json(COMPANIES_FILE)
        if fmt == "csv":
            output_file = output or "companies_export.csv" if data_type == "companies" else "companies_export.csv"
            if data_type == "all" and output:
                output_file = output.replace("contacts", "companies").replace(".csv", "_companies.csv")
            if companies:
                fieldnames = ["id", "name", "industry", "size", "linkedin_url", "website",
                              "why_target", "priority", "notes", "created_at"]
                with open(output_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                    writer.writeheader()
                    writer.writerows(companies)
                console.print(f"[green]✓ Exported {len(companies)} companies to {output_file}[/green]")
            else:
                console.print("[yellow]No companies to export[/yellow]")
        else:
            output_file = output or "companies_export.json"
            if data_type == "all" and output:
                output_file = output.replace("contacts", "companies").replace(".json", "_companies.json")
            save_json(Path(output_file), companies)
            console.print(f"[green]✓ Exported {len(companies)} companies to {output_file}[/green]")


@data.command("import")
@click.argument("data_type", type=click.Choice(["contacts", "companies"]))
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing data instead of replacing")
def data_import(data_type, file_path, merge):
    """Import contacts or companies from a file."""
    import csv

    file_path = Path(file_path)

    if data_type == "contacts":
        target_file = CONTACTS_FILE
        existing = load_json(CONTACTS_FILE) if merge else []

        if file_path.suffix == ".csv":
            with open(file_path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    # Convert string IDs to int
                    if "id" in row:
                        row["id"] = int(row["id"]) if row["id"] else len(existing) + len(imported) + 1
                    if "company_id" in row and row["company_id"]:
                        row["company_id"] = int(row["company_id"])
                    else:
                        row["company_id"] = None
                    # Set defaults for missing fields
                    row.setdefault("status", "not_contacted")
                    row.setdefault("activities", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(file_path.read_text())

        if merge:
            # Assign new IDs to imported contacts
            max_id = max([c["id"] for c in existing], default=0)
            for contact in imported:
                max_id += 1
                contact["id"] = max_id
            final = existing + imported
        else:
            final = imported

        save_json(target_file, final)
        console.print(f"[green]✓ Imported {len(imported)} contacts[/green]")

    else:  # companies
        target_file = COMPANIES_FILE
        existing = load_json(COMPANIES_FILE) if merge else []

        if file_path.suffix == ".csv":
            with open(file_path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    if "id" in row:
                        row["id"] = int(row["id"]) if row["id"] else len(existing) + len(imported) + 1
                    row.setdefault("key_people_to_find", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(file_path.read_text())

        if merge:
            max_id = max([c["id"] for c in existing], default=0)
            for company in imported:
                max_id += 1
                company["id"] = max_id
            final = existing + imported
        else:
            final = imported

        save_json(target_file, final)
        console.print(f"[green]✓ Imported {len(imported)} companies[/green]")


@data.command("backup")
@click.option("--output", "-o", default=None, help="Output backup file path")
def data_backup(output):
    """Create a backup of all data files."""
    import zipfile

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = output or str(BACKUPS_DIR / f"linkedin_cli_backup_{timestamp}.zip")

    files_to_backup = [
        PROFILE_FILE,
        CONTACTS_FILE,
        COMPANIES_FILE,
        DRAFTS_FILE,
        RESEARCH_FILE,
    ]

    backed_up = 0
    with zipfile.ZipFile(backup_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in files_to_backup:
            if file_path.exists():
                zipf.write(file_path, file_path.name)
                backed_up += 1

    console.print(f"[green]✓ Backup created: {backup_name}[/green]")
    console.print(f"  Backed up {backed_up} files")


@data.command("restore")
@click.argument("backup_file", type=click.Path(exists=True))
@click.confirmation_option(prompt="This will overwrite your current data. Continue?")
def data_restore(backup_file):
    """Restore data from a backup file."""
    import zipfile

    backup_path = Path(backup_file)

    if not zipfile.is_zipfile(backup_path):
        console.print("[red]Not a valid backup file (must be a zip file)[/red]")
        return

    ensure_dirs()

    restored = 0
    with zipfile.ZipFile(backup_path, "r") as zipf:
        for filename in zipf.namelist():
            zipf.extract(filename, DATA_DIR)
            restored += 1

    console.print(f"[green]✓ Restored {restored} files from backup[/green]")


@data.command("backups")
def data_backups():
    """List available backups."""
    if not BACKUPS_DIR.exists():
        console.print("[yellow]No backups directory found[/yellow]")
        return

    backups = list(BACKUPS_DIR.glob("*.zip"))
    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        console.print("Create one with: linkedin-cli data backup")
        return

    backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    table = Table(title="Available Backups")
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Created", style="green")

    for backup in backups:
        stat = backup.stat()
        size_kb = stat.st_size / 1024
        created = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        table.add_row(backup.name, f"{size_kb:.1f} KB", created)

    console.print(table)
    console.print("\nRestore with: linkedin-cli data restore <backup-file>")


# =============================================================================
# Dashboard
# =============================================================================

@cli.command()
def dashboard():
    """Show overview of your job hunt progress."""
    my_profile = load_json(PROFILE_FILE, {})
    all_contacts = load_json(CONTACTS_FILE)
    companies_list = load_json(COMPANIES_FILE)
    drafts_list = load_json(DRAFTS_FILE)

    console.print("\n[bold]📊 Job Hunt Dashboard[/bold]\n")

    # Profile status
    if my_profile:
        console.print(f"[bold]PROFILE:[/bold] {my_profile.get('name', 'Set up')} → {my_profile.get('target_role', 'Role TBD')}")
    else:
        console.print("[yellow]⚠[/yellow] Profile: Not set up (run: linkedin-cli profile setup)")

    # Contacts Pipeline with visual bars
    console.print("\n[bold]CONTACTS PIPELINE[/bold]")
    if all_contacts:
        status_counts = {}
        for c in all_contacts:
            status = c["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        total = len(all_contacts)
        pipeline = [
            ("not_contacted", "⚪ Not Contacted"),
            ("connection_sent", "📤 Pending"),
            ("connected", "🤝 Connected"),
            ("messaged", "💬 Messaged"),
            ("responded", "✉️ Responded"),
            ("call_scheduled", "📅 Calls"),
        ]

        max_label_len = max(len(label) for _, label in pipeline)
        for status, label in pipeline:
            count = status_counts.get(status, 0)
            bar_width = int(count * 20 / total) if total > 0 else 0
            bar = "█" * bar_width
            console.print(f"  {label:{max_label_len}} {bar:20} {count}")
    else:
        console.print("  [dim]No contacts yet[/dim]")

    # Overdue follow-ups
    today = datetime.now().date()
    overdue = []
    stale_connections = []

    for contact in all_contacts:
        # Check follow-up dates
        follow_up = contact.get("follow_up_date")
        if follow_up:
            try:
                follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
                if follow_up_date < today:
                    days_overdue = (today - follow_up_date).days
                    overdue.append((contact, days_overdue))
            except (ValueError, AttributeError):
                pass

        # Check stale connection requests
        if contact["status"] == "connection_sent":
            last_contact = contact.get("last_contact")
            if last_contact:
                try:
                    last_date = datetime.fromisoformat(last_contact.replace("Z", "+00:00")).date()
                    days_since = (today - last_date).days
                    if days_since >= 14:
                        stale_connections.append((contact, days_since))
                except (ValueError, AttributeError):
                    pass

    if overdue or stale_connections:
        console.print(f"\n[bold red]⚠️  OVERDUE FOLLOW-UPS ({len(overdue) + len(stale_connections)})[/bold red]")
        overdue.sort(key=lambda x: x[1], reverse=True)
        for contact, days in overdue[:3]:
            console.print(f"  ! {contact['name']} - Follow up was {days} days ago")
        for contact, days in stale_connections[:3]:
            console.print(f"  ! {contact['name']} - Connection sent {days} days ago, no response")
        if len(overdue) + len(stale_connections) > 6:
            console.print(f"  [dim]... and {len(overdue) + len(stale_connections) - 6} more[/dim]")

    # Target companies
    if companies_list:
        console.print(f"\n[bold]TARGET COMPANIES ({len(companies_list)})[/bold]")
        # Show companies with contact counts
        company_contacts = {}
        for contact in all_contacts:
            cid = contact.get("company_id")
            if cid:
                company_contacts[cid] = company_contacts.get(cid, 0) + 1

        high_priority = [c for c in companies_list if c.get("priority") == "high"]
        display_companies = high_priority[:3] if high_priority else companies_list[:3]

        for company in display_companies:
            contact_count = company_contacts.get(company["id"], 0)
            priority_marker = "🔴" if company.get("priority") == "high" else "🟡" if company.get("priority") == "medium" else "🟢"
            console.print(f"  {priority_marker} {company['name']} ({contact_count} contacts)")

    # Drafts summary
    console.print("\n[bold]DRAFTS[/bold]")
    console.print(f"  Total saved: {len(drafts_list)}")
    draft_types = {}
    for d in drafts_list:
        dtype = d.get("type", "unknown")
        draft_types[dtype] = draft_types.get(dtype, 0) + 1
    if draft_types:
        type_summary = ", ".join([f"{v} {k.replace('_', ' ')}" for k, v in list(draft_types.items())[:3]])
        console.print(f"  [dim]{type_summary}[/dim]")

    # Suggested actions
    console.print("\n[bold]SUGGESTED ACTIONS[/bold]")
    suggestions = []

    if overdue:
        suggestions.append(f"→ Follow up with {overdue[0][0]['name']}")

    not_contacted = [c for c in all_contacts if c["status"] == "not_contacted"]
    if not_contacted:
        suggestions.append(f"→ {len(not_contacted)} contacts to reach out to")

    connected = [c for c in all_contacts if c["status"] == "connected"]
    if connected:
        suggestions.append(f"→ {len(connected)} connections to message")

    # Check for companies needing more contacts
    for company in companies_list[:3]:
        contact_count = company_contacts.get(company["id"], 0) if companies_list else 0
        if contact_count == 0:
            suggestions.append(f"→ Find contacts at {company['name']}")
            break

    if not my_profile:
        suggestions.append("→ Set up your profile for personalized drafts")

    if not suggestions:
        suggestions.append("→ Add more contacts or companies to track")

    for suggestion in suggestions[:5]:
        console.print(f"  {suggestion}")


if __name__ == "__main__":
    cli()
