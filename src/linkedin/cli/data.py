import json
from pathlib import Path

import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console


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
