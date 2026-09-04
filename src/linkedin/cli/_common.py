from importlib.metadata import PackageNotFoundError, version

import click
from rich.console import Console

from linkedin.ai.client import AIResult
from linkedin.app import App

console = Console()


def _app_version() -> str:
    """Read package version, falling back when running from source without install."""
    try:
        return version("linkedin")
    except PackageNotFoundError:
        return "0.0.0"


class _AppHandle:
    """The App for this process, built from the environment on first use.

    Commands reach services as `_app.contact_svc`. Nothing is built at import,
    so importing the CLI never touches disk, and a test redirects every store
    by setting LINKEDIN_DATA_DIR and calling `_app.reset()`.
    """

    def __init__(self) -> None:
        self._app: App | None = None

    def get(self) -> App:
        if self._app is None:
            self._app = App.from_env()
        return self._app

    def reset(self, app: App | None = None) -> None:
        self._app = app

    def __getattr__(self, name: str):
        return getattr(self.get(), name)


_app = _AppHandle()


def _warn_if_fallback(result: AIResult, used_context: bool = False) -> None:
    """Say out loud when a draft came from the offline template.

    A template is not a draft: it knows nothing about the conversation and
    cannot use --context. Passing one back silently is how a --context of
    instructions ended up as the message body. The API key commonly lives in
    ~/.linkedin-cli/cron.env, which only cron sources — so scheduled runs get
    real drafts while interactive ones quietly degrade.
    """
    if not result.was_fallback:
        return
    console.print(f"[yellow]⚠ AI unavailable ({result.error}) — this is an offline template, not a draft.[/yellow]")
    if used_context:
        console.print("[yellow]  Your --context was NOT used. Edit before sending.[/yellow]")
    console.print("[dim]  Set ANTHROPIC_API_KEY (one may already be in ~/.linkedin-cli/cron.env).[/dim]")


@click.group()
@click.version_option(version=_app_version(), prog_name="linkedin-cli")
def cli():
    """
    LinkedIn Job Hunt Assistant

    \b
    A local CRM + AI-powered tool to accelerate your job search:
    - Track contacts and outreach status
    - Generate personalized drafts with AI
    - Research high-engagement content
    - Plan your LinkedIn strategy

    \b
    Quick Start:
      1. linkedin-cli profile setup     # Add your info
      2. linkedin-cli contacts add      # Add target contacts
      3. linkedin-cli drafts connection <contact-id>   # AI writes your outreach
    """
    pass


def _exit_unless_ok(result, *, dry_run_message: str, failure_prefix: str) -> None:
    """Common tail: say what happened; exit nonzero unless the verb succeeded."""
    if result.dry_run:
        console.print(f"[cyan]Dry run:[/cyan] {dry_run_message}")
        raise SystemExit(0)
    if not result:
        console.print(f"[red]{failure_prefix} ({result.status}: {result.reason}).[/red]")
        raise SystemExit(1)
