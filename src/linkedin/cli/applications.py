import click
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.services.resume_service import (
    ResumeRepoError,
    import_autoapply_applications,
    list_variants,
    match_variants,
    merge_into_applications,
    resolve_pdf,
)


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
            console.print(f"  {(event.get('date') or '')[:10]}  {event.get('status')}  {event.get('notes') or ''}")


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
    console.print(
        f"\nAttach with: linkedin-cli applications attach-resume {application_id} --variant {ranked[0]['variant']}"
    )


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
        console.print(
            f"[yellow]No built PDF for '{variant}' (run ./build.sh in the resume repo). Recording variant only.[/yellow]"
        )
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
