import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console


@cli.group()
def postings():
    """Job postings scored against your profile; what `automate jobs` imports and the daily plan reads."""
    pass


@postings.command("add")
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
    posting = _app.posting_svc.add_posting(
        {
            "title": title,
            "company": company,
            "location": location,
            "skills_required": skills,
            "url": url,
            "source": source,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "notes": notes,
        }
    )
    console.print(f"[green]✓ Added posting #{posting['id']}: {posting['title']} at {posting['company']}[/green]")


@postings.command("import")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--merge", is_flag=True, help="Merge with existing postings instead of replacing")
def market_import_postings(file_path, merge):
    """Import job postings from CSV or JSON."""
    try:
        imported, skipped = _app.posting_svc.import_postings(file_path, merge=merge)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return

    console.print(f"[green]✓ Imported {imported} posting(s)[/green]")
    if skipped:
        console.print(f"[yellow]Skipped {skipped} duplicate/invalid posting(s)[/yellow]")


@postings.command("list")
@click.option("--limit", "-l", type=int, default=20, help="Max postings to show")
@click.option("--min-score", type=int, default=0, help="Minimum profile-match score (0-100)")
def market_postings(limit, min_score):
    """List tracked postings ranked by profile match."""
    postings = _app.posting_svc.list_postings(limit=limit, min_score=min_score)
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
