"""The automation package must import without Playwright or keyring.

CI installs only `--extra dev`. Any module that imports playwright/keyring at
module scope drops itself (and everything importing it) to 0% coverage — which
is how `linkedin_page.py`, the layer that actually talks to LinkedIn, went
untested. This test fails the moment that regresses.
"""

import importlib
import pkgutil
import sys
from unittest.mock import MagicMock, patch

import pytest

import linkedin.automation


def _automation_modules():
    return sorted(m.name for m in pkgutil.walk_packages(linkedin.automation.__path__, "linkedin.automation."))


@pytest.mark.parametrize("module_name", _automation_modules())
def test_module_imports_without_optional_extras(module_name):
    assert importlib.import_module(module_name)


def test_importing_the_package_does_not_pull_in_playwright():
    for name in _automation_modules():
        importlib.import_module(name)
    assert "playwright" not in sys.modules
    assert "keyring" not in sys.modules


class TestCredentials:
    """Keyring is imported lazily; these verify the wrapper still behaves."""

    def _keyring(self):
        fake = MagicMock()
        fake.errors.PasswordDeleteError = RuntimeError
        return fake

    def test_store_writes_both_fields(self):
        from linkedin.automation import credentials

        fake = self._keyring()
        with patch.dict(sys.modules, {"keyring": fake}):
            credentials.store_credentials("a@b.c", "pw")
        fake.set_password.assert_any_call("linkedin-cli", "email", "a@b.c")
        fake.set_password.assert_any_call("linkedin-cli", "password", "pw")

    def test_get_returns_the_pair(self):
        from linkedin.automation import credentials

        fake = self._keyring()
        fake.get_password.side_effect = ["a@b.c", "pw"]
        with patch.dict(sys.modules, {"keyring": fake}):
            assert credentials.get_credentials() == ("a@b.c", "pw")

    def test_get_returns_none_when_incomplete(self):
        from linkedin.automation import credentials

        fake = self._keyring()
        fake.get_password.side_effect = ["a@b.c", None]
        with patch.dict(sys.modules, {"keyring": fake}):
            assert credentials.get_credentials() is None

    def test_delete_tolerates_missing_entries(self):
        from linkedin.automation import credentials

        fake = self._keyring()
        fake.delete_password.side_effect = RuntimeError("not found")
        with patch.dict(sys.modules, {"keyring": fake}):
            credentials.delete_credentials()  # must not raise

    def test_has_credentials(self):
        from linkedin.automation import credentials

        fake = self._keyring()
        fake.get_password.side_effect = ["a@b.c", "pw"]
        with patch.dict(sys.modules, {"keyring": fake}):
            assert credentials.has_credentials() is True


class TestLogin:
    """`session._login`: saved session first, credentials second, and on every
    failure the browser is left on a page a human can use."""

    def _page(self, logged_in=False, login_ok=False, url="about:blank"):
        page = MagicMock()
        page.is_logged_in.return_value = logged_in
        page.login.return_value = login_ok
        page.page.url = url
        return page

    def test_returns_false_without_stored_credentials_and_lands_on_login(self):
        """Returning False must not leave the browser on about:blank: the CLI's
        fallback is 'finish the login yourself in the window'."""
        from linkedin.automation.session import _login

        page = self._page()
        with patch("linkedin.automation.credentials.get_credentials", return_value=None):
            assert _login(MagicMock(), page) is False
        page.goto_login.assert_called_once()

    def test_a_valid_saved_session_needs_no_stored_credentials(self):
        """Checking credentials first threw away a working session whenever
        `automate setup` had never been run — every hand-established session."""
        from linkedin.automation.session import _login

        page = self._page(logged_in=True)
        browser = MagicMock()
        with patch("linkedin.automation.credentials.get_credentials", side_effect=AssertionError("must not be asked")):
            assert _login(browser, page) is True
        page.login.assert_not_called()
        browser.save_session.assert_not_called()

    def test_successful_login_saves_the_session(self):
        from linkedin.automation.session import _login

        page = self._page(login_ok=True)
        browser = MagicMock()
        with patch("linkedin.automation.credentials.get_credentials", return_value=("a@b.c", "pw")):
            assert _login(browser, page) is True
        page.login.assert_called_once_with("a@b.c", "pw")
        browser.save_session.assert_called_once()

    def test_failed_credentials_leave_the_login_page_open(self):
        from linkedin.automation.session import _login

        page = self._page(login_ok=False, url="about:blank")
        browser = MagicMock()
        with patch("linkedin.automation.credentials.get_credentials", return_value=("a@b.c", "pw")):
            assert _login(browser, page) is False
        browser.save_session.assert_not_called()
        page.goto_login.assert_called_once()

    def test_a_security_checkpoint_is_not_navigated_away_from(self):
        """A failed login often means 2FA, and that challenge is the page the
        human needs. Reloading /login would discard it."""
        from linkedin.automation.session import _login

        page = self._page(login_ok=False, url="https://www.linkedin.com/checkpoint/challenge/")
        with patch("linkedin.automation.credentials.get_credentials", return_value=("a@b.c", "pw")):
            assert _login(MagicMock(), page) is False
        page.goto_login.assert_not_called()
