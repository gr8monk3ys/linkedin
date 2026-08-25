"""Easy Apply actions — apply to a LinkedIn job posting with a resume PDF."""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def apply_to_job(
    linkedin: LinkedInPage,
    job_url: str,
    resume_path: str = "",
    submit: bool = False,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the Easy Apply flow for a job URL.

    Only counts against the daily cap when an application is actually
    submitted. Returns {"status": ..., "detail": ...} (see
    LinkedInPage.easy_apply for statuses).
    """
    if not job_url:
        return {"status": "error", "detail": "Application has no job URL"}

    if submit and safety and not safety.can_easy_apply():
        return {"status": "error", "detail": "daily_easy_apply_limit_reached"}

    if rate_limiter:
        rate_limiter.wait()

    if dry_run:
        return {"status": "dry_run", "detail": f"Would Easy Apply to {job_url}"}

    linkedin.goto_profile(job_url)  # generic navigation; works for any URL
    result = linkedin.easy_apply(resume_path=resume_path, submit=submit)

    if result.get("status") == "submitted" and safety:
        safety.record_easy_apply()
    return result
