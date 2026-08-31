"""Login action for LinkedIn.

Import-safe without Playwright or keyring: both are imported inside the
functions that need them, so this module can be imported (and tested) in CI,
which installs only `--extra dev`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.linkedin_page import LinkedInPage

if TYPE_CHECKING:
    from linkedin.automation.browser import BrowserManager


def login_action(browser: BrowserManager, email: str | None = None, password: str | None = None) -> bool:
    """Log in to LinkedIn using stored or provided credentials.

    Returns True if login succeeded. On every failure the browser is left on
    LinkedIn's login page, because the caller's fallback is to hand the window
    to a human — and a False that never navigated left them staring at
    about:blank, told to log in on a page that was not there.
    """
    from linkedin.automation.credentials import get_credentials

    page = browser.page
    if not page:
        return False

    linkedin = LinkedInPage(page)

    if not email or not password:
        creds = get_credentials()
        if not creds:
            linkedin.goto_login()
            return False
        email, password = creds

    # Check if already logged in via saved session
    if linkedin.is_logged_in():
        return True

    success = linkedin.login(email, password)
    if success:
        browser.save_session()
    elif not _on_linkedin(page):
        # Only when we ended up nowhere. A failed login often lands on a 2FA or
        # security checkpoint, and navigating back to /login would throw that
        # challenge away — which is the page the human actually needs.
        linkedin.goto_login()
    return success


def _on_linkedin(page) -> bool:
    try:
        return "linkedin.com" in (page.url or "")
    except Exception:
        return False


def setup_credentials(email: str, password: str) -> None:
    """Store credentials securely in system keyring."""
    from linkedin.automation.credentials import store_credentials

    store_credentials(email, password)
