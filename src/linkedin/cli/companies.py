"""Companies commands."""

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli import _company_svc, cli, console
from linkedin.constants import (
    COMPANY_PRIORITIES,
    COMPANY_SIZES,
    PRIORITY_EMOJI,
    STATUS_EMOJI,
    CompanyPriority,
    ContactStatus,
)


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
        console.print("[yellow]No companies yet. Run: linkedin companies add[/yellow]")
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
    if not result.ok:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    company = result.data
    company_contacts = company.get("contacts", [])
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
{chr(10).join([f"  - {c.get('name', '')} - {c.get('title', 'Title not set')}" for c in company_contacts]) if company_contacts else '  None yet'}
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
    if not result.ok:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Updated company #{company_id}[/green]")


@companies.command("delete")
@click.argument("company_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to delete this company?")
def companies_delete(company_id):
    """Delete a company."""
    result = _company_svc.delete_company(company_id)
    if not result.ok:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return
    console.print(f"[green]✓ Deleted company #{company_id}: {result.data['name']}[/green]")


@companies.command("contacts")
@click.argument("company_id", type=int)
def companies_contacts(company_id):
    """List contacts at a company."""
    result = _company_svc.get_company_contacts(company_id)

    if not result.ok:
        console.print(f"[red]Company #{company_id} not found[/red]")
        return

    company = result.data["company"]
    company_contacts = result.data["contacts"]

    if not company_contacts:
        console.print(f"[yellow]No contacts at {company['name']} yet.[/yellow]")
        console.print(f"Add one with: linkedin contacts add --company-id {company_id}")
        return

    table = Table(title=f"Contacts at {company['name']} ({len(company_contacts)})")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")

    for c in company_contacts:
        status_value = c.get("status", "not_contacted")
        emoji = STATUS_EMOJI.get(ContactStatus(status_value), "")
        table.add_row(
            str(c.get("id", "")),
            c.get("name", ""),
            c.get("title", "")[:30],
            f"{emoji} {status_value.replace('_', ' ')}",
        )

    console.print(table)
