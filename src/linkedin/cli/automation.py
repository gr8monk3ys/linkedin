"""Automation commands."""

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli import _company_repo, _contact_svc, _profile_repo, cli, console
from linkedin.services.automation_service import AutomationService


@cli.group()
def auto():
    """LinkedIn browser automation."""
    pass


@auto.command("login")
@click.option("--email", prompt=True, help="LinkedIn email")
@click.option("--password", prompt=True, hide_input=True, help="LinkedIn password")
def auto_login(email, password):
    """Save credentials and test login."""
    from linkedin.automation.config import AutomationConfig

    svc = AutomationService(_contact_svc, _company_repo, _profile_repo, AutomationConfig())
    console.print("[bold]Testing LinkedIn login...[/bold]")
    success = svc.login(email, password)
    if success:
        console.print("[green]✓ Login successful! Credentials and session saved.[/green]")
    else:
        console.print("[red]✗ Login failed. Check your credentials.[/red]")


@auto.command("connect")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.option("--limit", default=20, help="Max connections to send")
@click.option("--headless", is_flag=True, help="Run browser without window")
def auto_connect(dry_run, limit, headless):
    """Search LinkedIn and send personalized connection requests."""
    from linkedin.automation.config import AutomationConfig

    config = AutomationConfig(headless=headless)
    svc = AutomationService(_contact_svc, _company_repo, _profile_repo, config)

    mode_label = "[yellow]DRY RUN[/yellow] " if dry_run else ""
    console.print(f"\n{mode_label}[bold]Starting connection automation (limit: {limit})...[/bold]\n")

    results = svc.run_connect(limit=limit, dry_run=dry_run)

    if not results:
        console.print("[yellow]No candidates found. Add target companies or set up your profile.[/yellow]")
        return

    # Check for login failure
    if len(results) == 1 and results[0].get("reason") == "Login failed":
        console.print("[red]✗ Login failed. Run 'linkedin auto login' first.[/red]")
        return

    # Results table
    table = Table(title="Connection Results")
    table.add_column("Name", style="cyan")
    table.add_column("Company", style="dim")
    table.add_column("Note", max_width=40)
    table.add_column("Status", justify="center")

    sent = 0
    failed = 0
    for r in results:
        status = "[green]✓ Sent[/green]" if r["success"] else f"[red]✗ {r.get('reason', 'failed')}[/red]"
        note_preview = (r["note"][:37] + "...") if len(r.get("note", "")) > 40 else r.get("note", "")
        table.add_row(r["name"], r["company"], note_preview, status)
        if r["success"]:
            sent += 1
        else:
            failed += 1

    console.print(table)
    console.print(f"\n[bold]Summary:[/bold] {sent} sent, {failed} failed out of {len(results)} candidates")


@auto.command("engage")
@click.option("--dry-run", is_flag=True, help="Preview without liking/commenting")
@click.option("--limit", default=10, help="Max posts to engage with")
@click.option("--comments", default=5, help="How many posts to comment on")
@click.option("--headless", is_flag=True, help="Run browser headless")
def auto_engage(dry_run, limit, comments, headless):
    """Browse feed and engage — like posts and leave AI-personalized comments."""
    from linkedin.automation.config import AutomationConfig

    config = AutomationConfig(headless=headless)
    svc = AutomationService(_contact_svc, _company_repo, _profile_repo, config)

    mode_label = "[yellow]DRY RUN[/yellow] " if dry_run else ""
    console.print(f"\n{mode_label}[bold]Starting feed engagement (limit: {limit}, comments: {comments})...[/bold]\n")

    results = svc.run_engage(limit=limit, comment_count=comments, dry_run=dry_run)

    if not results:
        console.print("[yellow]No posts found in feed. Try again later.[/yellow]")
        return

    # Check for login failure
    if len(results) == 1 and results[0].get("reason") == "Login failed":
        console.print("[red]✗ Login failed. Run 'linkedin auto login' first.[/red]")
        return

    # Results table
    table = Table(title="Engagement Results")
    table.add_column("Author", style="cyan")
    table.add_column("Content", max_width=30, style="dim")
    table.add_column("Liked", justify="center")
    table.add_column("Commented", justify="center")
    table.add_column("Comment", max_width=40)

    liked_count = 0
    commented_count = 0
    for r in results:
        liked_str = "[green]✓[/green]" if r["liked"] else "[dim]–[/dim]"
        commented_str = "[green]✓[/green]" if r["commented"] else "[dim]–[/dim]"
        comment_preview = (r["comment_text"][:37] + "...") if len(r.get("comment_text", "")) > 40 else r.get("comment_text", "")
        table.add_row(r["author"], r["content_preview"], liked_str, commented_str, comment_preview)
        if r["liked"]:
            liked_count += 1
        if r["commented"]:
            commented_count += 1

    console.print(table)
    console.print(f"\n[bold]Summary:[/bold] {liked_count} liked, {commented_count} commented out of {len(results)} posts")


@auto.command("status")
def auto_status():
    """Show today's automation stats."""
    from linkedin.automation.config import AutomationConfig

    svc = AutomationService(_contact_svc, _company_repo, _profile_repo, AutomationConfig())
    status = svc.get_status()

    console.print(Panel("[bold]Automation Status[/bold]", style="blue"))
    console.print(f"  Connections sent today:     {status['connections_sent']}")
    console.print(f"  Connections remaining:      {status['connections_remaining']}")
    console.print(f"  Messages sent today:        {status['messages_sent']}")
    console.print(f"  Messages remaining:         {status['messages_remaining']}")
    console.print(f"  Profile views:              {status['profile_views']}")
    console.print(f"  Searches performed:         {status['searches']}")
    console.print(f"  Likes given today:          {status['likes_given']}")
    console.print(f"  Likes remaining:            {status['likes_remaining']}")
    console.print(f"  Comments posted today:      {status['comments_posted']}")
    console.print(f"  Comments remaining:          {status['comments_remaining']}")
