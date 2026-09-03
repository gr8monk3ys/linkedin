"""Search LinkedIn jobs and feed the postings the planner scores.

Read-only. `market_service` has had posting import and profile matching since
the beginning and no way to get a posting in, which is why the daily plan said
"No postings above threshold" every morning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits
from linkedin.services.market_service import MarketService

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def search_jobs(
    linkedin: LinkedInPage,
    query: str,
    location: str = "",
    limit: int = 25,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
) -> list[dict]:
    """Run a LinkedIn job search and return raw result dicts. Writes nothing."""
    if safety and not safety.can_search():
        return []

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_job_search(query, location=location)

    if safety:
        safety.record_search()

    return linkedin.get_job_results(limit=limit)


def import_job_results(results: list[dict], market: MarketService) -> tuple[list[dict], int]:
    """Persist job results as scored postings. Returns (added, skipped_count).

    Deduped on URL, falling back to (company, title) for rows LinkedIn rendered
    without a link — a job search re-run daily otherwise stacks the same posting
    over and over and drowns the plan's opportunity section.
    """
    existing = market.list_postings(limit=10_000)
    seen_urls = {p.get("url", "").split("?")[0] for p in existing if p.get("url")}
    seen_roles = {
        (p.get("company", "").lower(), p.get("title", "").lower()) for p in existing
    }

    added: list[dict] = []
    skipped = 0

    for result in results:
        title = (result.get("title") or "").strip()
        company = (result.get("company") or "").strip()
        if not title:
            skipped += 1
            continue

        url = (result.get("url") or "").split("?")[0]
        role_key = (company.lower(), title.lower())
        if (url and url in seen_urls) or (not url and role_key in seen_roles):
            skipped += 1
            continue

        notes = "Easy Apply" if result.get("easy_apply") else ""
        posting = market.add_posting({
            "title": title,
            "company": company,
            "location": result.get("location", ""),
            "url": url,
            "source": "linkedin_jobs",
            "posted_date": result.get("posted", ""),
            "notes": notes,
        })
        added.append(posting)
        if url:
            seen_urls.add(url)
        seen_roles.add(role_key)

    return added, skipped
