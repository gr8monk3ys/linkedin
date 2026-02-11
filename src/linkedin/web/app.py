"""LinkedIn Job Hunt Assistant — Reflex Web App."""

import reflex as rx

from linkedin.web.pages.companies import companies_page
from linkedin.web.pages.contacts import contacts_page
from linkedin.web.pages.dashboard import dashboard_page
from linkedin.web.pages.discover import discover_page
from linkedin.web.pages.drafts import drafts_page
from linkedin.web.pages.research import research_page
from linkedin.web.pages.settings import settings_page

app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="medium",
        accent_color="blue",
    ),
)

app.add_page(dashboard_page, route="/", title="Dashboard | LinkedIn Assistant")
app.add_page(contacts_page, route="/contacts", title="Contacts | LinkedIn Assistant")
app.add_page(companies_page, route="/companies", title="Companies | LinkedIn Assistant")
app.add_page(drafts_page, route="/drafts", title="Drafts | LinkedIn Assistant")
app.add_page(discover_page, route="/discover", title="Discover | LinkedIn Assistant")
app.add_page(research_page, route="/research", title="Research | LinkedIn Assistant")
app.add_page(settings_page, route="/settings", title="Settings | LinkedIn Assistant")


def main():
    """Entry point for the web app."""
    import subprocess
    import sys

    subprocess.run([sys.executable, "-m", "reflex", "run"], check=True)
