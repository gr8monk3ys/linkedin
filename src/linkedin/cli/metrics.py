import click
from rich.table import Table

from linkedin.cli._common import _app, cli, console
from linkedin.cli.automate import _open_session


@cli.group("metrics")
def metrics():
    """The account's own numbers over time — the measurement the growth goal is judged by."""


@metrics.command("collect")
@click.option("--posts/--no-posts", default=True, help="Also read impressions for each recorded post")
@click.option("--headless", is_flag=True, help="Run without a visible browser window")
def metrics_collect(posts, headless):
    """Read followers, connections, profile views, impressions, search appearances, SSI. Read-only."""
    urns = [p["urn"] for p in _app.metrics_svc.post_rows()] if posts else []
    with _open_session(headless=headless) as session:
        result = session.metrics(post_urns=urns)
    if not result:
        console.print(f"[red]Metrics not read ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
    entry = _app.metrics_svc.record(result.data)
    unread = [k for k, v in entry.items() if k != "date" and v is None]
    console.print(f"[green]Recorded metrics for {entry['date']}.[/green]")
    _render_metrics(_app.metrics_svc.summary())
    if unread:
        console.print(f"[yellow]Could not read: {', '.join(unread)} — recorded as missing, not zero.[/yellow]")


@metrics.command("show")
@click.option("--days", default=7, help="Delta window in days")
def metrics_show(days):
    """Latest metrics and their change over the window."""
    summary = _app.metrics_svc.summary(days=days)
    if not summary:
        console.print("[dim]No metrics yet. Run: linkedin-cli metrics collect[/dim]")
        return
    console.print(f"[dim]Latest: {_app.metrics_svc.latest()['date']}[/dim]")
    _render_metrics(summary, days=days)
    posts = [p for p in _app.metrics_svc.post_rows() if p.get("impressions") is not None]
    if posts:
        table = Table(title="Post impressions")
        table.add_column("#", justify="right")
        table.add_column("Posted", style="dim")
        table.add_column("Impressions", justify="right")
        table.add_column("Text")
        for p in posts:
            text = p.get("text", "")
            table.add_row(
                str(p["id"]),
                p.get("posted_at", "")[:10],
                str(p["impressions"]),
                text if len(text) <= 50 else text[:47] + "...",
            )
        console.print(table)


def _render_metrics(summary: list[dict], days: int = 7) -> None:
    table = Table()
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column(f"Δ{days}d", justify="right")
    for m in summary:
        value = "[red]—[/red]" if m["value"] is None else str(m["value"])
        delta = "—" if m["delta"] is None else f"{m['delta']:+d}"
        table.add_row(m["metric"], value, delta)
    console.print(table)
