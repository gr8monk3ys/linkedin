import click

from linkedin.cli._common import _app, cli, console
from linkedin.settings import load_settings, set_setting


@cli.group("settings")
def settings():
    """Per-installation choices (settings.json in the data dir)."""


@settings.command("show")
def settings_show():
    for key, value in load_settings(_app.data_dir).items():
        console.print(f"{key}: {value}")


@settings.command("ai")
@click.argument("state", type=click.Choice(["on", "off"]))
def settings_ai(state):
    """Turn model calls on or off. Off means drafts are written by hand and the daily run does not draft."""
    current = set_setting("ai_enabled", state == "on", _app.data_dir)
    console.print(
        f"[green]ai_enabled: {current['ai_enabled']}[/green]"
        + (
            ""
            if state == "on"
            else "  (run-daily skips drafting; posts add-candidate and drafts add take hand-written text)"
        )
    )
