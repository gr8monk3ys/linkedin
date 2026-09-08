from datetime import datetime
from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.automate import _publish
from linkedin.cli.metrics import _render_metrics
from linkedin.services.fleet_facts import collect_fleet_facts, facts_digest


@cli.group("posts")
def posts():
    """Posts that went out through this tool, with the IDs that join them to metrics."""


@posts.command("facts")
@click.option("--days", default=7, help="Window in days")
def posts_facts(days):
    """What the public fleet did this week — the only thing the drafter is allowed to see."""
    facts = collect_fleet_facts(days=days)
    console.print(Panel(facts_digest(facts), title=f"Public fleet, last {days} days"))


@posts.command("draft-week")
@click.option("--count", default=3, help="Candidates to draft")
@click.option("--days", default=7, help="Window of fleet activity to draw on")
def posts_draft_week(count, days):
    """Draft this week's candidates from public fleet facts (the Sunday batch, step 1)."""
    facts = collect_fleet_facts(days=days)
    console.print(Panel(facts_digest(facts), title=f"Public fleet, last {days} days"))
    saved = 0
    for style, result in _app.content_svc.draft_candidates(facts, count=count):
        if not result.ok:
            console.print(f"[red]{style}: no draft — {result.error or 'AI unavailable'}[/red]")
            continue
        draft = _app.content_svc.save_candidate(result.text, style, facts)
        saved += 1
        console.print(Panel(draft["content"], title=f"Candidate #{draft['id']} ({style})", border_style="cyan"))
    if not saved:
        console.print(
            "[red]No candidates. A template is never a post, so nothing was saved. Check: linkedin-cli automation doctor --probe-ai[/red]"
        )
        raise SystemExit(1)
    console.print(f"[green]{saved} candidate(s) saved.[/green] Review with: linkedin-cli posts review")


@posts.command("add-candidate")
@click.option("--file", "path", type=click.Path(exists=True), default=None, help="Read the post text from a file")
@click.option("--text", default="", help="Post text (or pipe it on stdin)")
@click.option("--style", default="story", help="Angle label kept with the draft")
def posts_add_candidate(path, text, style):
    """Queue a hand-written post for the Sunday review, the same way draft-week queues a model's."""
    body = Path(path).read_text() if path else (text or click.get_text_stream("stdin").read())
    if not body.strip():
        console.print("[red]No text given.[/red]")
        raise SystemExit(1)
    facts = {"since": "hand", "until": datetime.now().date().isoformat()}
    draft = _app.content_svc.save_candidate(body, style, facts, hand_written=True)
    console.print(f"[green]Candidate #{draft['id']} queued.[/green] Review with: linkedin-cli posts review")


@posts.command("review")
@click.option("--publish-on", default=None, help="Date for approved posts (default: next Tuesday)")
def posts_review(publish_on):
    """Approve or reject each pending candidate; approved ones are scheduled (the Sunday batch, step 2)."""
    pending = _app.content_svc.pending_candidates()
    if not pending:
        console.print("[dim]No pending candidates. Run: linkedin-cli posts draft-week[/dim]")
        return
    metrics = _app.metrics_svc.summary()
    if metrics:
        console.print("[bold]Yesterday's numbers[/bold]")
        _render_metrics(metrics)
    approved = rejected = kept = 0
    for draft in pending:
        console.print(
            Panel(draft["content"], title=f"Candidate #{draft['id']} — {draft.get('topic', '')}", border_style="cyan")
        )
        choice = click.prompt(
            "  [a]pprove / [r]eject / [s]kip", type=click.Choice(["a", "r", "s"]), default="s", show_choices=False
        )
        if choice == "a":
            entry = _app.content_svc.approve(draft["id"], publish_on)
            approved += 1
            console.print(f"  [green]Scheduled for {entry['scheduled_date']} (calendar #{entry['id']}).[/green]")
        elif choice == "r":
            _app.content_svc.reject(draft["id"])
            rejected += 1
        else:
            kept += 1
    console.print(
        f"\n[green]Approved {approved}[/green], rejected {rejected}, left {kept} pending. Publish with: linkedin-cli posts publish-due"
    )


@posts.command("publish-due")
@click.option("--force", is_flag=True, help="Publish even when the last posts underperformed")
@click.option("--dry-run", is_flag=True, help="Do everything except publish")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def posts_publish_due(force, dry_run, headless):
    """Publish the next scheduled post, unless the skip rule says not to (the Sunday batch, step 3)."""
    decision = _app.content_svc.publish_decision(force=force)
    if decision["skip"] and decision["entry"] is None:
        console.print(f"[dim]{decision['skip'].capitalize()}.[/dim]")
        return
    entry, draft = decision["entry"], decision["draft"]
    if decision["skip"]:
        console.print(f"[yellow]Skipping calendar #{entry['id']}: {decision['skip']}.[/yellow]")
        console.print("[dim]  Pass --force to publish anyway. The entry stays scheduled.[/dim]")
        raise SystemExit(2)
    console.print(Panel(draft["content"], title=f"Publishing calendar #{entry['id']} (draft #{draft['id']})"))
    _publish(draft["content"], draft_id=draft["id"], calendar_id=entry["id"], dry_run=dry_run, headless=headless)


@posts.command("list")
def posts_list():
    """List published posts, newest first."""
    rows = _app.post_svc.list_posts()
    if not rows:
        console.print("[dim]No posts published through this tool yet.[/dim]")
        return
    table = Table(title="Published posts")
    table.add_column("#", justify="right")
    table.add_column("Posted", style="dim")
    table.add_column("URN")
    table.add_column("Text")
    for p in rows:
        text = p.get("text", "")
        table.add_row(
            str(p["id"]),
            p.get("posted_at", "")[:16],
            p.get("urn") or "[red]unreadable[/red]",
            text if len(text) <= 60 else text[:57] + "...",
        )
    console.print(table)
    missing = _app.post_svc.unmeasurable()
    if missing:
        console.print(f"[yellow]{len(missing)} post(s) have no URN and cannot be joined to metrics.[/yellow]")
