"""Profile sync actions — push local profile/optimizer output to LinkedIn."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def sync_profile(
    linkedin: LinkedInPage,
    headline: str = "",
    about: str = "",
    rate_limiter: RateLimiter | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    """Update own LinkedIn headline and/or about section.

    Returns {"headline": status, "about": status} for the fields requested,
    where status is "updated", "failed", "dry_run", or "skipped".
    """
    results: dict[str, str] = {}

    if not headline and not about:
        return results

    if rate_limiter:
        rate_limiter.wait()

    if headline:
        if dry_run:
            results["headline"] = "dry_run"
        else:
            results["headline"] = "updated" if linkedin.update_headline(headline) else "failed"
    else:
        results["headline"] = "skipped"

    if about:
        if dry_run:
            results["about"] = "dry_run"
        else:
            results["about"] = "updated" if linkedin.update_about(about) else "failed"
    else:
        results["about"] = "skipped"

    return results
