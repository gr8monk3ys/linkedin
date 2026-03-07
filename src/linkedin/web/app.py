"""LinkedIn Job Hunt Assistant — Reflex Web App."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import reflex as rx

from linkedin.web.pages.companies import companies_page
from linkedin.web.pages.contacts import contacts_page
from linkedin.web.pages.dashboard import dashboard_page
from linkedin.web.pages.discover import discover_page
from linkedin.web.pages.drafts import drafts_page
from linkedin.web.pages.research import research_page
from linkedin.web.pages.settings import settings_page

PAGE_SPECS = [
    (dashboard_page, "/", "Dashboard | LinkedIn Assistant"),
    (contacts_page, "/contacts", "Contacts | LinkedIn Assistant"),
    (companies_page, "/companies", "Companies | LinkedIn Assistant"),
    (drafts_page, "/drafts", "Drafts | LinkedIn Assistant"),
    (discover_page, "/discover", "Discover | LinkedIn Assistant"),
    (research_page, "/research", "Research | LinkedIn Assistant"),
    (settings_page, "/settings", "Settings | LinkedIn Assistant"),
]
REGISTERED_ROUTES = [route for _, route, _ in PAGE_SPECS]


app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="medium",
        accent_color="blue",
    ),
)

for page, route, title in PAGE_SPECS:
    app.add_page(page, route=route, title=title)


def get_reflex_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build the environment used to launch Reflex."""
    env = (base_env or os.environ).copy()
    # Reflex defaults to a user app-support directory, which is not always writable in sandboxed environments.
    env.setdefault("REFLEX_DIR", os.path.join(tempfile.gettempdir(), "linkedin_reflex"))
    return env


def get_reflex_run_command(args: list[str] | None = None) -> list[str]:
    """Build the subprocess command used to launch Reflex."""
    return [sys.executable, "-m", "reflex", "run", *(args or [])]


def main() -> None:
    """Entry point for the web app."""
    subprocess.run(get_reflex_run_command(sys.argv[1:]), check=True, env=get_reflex_env())
