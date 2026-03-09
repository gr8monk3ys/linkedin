"""Data management and dashboard commands."""

import click
from rich.table import Table

from linkedin.cli import _dashboard_svc, _data_svc, cli, console
from linkedin.constants import (
    DASHBOARD_PIPELINE,
    PRIORITY_EMOJI,
    CompanyPriority,
)


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
    try:
        if data_type == "contacts":
            count = _data_svc.import_contacts(file_path, merge)
            console.print(f"[green]✓ Imported {count} contacts[/green]")
        else:
            count = _data_svc.import_companies(file_path, merge)
            console.print(f"[green]✓ Imported {count} companies[/green]")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")


@data.command("backup")
@click.option("--output", "-o", default=None, help="Output backup file path")
def data_backup(output):
    """Create a backup of all data files."""
    try:
        backup_name, backed_up = _data_svc.create_backup(output)
        console.print(f"[green]✓ Backup created: {backup_name}[/green]")
        console.print(f"  Backed up {backed_up} files")
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")


@data.command("restore")
@click.argument("backup_file", type=click.Path(exists=True))
@click.confirmation_option(prompt="This will overwrite your current data. Continue?")
def data_restore(backup_file):
    """Restore data from a backup file."""
    try:
        restored = _data_svc.restore_backup(backup_file)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return
    if restored is None:
        console.print("[red]Not a valid backup file (must be a zip file)[/red]")
        return
    console.print(f"[green]✓ Restored {restored} files from backup[/green]")


@data.command("backups")
def data_backups():
    """List available backups."""
    try:
        backups = _data_svc.list_backups()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    if not backups:
        console.print("[yellow]No backups found[/yellow]")
        console.print("Create one with: linkedin data backup")
        return

    table = Table(title="Available Backups")
    table.add_column("Filename", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Created", style="green")

    for b in backups:
        table.add_row(b["name"], f"{b['size_kb']:.1f} KB", b["created"])

    console.print(table)
    console.print("\nRestore with: linkedin data restore <backup-file>")


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
        console.print("[yellow]⚠[/yellow] Profile: Not set up (run: linkedin profile setup)")

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
