"""Scraping actions — import contacts from LinkedIn search results."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits
from linkedin.data.repository import ContactRepo
from linkedin.services.contact_service import cadence_follow_up_date
from linkedin.types import ContactDict

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


def search_and_collect(
    linkedin: LinkedInPage,
    query: str,
    limit: int = 20,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
) -> list[dict[str, str]]:
    """Run a LinkedIn people search and return raw result dicts.

    Returns list of {name, headline, linkedin_url}.
    Does NOT write to any repo — call import_search_results to persist.
    """
    if safety and not safety.can_search():
        return []

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_search(query)

    if safety:
        safety.record_search()

    results = linkedin.get_search_results()
    return results[:limit]


def import_search_results(
    results: list[dict[str, str]],
    contact_repo: ContactRepo,
    skip_existing_urls: bool = True,
) -> tuple[list[ContactDict], list[str]]:
    """Persist search results into the contact repo.

    Returns (added_contacts, skipped_urls).
    Skips contacts whose linkedin_url already exists in repo if skip_existing_urls=True.
    """
    existing_urls = set()
    if skip_existing_urls:
        existing_urls = {c.get("linkedin_url", "") for c in contact_repo.list_all()}

    added: list[ContactDict] = []
    skipped: list[str] = []

    for result in results:
        url = result.get("linkedin_url", "")
        if skip_existing_urls and url and url in existing_urls:
            skipped.append(url)
            continue

        headline = result.get("headline", "")
        title, company = _parse_headline(headline)

        contact: ContactDict = {
            "id": contact_repo.next_id(),
            "name": result.get("name", "Unknown"),
            "title": title,
            "company": company,
            "linkedin_url": url,
            "notes": f"Imported from search. Headline: {headline}",
            "status": "not_contacted",
            "follow_up_date": cadence_follow_up_date("not_contacted"),
            "source": "linkedin_search",
            "created_at": datetime.now().isoformat(),
            "activities": [],
        }
        contact_repo.add(contact)
        added.append(contact)

    return added, skipped


def scrape_and_import_profile(
    linkedin: LinkedInPage,
    url: str,
    contact_repo: ContactRepo,
    rate_limiter: RateLimiter | None = None,
) -> ContactDict | None:
    """Scrape a single LinkedIn profile and add/update in contact repo.

    Returns the created/updated ContactDict, or None on failure.
    """
    if rate_limiter:
        rate_limiter.wait()

    try:
        linkedin.goto_profile(url)
        data = linkedin.scrape_profile()
    except Exception:
        return None

    if not data.get("name"):
        return None

    existing = next(
        (c for c in contact_repo.list_all() if c.get("linkedin_url") == url),
        None,
    )

    title, company = _parse_headline(data.get("headline", ""))

    if existing:
        existing["title"] = title or existing.get("title", "")
        existing["company"] = company or existing.get("company", "")
        contact_repo.update(existing)
        return existing

    contact: ContactDict = {
        "id": contact_repo.next_id(),
        "name": data["name"],
        "title": title,
        "company": company,
        "linkedin_url": url,
        "notes": data.get("about", ""),
        "status": "not_contacted",
        "follow_up_date": cadence_follow_up_date("not_contacted"),
        "source": "linkedin_scrape",
        "created_at": datetime.now().isoformat(),
        "activities": [],
    }
    contact_repo.add(contact)
    return contact


def _parse_headline(headline: str) -> tuple[str, str]:
    """Parse 'Title at Company' into (title, company). Best-effort."""
    if " at " in headline:
        parts = headline.split(" at ", 1)
        return parts[0].strip(), parts[1].strip()
    if " @ " in headline:
        parts = headline.split(" @ ", 1)
        return parts[0].strip(), parts[1].strip()
    return headline.strip(), ""
