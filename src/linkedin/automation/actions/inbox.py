"""Read LinkedIn's inbound surfaces: message threads and sent invitations.

Read-only. This action navigates and returns raw dicts; deciding what any of it
means about a contact is `services/inbox_service.py`, deliberately kept out of
the browser layer so the logic that can corrupt the CRM is testable without a
page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def read_inbox(
    linkedin: LinkedInPage,
    thread_limit: int = 25,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
) -> dict:
    """Return {"threads": [...], "pending_invitations": [...] | None}.

    `pending_invitations` is None when the list could not be read — including
    when the budget stopped us before we looked. The caller infers acceptance
    from an invitation's absence, so "we did not look" and "nothing is pending"
    must never collapse into the same value.
    """
    if safety and not safety.can_search():
        return {"threads": [], "pending_invitations": None}

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_messaging()
    threads = linkedin.get_message_threads(limit=thread_limit)

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_sent_invitations()
    pending = linkedin.get_pending_sent_invitations()

    if safety:
        safety.record_search()

    return {"threads": threads, "pending_invitations": pending}
