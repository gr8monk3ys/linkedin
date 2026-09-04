from datetime import datetime, timedelta

import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.automate import _open_session
from linkedin.data.json_store import load_json, save_json
from linkedin.services.inbox_service import inbound_from_strangers, review_proposals, update_thread_index


def load_inbox_proposals() -> list[dict]:
    """Proposed pipeline transitions awaiting confirmation."""
    return load_json(_app.data_dir.inbox_proposals, [])


def save_inbox_proposals(proposals: list[dict]) -> None:
    save_json(_app.data_dir.inbox_proposals, proposals)


@cli.group("inbox")
def inbox():
    """Read replies and accepted invitations, and confirm what they imply.

    Every other automation action is outbound, so a contact stays at the status
    it was created with until a human retypes it. These commands are the inbound
    edge — and they only ever *propose* a change.
    """


@inbox.command("sync")
@click.option("--limit", "-l", default=25, help="Max message threads to read")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def inbox_sync(limit, headless):
    """Read LinkedIn messaging and sent invitations; save proposed transitions."""
    with _open_session(headless=headless) as session:
        result = session.inbox(thread_limit=limit)
    signals = result.data or {"threads": [], "pending_invitations": None}
    if not result:
        console.print(f"[yellow]Inbox not read ({result.status}: {result.reason}).[/yellow]")

    pending = signals["pending_invitations"]
    if pending is None:
        console.print(
            "[yellow]Could not read the sent-invitation list — skipping acceptance checks.[/yellow]\n"
            "[dim]An empty list would mean 'every invitation was accepted', so it is not assumed.[/dim]"
        )

    contacts = _app.contact_repo.list_all()
    proposals = _app.inbox_svc.propose_transitions(signals["threads"], pending, contacts)
    save_inbox_proposals(proposals)
    index = update_thread_index(load_json(_app.data_dir.thread_index, []), signals["threads"], contacts)
    save_json(_app.data_dir.thread_index, index)

    strangers = inbound_from_strangers(index, datetime.now().date() - timedelta(days=30))
    console.print(
        f"[dim]Read {len(signals['threads'])} thread(s); {len(strangers)} inbound from strangers in the last 30 days.[/dim]"
    )
    if not proposals:
        console.print("[green]No pipeline changes to propose.[/green]")
        return
    _render_proposals(proposals)
    console.print("\n[dim]Apply with: linkedin-cli inbox review[/dim]")


@inbox.command("list")
def inbox_list():
    """Show proposed transitions awaiting confirmation."""
    proposals = load_inbox_proposals()
    if not proposals:
        console.print("[dim]No pending proposals. Run: linkedin-cli inbox sync[/dim]")
        return
    _render_proposals(proposals)


@inbox.command("review")
@click.option("--yes", is_flag=True, help="Apply every high-confidence proposal without prompting")
def inbox_review(yes):
    """Confirm proposed transitions one at a time and apply them.

    `--yes` applies high-confidence proposals only. A low-confidence proposal
    matched a contact by display name alone, so it is always asked about.
    """
    proposals = load_inbox_proposals()
    if not proposals:
        console.print("[dim]No pending proposals. Run: linkedin-cli inbox sync[/dim]")
        return

    def confirm(proposal: dict, low: bool) -> bool:
        console.print(
            f"\n[bold cyan]{proposal.get('name')}[/bold cyan] "
            f"{proposal.get('from_status')} → {proposal.get('to_status')}"
            + (" [red](matched by name only)[/red]" if low else "")
        )
        console.print(f"  [dim]{proposal.get('evidence', '')}[/dim]")
        return click.confirm("  Apply?", default=not low)

    review = review_proposals(proposals, _app.contact_repo.list_all(), confirm=confirm, yes=yes)
    for proposal, why in review.dropped:
        console.print(f"[yellow]{proposal.get('name')} — dropping this proposal: {why}.[/yellow]")
    for proposal in review.apply:
        _app.contact_svc.update_contact(proposal["contact_id"], status=proposal["to_status"])
    save_inbox_proposals(review.kept)
    console.print(
        f"\n[green]Applied {len(review.apply)}[/green]"
        + (f", kept {len(review.kept)} for later" if review.kept else "")
    )


@inbox.command("strangers")
@click.option("--days", default=30, help="Window in days (default 30)")
def inbox_strangers(days):
    """People who are not contacts and wrote to you in the window — the inbound metric."""
    index = load_json(_app.data_dir.thread_index, [])
    rows = inbound_from_strangers(index, datetime.now().date() - timedelta(days=days))
    console.print(
        f"[bold]{len(rows)}[/bold] inbound from strangers in the last {days} days"
        + ("." if rows else " (run: linkedin-cli inbox sync).")
    )
    if not rows:
        return
    table = Table()
    table.add_column("Name", style="cyan")
    table.add_column("Last wrote", style="dim")
    table.add_column("Profile", style="dim")
    for row in rows:
        table.add_row(row.get("name", ""), row.get("last_message_at", ""), row.get("url", ""))
    console.print(table)


def _render_proposals(proposals: list[dict]) -> None:
    table = Table(title="Proposed pipeline changes")
    table.add_column("Contact", style="cyan")
    table.add_column("Transition", style="yellow")
    table.add_column("Source", style="dim")
    table.add_column("Evidence", style="dim")
    for proposal in proposals:
        marker = " [red](low)[/red]" if proposal.get("confidence") == "low" else ""
        table.add_row(
            proposal.get("name", "Unknown"),
            f"{proposal.get('from_status', '')} → {proposal.get('to_status', '')}{marker}",
            proposal.get("source", ""),
            proposal.get("evidence", ""),
        )
    console.print(table)
