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

    Returns True if login successful.
    """
    from linkedin.automation.credentials import get_credentials

    if not email or not password:
        creds = get_credentials()
        if not creds:
            return False
        email, password = creds

    page = browser.page
    if not page:
        return False

    linkedin = LinkedInPage(page)

    # Check if already logged in via saved session
    if linkedin.is_logged_in():
        return True

    success = linkedin.login(email, password)
    if success:
        browser.save_session()
    return success


def setup_credentials(email: str, password: str) -> None:
    """Store credentials securely in system keyring."""
    from linkedin.automation.credentials import store_credentials

    store_credentials(email, password)
