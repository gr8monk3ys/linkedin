"""Secure credential storage using the system keyring.

Import-safe without keyring installed: it is imported inside each function, so
this module (and everything that reaches it) can be imported in CI, which
installs only `--extra dev`. Calling any of these without `--extra automation`
raises ImportError, which is the honest outcome.
"""

SERVICE_NAME = "linkedin-cli"

CREDENTIAL_KEYS = ("email", "password")


def store_credentials(email: str, password: str) -> None:
    """Store LinkedIn credentials in the system keyring."""
    import keyring

    keyring.set_password(SERVICE_NAME, "email", email)
    keyring.set_password(SERVICE_NAME, "password", password)


def get_credentials() -> tuple[str, str] | None:
    """Retrieve LinkedIn credentials from the system keyring.

    Returns (email, password) tuple or None if not stored.
    """
    import keyring

    email = keyring.get_password(SERVICE_NAME, "email")
    password = keyring.get_password(SERVICE_NAME, "password")
    if email and password:
        return email, password
    return None


def delete_credentials() -> None:
    """Remove stored credentials from the system keyring."""
    import keyring

    for key in CREDENTIAL_KEYS:
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass


def has_credentials() -> bool:
    """Check if credentials are stored."""
    return get_credentials() is not None
