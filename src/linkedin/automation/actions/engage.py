"""Engagement actions — like posts from target contacts or the feed."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def like_contact_posts(
    linkedin: LinkedInPage,
    profile_url: str,
    count: int = 2,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> int:
    """Like up to `count` recent posts by a contact. Returns number liked."""
    if not profile_url:
        return 0

    count = _clamp_to_budget(count, safety)
    if count <= 0:
        return 0

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        _record(count, safety)
        return count

    linkedin.goto_recent_activity(profile_url)
    liked = linkedin.like_visible_posts(count)
    _record(liked, safety)
    return liked


def like_feed_posts(
    linkedin: LinkedInPage,
    count: int = 3,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> int:
    """Like up to `count` posts on the home feed. Returns number liked."""
    count = _clamp_to_budget(count, safety)
    if count <= 0:
        return 0

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        _record(count, safety)
        return count

    linkedin.goto_feed()
    liked = linkedin.like_visible_posts(count)
    _record(liked, safety)
    return liked


def _clamp_to_budget(count: int, safety: SafetyLimits | None) -> int:
    if safety is None:
        return count
    if not safety.can_react():
        return 0
    return min(count, safety.remaining_reactions())


def _record(n: int, safety: SafetyLimits | None) -> None:
    if safety:
        for _ in range(n):
            safety.record_reaction()
