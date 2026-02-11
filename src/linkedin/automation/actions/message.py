"""Messaging actions."""

from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits


def send_message(
    linkedin: LinkedInPage,
    profile_url: str,
    message: str,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> bool:
    """Send a message to a connected profile.

    Returns True if the message was sent successfully.
    """
    if safety and not safety.can_send_message():
        return False

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_profile(profile_url)

    if dry_run:
        if safety:
            safety.record_message()
        return True

    success = linkedin.send_message(message)
    if success and safety:
        safety.record_message()
    return success
