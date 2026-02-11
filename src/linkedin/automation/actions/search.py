"""Search actions."""

from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits


def search_people(
    linkedin: LinkedInPage,
    query: str,
    network: str = "",
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
) -> list[dict[str, str]]:
    """Search for people on LinkedIn.

    Args:
        query: Search keywords
        network: Network filter - "F" (1st), "S" (2nd), "O" (3rd+)
        rate_limiter: Optional rate limiter
        safety: Optional safety limits

    Returns list of search results with name, headline, url.
    """
    if safety and not safety.can_search():
        return []

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_search(query, network=network)

    if safety:
        safety.record_search()

    return linkedin.get_search_results()
