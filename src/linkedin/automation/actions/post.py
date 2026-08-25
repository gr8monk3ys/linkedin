"""Publishing actions — post content to the LinkedIn feed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def publish_post(
    linkedin: LinkedInPage,
    text: str,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Publish a text post. Returns (success, reason)."""
    if not text.strip():
        return False, "empty_post"

    if safety and not safety.can_post():
        return False, "daily_post_limit_reached"

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        if safety:
            safety.record_post()
        return True, "dry_run"

    success = linkedin.create_post(text)
    if success and safety:
        safety.record_post()
    return success, "posted" if success else "post_failed"
