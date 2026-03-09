"""Discovery and research commands."""

import click
from rich.markdown import Markdown
from rich.panel import Panel

from linkedin.cli import _discover_svc, _research_svc, cli, console


@cli.group()
def discover():
    """AI-powered suggestions for contacts and companies."""
    pass


@discover.command("contacts")
@click.option("--company", "-c", default=None, help="Suggest contacts to find at a company")
@click.option("--role", "-r", default=None, help="Suggest contacts by role/title")
def discover_contacts(company, role):
    """Get AI suggestions for who to connect with."""
    error, suggestions = _discover_svc.discover_contacts(company, role)

    if error:
        if "Specify" in error:
            console.print(f"[yellow]{error}[/yellow]")
            console.print("Examples:")
            console.print("  linkedin discover contacts --company 'LangChain'")
            console.print("  linkedin discover contacts --role 'Engineering Manager'")
        else:
            console.print(f"[yellow]{error}[/yellow]")
        return

    label = f"at {company}" if company else f"for {role}"
    console.print(f"\n[bold]Finding who to connect with {label}...[/bold]\n")
    console.print(Panel(suggestions, title="Contact Discovery Suggestions", border_style="cyan"))


@discover.command("companies")
def discover_companies():
    """Get AI suggestions for companies to target."""
    error, suggestions = _discover_svc.discover_companies()

    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return

    console.print("\n[bold]Discovering companies to target...[/bold]\n")
    console.print(Panel(suggestions, title="Company Discovery Suggestions", border_style="green"))

    if click.confirm("\nWould you like to add any of these companies?"):
        console.print("[dim]Use 'linkedin companies add' to add companies[/dim]")


# =============================================================================
# Research Commands
# =============================================================================


@cli.group()
def research():
    """Research content strategies and post ideas."""
    pass


@research.command("engagement")
def research_engagement():
    """Show high-engagement content strategies for LinkedIn."""
    content = _research_svc.get_engagement_strategies()
    console.print(Markdown(content))


@research.command("ideas")
@click.option("--topic", "-t", default=None, help="Topic to generate ideas for")
def research_ideas(topic):
    """Generate post ideas based on your profile."""
    error, payload = _research_svc.generate_ideas(topic)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return
    focus, ideas = payload

    console.print(f"\n[bold]Generating post ideas for: {focus}...[/bold]\n")
    console.print(Panel(ideas, title="Post Ideas", border_style="green"))

    if click.confirm("\nSave these ideas?"):
        _research_svc.save_ideas(focus, ideas)
        console.print("[green]✓ Ideas saved![/green]")


@research.command("draft-post")
@click.argument("topic")
@click.option("--style", "-s", type=click.Choice(["story", "listicle", "contrarian", "how-to"]), default="story")
def research_draft_post(topic, style):
    """Generate a full post draft."""
    console.print(f"\n[bold]Generating {style} post about: {topic}...[/bold]\n")

    error, draft = _research_svc.generate_post_draft(topic, style)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return
    console.print(Panel(draft, title=f"Post Draft ({style})", border_style="green"))

    if click.confirm("\nSave this draft?"):
        _research_svc.save_post_draft(topic, style, draft)
        console.print("[green]✓ Post draft saved![/green]")


@research.command("hashtags")
@click.argument("topic")
def research_hashtags(topic):
    """Get hashtag recommendations for a topic."""
    console.print(f"\n[bold]Finding hashtags for: {topic}...[/bold]\n")

    error, hashtags = _research_svc.generate_hashtags(topic)
    if error:
        console.print(f"[yellow]{error}[/yellow]")
        return
    console.print(Panel(hashtags, title="Hashtag Recommendations", border_style="cyan"))
