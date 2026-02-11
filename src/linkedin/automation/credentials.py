"""Secure credential storage using system keyring."""

import keyring

SERVICE_NAME = "linkedin-cli"

CREDENTIAL_KEYS = ("email", "password")


def store_credentials(email: str, password: str) -> None:
    """Store LinkedIn credentials in the system keyring."""
    keyring.set_password(SERVICE_NAME, "email", email)
    keyring.set_password(SERVICE_NAME, "password", password)


def get_credentials() -> tuple[str, str] | None:
    """Retrieve LinkedIn credentials from the system keyring.

    Returns (email, password) tuple or None if not stored.
    """
    email = keyring.get_password(SERVICE_NAME, "email")
    password = keyring.get_password(SERVICE_NAME, "password")
    if email and password:
        return email, password
    return None


def delete_credentials() -> None:
    """Remove stored credentials from the system keyring."""
    for key in CREDENTIAL_KEYS:
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass


def has_credentials() -> bool:
    """Check if credentials are stored."""
    return get_credentials() is not None
