import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console


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
        console.print(
            f"[dim]Headline and About come from the {data['copy_source']} (docs/linkedin-copy.md); the local copy is a fallback.[/dim]"
        )
