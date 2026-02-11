"""Login action for LinkedIn."""

from linkedin.automation.browser import BrowserManager
from linkedin.automation.credentials import get_credentials, store_credentials
from linkedin.automation.linkedin_page import LinkedInPage


def login_action(browser: BrowserManager, email: str | None = None, password: str | None = None) -> bool:
    """Log in to LinkedIn using stored or provided credentials.

    Returns True if login successful.
    """
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
    store_credentials(email, password)
