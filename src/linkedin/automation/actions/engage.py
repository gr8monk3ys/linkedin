"""Feed engagement actions — like and comment on posts."""

from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits


def like_post(
    linkedin: LinkedInPage,
    post_index: int,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> bool:
    """Like a single feed post by index.

    Returns True if the post was liked successfully.
    """
    if safety and not safety.can_like():
        return False

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        if safety:
            safety.record_like()
        return True

    success = linkedin.like_post(post_index)
    if success and safety:
        safety.record_like()
    return success


def comment_on_post(
    linkedin: LinkedInPage,
    post_index: int,
    comment_text: str,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> bool:
    """Post a comment on a feed post by index.

    Returns True if the comment was posted successfully.
    """
    if safety and not safety.can_comment():
        return False

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        if safety:
            safety.record_comment()
        return True

    success = linkedin.comment_on_post(post_index, comment_text)
    if success and safety:
        safety.record_comment()
    return success
