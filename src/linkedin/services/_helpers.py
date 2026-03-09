"""Shared helpers for service layer."""

from linkedin.data.repository import ProfileRepo
from linkedin.types import ProfileDict

PROFILE_REQUIRED_ERROR = "Set up your profile first: linkedin profile setup"
AI_ERROR_PREFIX = "[AI generation failed:"


def get_profile_or_error(profile_repo: ProfileRepo) -> tuple[ProfileDict | None, str | None]:
    """Return (profile, None) or (None, error_message)."""
    profile = profile_repo.get()
    if not profile or not profile.get("name"):
        return None, PROFILE_REQUIRED_ERROR
    return profile, None


def get_ai_text_or_error(text: str) -> tuple[str | None, str | None]:
    """Return (text, None) or (None, normalized_error_message)."""
    if text.startswith(AI_ERROR_PREFIX):
        if text.startswith("[") and text.endswith("]"):
            return None, text[1:-1]
        return None, text
    return text, None
