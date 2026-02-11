"""Connection request actions."""

from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits


def send_connection(
    linkedin: LinkedInPage,
    profile_url: str,
    note: str = "",
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> bool:
    """Send a connection request to a single profile.

    Returns True if the request was sent successfully.
    """
    if safety and not safety.can_send_connection():
        return False

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_profile(profile_url)

    if dry_run:
        if safety:
            safety.record_connection()
        return True

    success = linkedin.send_connection_request(note=note)
    if success and safety:
        safety.record_connection()
    return success


def batch_connect(
    linkedin: LinkedInPage,
    profiles: list[dict],
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
    limit: int = 5,
) -> list[dict]:
    """Send connection requests to multiple profiles.

    Returns list of results: [{"profile": {...}, "success": bool}]
    """
    results = []
    for profile in profiles[:limit]:
        if safety and not safety.can_send_connection():
            break

        url = profile.get("linkedin_url", "")
        if not url:
            results.append({"profile": profile, "success": False, "reason": "no_url"})
            continue

        note = profile.get("connection_note", "")
        success = send_connection(
            linkedin, url, note=note, rate_limiter=rate_limiter, safety=safety, dry_run=dry_run
        )
        results.append({"profile": profile, "success": success})

    return results
