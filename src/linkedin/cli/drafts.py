"""Drafts and templates commands."""

import click
from rich.panel import Panel
from rich.table import Table

from linkedin.cli import _contact_svc, _draft_svc, _template_svc, cli, console


@cli.group()
def drafts():
    """Generate and manage AI-powered outreach drafts."""
    pass


@drafts.command("connection")
@click.argument("contact_id", type=int)
def drafts_connection(contact_id):
    """Generate a personalized connection request for a contact."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating connection request for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_connection(contact_id)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Connection Request Draft", border_style="green"))
    console.print(f"\n[dim]Characters: {len(draft)}/300[/dim]")

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "connection", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("message")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="Additional context for the message")
def drafts_message(contact_id, context):
    """Generate a personalized follow-up message."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating message for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_message(contact_id, context)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Message Draft", border_style="blue"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "message", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("intro-request")
@click.argument("contact_id", type=int)
@click.option("--to", "target_id", type=int, required=True, help="Contact ID to be introduced to")
def drafts_intro_request(contact_id, target_id):
    """Generate a message asking for an introduction to another contact."""
    console.print("\n[bold]Generating intro request...[/bold]\n")

    error, draft = _draft_svc.generate_intro_request(contact_id, target_id)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Introduction Request Draft", border_style="magenta"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "intro_request", draft, target_contact_id=target_id)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("thank-you")
@click.argument("contact_id", type=int)
@click.option("--context", "-c", default="", help="What to thank them for")
def drafts_thank_you(contact_id, context):
    """Generate a thank you message after a call or meeting."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating thank you note for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_thank_you(contact_id, context)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title="Thank You Note Draft", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, "thank_you", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("follow-up")
@click.argument("contact_id", type=int)
@click.option("--attempt", "-a", type=int, default=1, help="Which follow-up attempt (1, 2, or 3)")
def drafts_follow_up(contact_id, attempt):
    """Generate a follow-up message after no response."""
    contact = _contact_svc.get_contact(contact_id)
    if not contact:
        console.print(f"[red]Contact #{contact_id} not found[/red]")
        return

    console.print(f"\n[bold]Generating follow-up #{attempt} for {contact['name']}...[/bold]\n")

    error, draft = _draft_svc.generate_follow_up(contact_id, attempt)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print(Panel(draft, title=f"Follow-up #{attempt} Draft", border_style="yellow"))

    if click.confirm("\nSave this draft?"):
        _draft_svc.save_draft(contact_id, f"follow_up_{attempt}", draft)
        console.print("[green]✓ Draft saved![/green]")


@drafts.command("batch-connections")
@click.option("--limit", "-l", type=int, default=5, help="Max number of drafts to generate")
@click.option("--save-all", is_flag=True, help="Save all drafts without prompting")
def drafts_batch_connections(limit, save_all):
    """Generate connection requests for all not_contacted contacts."""
    error, results = _draft_svc.generate_batch_connections(limit)

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    if not results:
        console.print("[green]✓ All contacts have been contacted![/green]")
        return

    console.print(f"\n[bold]Generating connection requests for {len(results)} contacts...[/bold]\n")

    generated = 0
    for contact, draft in results:
        console.print(f"\n[cyan]{contact['name']}[/cyan] ({contact['title']} at {contact['company']}):")
        console.print(Panel(draft, border_style="green"))
        console.print(f"[dim]Characters: {len(draft)}/300[/dim]\n")

        if save_all or click.confirm("Save this draft?"):
            _draft_svc.save_draft(contact["id"], "connection", draft)
            generated += 1

    console.print(f"\n[green]✓ Generated and saved {generated} drafts![/green]")


@drafts.command("list")
def drafts_list_cmd():
    """List all saved drafts."""
    result = _draft_svc.list_drafts()

    if not result:
        console.print("[yellow]No drafts yet. Generate one with: linkedin drafts connection <id>[/yellow]")
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
    draft = _draft_svc.get_draft(draft_id)
    if not draft:
        console.print(f"[red]Draft #{draft_id} not found[/red]")
        return

    console.print(Panel(draft["content"], title=f"Draft #{draft_id} ({draft['type']})", border_style="blue"))


# =============================================================================
# Template Commands
# =============================================================================


@cli.group()
def templates():
    """Smart message templates with A/B testing."""
    pass


@templates.command("list")
def templates_list():
    """List all saved templates."""
    all_templates = _template_svc.list_templates()
    if not all_templates:
        console.print("[yellow]No templates saved yet. Use 'linkedin templates save' to create one.[/yellow]")
        return

    table = Table(title="Templates")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Variant")
    table.add_column("Uses")
    table.add_column("Rate")

    for t in all_templates:
        table.add_row(
            str(t["id"]),
            t["name"],
            t.get("template_type", ""),
            t.get("variant", "A"),
            str(t.get("usage_count", 0)),
            t.get("response_rate", "0%"),
        )

    console.print(table)


@templates.command("save")
@click.option("--name", required=True, help="Template name")
@click.option("--type", "template_type", required=True, help="Template type (connection, message, follow_up)")
@click.option("--content", required=True, help="Template content with {{name}}, {{company}} placeholders")
@click.option("--variant", default="A", help="A/B variant (A or B)")
def templates_save(name, template_type, content, variant):
    """Save a new message template."""
    template = _template_svc.save_template(name, template_type, content, variant)
    console.print(f"[green]Template '{template['name']}' saved (ID: {template['id']}, variant {variant})[/green]")


@templates.command("use")
@click.argument("template_id", type=int)
@click.argument("contact_id", type=int)
def templates_use(template_id, contact_id):
    """Apply a template for a specific contact."""
    rendered = _template_svc.use_template(template_id, contact_id)
    if not rendered:
        console.print("[red]Template or contact not found.[/red]")
        return
    console.print(Panel(rendered, title="Rendered Template"))


@templates.command("ab-results")
def templates_ab_results():
    """Show A/B test results."""
    results = _template_svc.get_ab_results()
    if not results:
        console.print("[yellow]No A/B tests found. Create templates with the same name but different variants.[/yellow]")
        return

    for result in results:
        sig_marker = " ✓ Significant" if result["significant"] else " (not significant)"
        console.print(f"\n[bold]{result['name']}[/bold] — Best: {result['best_variant']}{sig_marker}")
        for v in result["variants"]:
            console.print(f"  Variant {v['variant']}: {v['usage_count']} uses, {v['response_count']} responses ({v['response_rate']})")
