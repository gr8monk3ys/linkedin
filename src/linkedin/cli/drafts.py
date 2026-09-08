from pathlib import Path

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli._common import _app, _warn_if_fallback, cli, console


@cli.group()
def drafts():
    """Generate and manage AI-powered outreach drafts."""
    pass


@drafts.command("connection")
@click.argument("contact_id", type=int)
def drafts_connection(contact_id):
    """Generate a personalized connection request for a contact."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating connection request for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_connection(contact_id)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Connection Request Draft", border_style="green"))
    _warn_if_fallback(result, used_context=False)
    console.print(f"\n[dim]Characters: {len(draft)}/300[/dim]")

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "connection", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("message")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="Additional context for the message")
def drafts_message(contact_id, context):
    """Generate a personalized follow-up message."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating message for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_message(contact_id, context)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Message Draft", border_style="blue"))
    _warn_if_fallback(result, used_context=True)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "message", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("intro-request")
@click.argument("contact_id", type=int)
@click.option("--to", "target_id", type=int, required=True, help="Contact ID to be introduced to")
def drafts_intro_request(contact_id, target_id):
    """Generate a message asking for an introduction to another contact."""
    console.print("\n[bold]Generating intro request...[/bold]\n")

    result = _app.draft_svc.generate_intro_request(contact_id, target_id)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Introduction Request Draft", border_style="magenta"))
    _warn_if_fallback(result, used_context=False)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "intro_request", draft, source=result.source, target_contact_id=target_id)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("thank-you")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="What to thank them for")
def drafts_thank_you(contact_id, context):
    """Generate a thank you message after a call or meeting."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating thank you note for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_thank_you(contact_id, context)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title="Thank You Note Draft", border_style="green"))
    _warn_if_fallback(result, used_context=True)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, "thank_you", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("follow-up")
@click.argument("contact_id", type=int)
@click.option("--attempt", "-a", type=int, default=1, help="Which follow-up attempt (1, 2, or 3)")
def drafts_follow_up(contact_id, attempt):
    """Generate a follow-up message after no response."""
    contact = _app.contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating follow-up #{attempt} for {contact['name']}...[/bold]\n")

    result = _app.draft_svc.generate_follow_up(contact_id, attempt)
    if not result:
        console.print(f"[yellow]{result.error}[/yellow]")
        return
    draft = result.text

    console.print(Panel(draft, title=f"Follow-up #{attempt} Draft", border_style="yellow"))
    _warn_if_fallback(result)

    if click.confirm("\nSave this draft?"):
        _app.draft_svc.save_draft(contact_id, f"follow_up_{attempt}", draft, source=result.source)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("batch-connections")
@click.option("--limit", "-l", type=int, default=5, help="Max number of drafts to generate")
@click.option("--save-all", is_flag=True, help="Save all drafts without prompting")
def drafts_batch_connections(limit, save_all):
    """Generate connection requests for all not_contacted contacts."""
    error, results = _app.draft_svc.generate_batch_connections(limit)

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    if not results:
        console.print("[green]✓ All contacts have been contacted![/green]")
        return

    console.print(f"\n[bold]Generating connection requests for {len(results)} contacts...[/bold]\n")

    generated = 0
    for contact, result in results:
        draft = result.text
        console.print(f"\n[cyan]{contact['name']}[/cyan] ({contact['title']} at {contact['company']}):")
        console.print(Panel(draft, border_style="green"))
        _warn_if_fallback(result)
        console.print(f"[dim]Characters: {len(draft)}/300[/dim]\n")

        if save_all or click.confirm("Save this draft?"):
            _app.draft_svc.save_draft(contact["id"], "connection", draft, source=result.source)
            generated += 1

    console.print(f"\n[green]✓ Generated and saved {generated} drafts![/green]")


@drafts.command("add")
@click.argument("contact_id", type=int)
@click.option("--file", "path", type=click.Path(exists=True), default=None, help="Read the message from a file")
@click.option("--text", default="", help="Message text (or pipe it on stdin)")
@click.option("--type", "draft_type", default="message", help="Draft type (message, connection, follow_up_1, ...)")
def drafts_add(contact_id, path, text, draft_type):
    """Save a hand-written draft for a contact so automate message/connect can send it."""
    if not _app.contact_repo.get(contact_id):
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        raise SystemExit(1)
    body = Path(path).read_text() if path else (text or click.get_text_stream("stdin").read())
    if not body.strip():
        console.print("[red]No text given.[/red]")
        raise SystemExit(1)
    draft = _app.draft_svc.save_draft(contact_id, draft_type, body.strip(), source="ai", generated_from="hand-written")
    console.print(
        f"[green]Draft #{draft['id']} saved for contact #{contact_id}.[/green] Send with: linkedin-cli automate message {contact_id} --draft-id {draft['id']}",
        soft_wrap=True,
    )


@drafts.command("delete")
@click.argument("draft_id", type=int)
@click.confirmation_option(prompt="Delete this draft?")
def drafts_delete(draft_id):
    """Delete a saved draft."""
    if _app.draft_svc.delete_draft(draft_id):
        console.print(f"[green]Deleted draft #{draft_id}.[/green]")
    else:
        console.print(f"[red]Draft #{draft_id} not found.[/red]")
        raise SystemExit(1)


@drafts.command("list")
def drafts_list_cmd():
    """List all saved drafts."""
    result = _app.draft_svc.list_drafts()

    if not result:
        console.print("[yellow]No drafts yet. Generate one with: linkedin-cli drafts connection <id>[/yellow]")
        return

    table = Table(title="Saved Drafts")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("For", style="green")
    table.add_column("Preview", style="white")
    table.add_column("Created", style="dim")

    for d in result:
        preview = d["content"][:50] + "..." if len(d["content"]) > 50 else d["content"]
        table.add_row(
            str(d["id"]),
            d["type"],
            d.get("contact_name", "Unknown"),
            preview,
            d["created_at"][:10],
        )

    console.print(table)


@drafts.command("view")
@click.argument("draft_id", type=int)
def drafts_view(draft_id):
    """View a saved draft."""
    draft = _app.draft_svc.get_draft(draft_id)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found[/red]")
        return

    console.print(Panel(draft["content"], title=f"Draft #{draft_id} ({draft['type']})", border_style="blue"))
