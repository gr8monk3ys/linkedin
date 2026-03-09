"""Analytics, market intelligence, and optimizer commands."""

import click
from rich.markdown import Markdown
from rich.panel import Panel

from linkedin.cli import _analytics_svc, _market_svc, _optimizer_svc, cli, console


@cli.group()
def analytics():
    """View outreach analytics and pipeline metrics."""
    pass


@analytics.command("summary")
def analytics_summary():
    """Show analytics summary with key metrics."""
    data = _analytics_svc.get_summary()

    console.print(Panel("[bold]Analytics Summary[/bold]", style="blue"))
    console.print(f"  Total contacts: {data['total_contacts']}")
    console.print(f"  Response rate: {data['response_rate']}")
    console.print(f"  Conversion rate: {data['conversion_rate']}")
    console.print(f"  Outreach velocity: {data['outreach_velocity']}")

    if data["pipeline"]:
        console.print("\n[bold]Pipeline:[/bold]")
        for status, count in data["pipeline"].items():
            bar = "█" * count
            console.print(f"  {status.replace('_', ' ').title():20s} {bar} {count}")

    if data["source_effectiveness"]:
        console.print("\n[bold]Source Effectiveness:[/bold]")
        for source, info in data["source_effectiveness"].items():
            console.print(f"  {source.replace('_', ' '):20s} {info['responded']}/{info['total']} ({info['rate']})")

    if data["draft_type_counts"]:
        console.print("\n[bold]Draft Types:[/bold]")
        for dtype, count in data["draft_type_counts"].items():
            console.print(f"  {dtype.replace('_', ' '):20s} {count}")


@analytics.command("conversion")
def analytics_conversion():
    """Show pipeline conversion funnel."""
    funnel = _analytics_svc.get_conversion_funnel()
    if not funnel:
        console.print("[yellow]No contacts yet. Add contacts to see conversion data.[/yellow]")
        return

    console.print(Panel("[bold]Conversion Funnel[/bold]", style="blue"))
    for stage in funnel:
        bar_width = min(50, stage["remaining"])
        bar = "█" * bar_width
        console.print(f"  {stage['stage']:20s} {bar} {stage['remaining']} ({stage['pct']})")


@analytics.command("velocity")
@click.option("--weeks", default=8, help="Number of weeks to show")
def analytics_velocity(weeks):
    """Show outreach velocity over time."""
    data = _analytics_svc.get_velocity(weeks)

    console.print(Panel("[bold]Outreach Velocity[/bold]", style="blue"))
    max_count = max((d["contacts"] for d in data), default=1) or 1
    for entry in data:
        bar_width = int(entry["contacts"] / max_count * 30) if max_count > 0 else 0
        bar = "█" * bar_width
        console.print(f"  {entry['week']:10s} {bar} {entry['contacts']}")


# =============================================================================
# Market Intelligence Commands
# =============================================================================


@cli.group()
def market():
    """Job market intelligence and salary estimates."""
    pass


@market.command("analyze")
@click.option("--role", default="", help="Target role to analyze")
@click.option("--industry", default="", help="Target industry")
def market_analyze(role, industry):
    """Get AI market analysis for a role/industry."""
    console.print("\n[bold]Analyzing market...[/bold]\n")
    error, result = _market_svc.analyze_market(role, industry)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("salary")
@click.option("--role", default="", help="Target role")
@click.option("--location", default="", help="Location")
def market_salary(role, location):
    """Get AI salary estimates for a role."""
    console.print("\n[bold]Estimating salary...[/bold]\n")
    error, result = _market_svc.estimate_salary(role, location)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@market.command("trends")
@click.option("--industry", default="", help="Industry to analyze")
def market_trends(industry):
    """Get AI hiring trend analysis."""
    console.print("\n[bold]Analyzing trends...[/bold]\n")
    error, result = _market_svc.analyze_trends(industry)
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


# =============================================================================
# Profile Optimizer Commands
# =============================================================================


@cli.group()
def optimize():
    """AI-powered LinkedIn profile optimization."""
    pass


@optimize.command("headline")
def optimize_headline():
    """Generate optimized headline variants."""
    console.print("\n[bold]Generating headline options...[/bold]\n")
    error, result = _optimizer_svc.optimize_headline()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("about")
def optimize_about():
    """Generate optimized About section."""
    console.print("\n[bold]Generating About section...[/bold]\n")
    error, result = _optimizer_svc.optimize_about()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("skills")
def optimize_skills():
    """Analyze and optimize skills."""
    console.print("\n[bold]Analyzing skills...[/bold]\n")
    error, result = _optimizer_svc.optimize_skills()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))


@optimize.command("full")
def optimize_full():
    """Full profile optimization review."""
    console.print("\n[bold]Running full optimization review...[/bold]\n")
    error, result = _optimizer_svc.optimize_full()
    if error:
        console.print(f"[red]{error}[/red]")
    else:
        console.print(Markdown(result))
