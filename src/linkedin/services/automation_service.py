"""Automation orchestration service.

Coordinates browser automation with CRM data and AI generation
to automate LinkedIn connection outreach.

Playwright-dependent modules are imported lazily so this module
can be imported and tested without playwright installed.
"""

from __future__ import annotations

from linkedin.ai.client import generate_with_ai
from linkedin.automation.config import AutomationConfig
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits
from linkedin.data.repository import CompanyRepo, ProfileRepo
from linkedin.services.contact_service import ContactService
from linkedin.types import ProfileDict


class AutomationService:
    """Orchestrates LinkedIn browser automation with CRM and AI."""

    def __init__(
        self,
        contact_service: ContactService,
        company_repo: CompanyRepo,
        profile_repo: ProfileRepo,
        config: AutomationConfig | None = None,
    ):
        self.contacts = contact_service
        self.companies = company_repo
        self.profiles = profile_repo
        self.config = config or AutomationConfig()

    def run_connect(
        self,
        limit: int = 20,
        dry_run: bool = False,
        extra_queries: list[str] | None = None,
    ) -> list[dict]:
        """Run the full connection automation pipeline.

        Returns list of result dicts:
            {"name", "company", "note", "success", "reason"}
        """
        from linkedin.automation.actions.login import login_action
        from linkedin.automation.browser import BrowserManager
        from linkedin.automation.linkedin_page import LinkedInPage

        safety = SafetyLimits()
        rate_limiter = RateLimiter(
            min_delay=self.config.min_delay_seconds,
            max_delay=self.config.max_delay_seconds,
        )

        with BrowserManager(self.config) as browser:
            # Step 1: Login
            if not login_action(browser):
                return [{"name": "", "company": "", "note": "", "success": False, "reason": "Login failed"}]

            linkedin = LinkedInPage(browser.page)

            # Step 2: Build search queries
            queries = self._build_search_queries()
            if extra_queries:
                for q in extra_queries:
                    queries.append({"query": q, "network": "", "priority": 4})

            # Step 3+4: Search and deduplicate
            candidates = self._search_and_collect(linkedin, queries, safety, rate_limiter)

            # Step 5: Connect to each candidate
            results = []
            profile = self.profiles.get()

            for person in candidates[:limit]:
                if not safety.can_send_connection():
                    break

                result = self._connect_to_person(
                    linkedin, person, profile, safety, rate_limiter, dry_run
                )
                results.append(result)

            return results

    def _build_search_queries(self) -> list[dict]:
        """Generate search queries from CRM data.

        Returns list of dicts: {"query": str, "network": str, "priority": int}
        Priority 1: Target companies
        Priority 2: 2nd-degree connections
        Priority 3: Broad industry search
        """
        profile = self.profiles.get()
        target_role = profile.get("target_role", "") if profile else ""
        if not target_role:
            return []

        queries = []

        # Priority 1: Search at each target company
        companies = self.companies.list_all()
        for company in companies:
            queries.append({
                "query": f"{target_role} at {company['name']}",
                "network": "",
                "priority": 1,
            })

        # Priority 2: 2nd-degree connections
        queries.append({
            "query": target_role,
            "network": "S",
            "priority": 2,
        })

        # Priority 3: Broad industry search
        industries = profile.get("industries", "") if profile else ""
        if industries:
            queries.append({
                "query": f"{target_role} {industries}",
                "network": "",
                "priority": 3,
            })

        return queries

    def _search_and_collect(self, linkedin, queries, safety, rate_limiter):
        """Execute searches and deduplicate against existing contacts."""
        from linkedin.automation.actions.search import search_people

        # Build set of known LinkedIn URLs for deduplication
        existing_contacts = self.contacts.list_contacts()
        known_urls = {c.get("linkedin_url", "").rstrip("/").lower() for c in existing_contacts if c.get("linkedin_url")}

        seen_urls: set[str] = set()
        candidates: list[dict] = []

        # Sort queries by priority
        sorted_queries = sorted(queries, key=lambda q: q["priority"])

        for q in sorted_queries:
            if not safety.can_search():
                break

            results = search_people(
                linkedin,
                query=q["query"],
                network=q.get("network", ""),
                rate_limiter=rate_limiter,
                safety=safety,
            )

            for person in results:
                url = person.get("url", "").rstrip("/").lower()
                if not url:
                    continue
                if url in known_urls or url in seen_urls:
                    continue
                seen_urls.add(url)
                candidates.append(person)

        return candidates

    def _generate_connection_note(self, profile: ProfileDict | None, person_info: dict) -> str:
        """Generate a personalized connection note using AI."""
        if not profile:
            return ""

        prompt = f"""Write a LinkedIn connection request message (max 300 characters) from me to this person.

MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Current Role: {profile.get('headline', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}
- What Makes Me Unique: {profile.get('unique_value', 'N/A')}

THEIR PROFILE:
- Name: {person_info.get('name', 'Unknown')}
- Headline: {person_info.get('headline', 'N/A')}
- Location: {person_info.get('location', 'N/A')}

Write a warm, personalized connection request that:
1. Shows I've looked at their profile
2. Mentions something specific about their headline or role
3. Briefly explains why connecting would be mutually valuable
4. Is under 300 characters (LinkedIn limit)
5. Sounds natural, not salesy

Just write the message, no explanations."""

        return generate_with_ai(prompt, max_tokens=200)

    def _connect_to_person(self, linkedin, person, profile, safety, rate_limiter, dry_run):
        """Connect to a single person: scrape, add to CRM, generate note, send request."""
        from linkedin.automation.actions.connect import send_connection

        name = person.get("name", "Unknown")
        url = person.get("url", "")
        headline = person.get("headline", "")

        # Visit profile and scrape additional info
        if rate_limiter:
            rate_limiter.wait()

        linkedin.goto_profile(url)
        if safety:
            safety.record_profile_view()

        info = linkedin.get_profile_info()
        name = info.get("name", name)
        headline = info.get("headline", headline)
        location = info.get("location", "")
        company = self._extract_company(headline)

        # Add to CRM
        contact_result = self.contacts.add_contact(
            name=name,
            title=headline,
            company=company,
            linkedin=url,
            notes=f"Found via automation search. Location: {location}",
            source="automation",
        )

        # If add_contact returned an error string, skip
        if isinstance(contact_result, str):
            return {
                "name": name,
                "company": company,
                "note": "",
                "success": False,
                "reason": contact_result,
            }

        contact_id = contact_result["id"]

        # Generate personalized note
        note = self._generate_connection_note(profile, {
            "name": name,
            "headline": headline,
            "location": location,
        })

        # Send connection request
        success = send_connection(
            linkedin,
            profile_url=url,
            note=note,
            rate_limiter=rate_limiter,
            safety=safety,
            dry_run=dry_run,
        )

        # Update CRM status
        if success:
            self.contacts.update_contact(contact_id, status="connection_sent")

        return {
            "name": name,
            "company": company,
            "note": note,
            "success": success,
            "reason": "sent" if success else "connection_request_failed",
        }

    @staticmethod
    def _extract_company(headline: str) -> str:
        """Extract company name from a headline like 'Engineer at Google'."""
        if " at " in headline:
            return headline.split(" at ", 1)[1].strip()
        if " @ " in headline:
            return headline.split(" @ ", 1)[1].strip()
        return ""

    def run_engage(
        self,
        limit: int = 10,
        comment_count: int = 5,
        dry_run: bool = False,
    ) -> list[dict]:
        """Run feed engagement pipeline: like posts and leave AI comments.

        Returns list of result dicts:
            {"author", "content_preview", "liked", "commented", "comment_text"}
        """
        from linkedin.automation.actions.engage import comment_on_post, like_post
        from linkedin.automation.actions.login import login_action
        from linkedin.automation.browser import BrowserManager
        from linkedin.automation.linkedin_page import LinkedInPage

        safety = SafetyLimits()
        rate_limiter = RateLimiter(
            min_delay=self.config.min_delay_seconds,
            max_delay=self.config.max_delay_seconds,
        )

        with BrowserManager(self.config) as browser:
            if not login_action(browser):
                return [{"author": "", "content_preview": "", "liked": False, "commented": False, "comment_text": "", "reason": "Login failed"}]

            linkedin = LinkedInPage(browser.page)

            # Browse feed and collect posts
            posts = linkedin.get_feed_posts(max_posts=limit)
            if not posts:
                return []

            profile = self.profiles.get()
            comments_left = comment_count
            results = []

            for post in posts:
                if not safety.can_like():
                    break

                # Like the post
                liked = like_post(
                    linkedin,
                    post["element_index"],
                    rate_limiter=rate_limiter,
                    safety=safety,
                    dry_run=dry_run,
                )

                # Comment if budget remains and post has text content
                commented = False
                comment_text = ""
                if comments_left > 0 and post.get("content") and safety.can_comment():
                    comment_text = self._generate_feed_comment(profile, post)
                    if comment_text:
                        commented = comment_on_post(
                            linkedin,
                            post["element_index"],
                            comment_text,
                            rate_limiter=rate_limiter,
                            safety=safety,
                            dry_run=dry_run,
                        )
                        if commented:
                            comments_left -= 1

                content = post.get("content", "")
                results.append({
                    "author": post.get("author", ""),
                    "content_preview": (content[:47] + "...") if len(content) > 50 else content,
                    "liked": liked,
                    "commented": commented,
                    "comment_text": comment_text,
                })

            return results

    def _generate_feed_comment(self, profile: ProfileDict | None, post: dict) -> str:
        """Generate an AI-personalized comment for a feed post."""
        my_context = ""
        if profile:
            my_context = f"""MY PROFILE:
- Name: {profile.get('name', 'N/A')}
- Headline: {profile.get('headline', 'N/A')}
- Target Role: {profile.get('target_role', 'N/A')}
- Key Skills: {profile.get('skills', 'N/A')}
"""

        prompt = f"""Write a LinkedIn comment on this post.

{my_context}
POST AUTHOR: {post.get('author', 'Unknown')}
AUTHOR HEADLINE: {post.get('headline', 'N/A')}
POST CONTENT: {post.get('content', '')}

Write a comment that:
1. Is 1-3 sentences, specific to the post content
2. Adds value — share an insight, ask a thoughtful question, or relate a brief experience
3. Sounds natural and conversational, not generic or salesy
4. Is under 200 characters preferred

Just write the comment, no explanations."""

        try:
            return generate_with_ai(prompt, max_tokens=150)
        except Exception:
            return ""

    def login(self, email: str | None = None, password: str | None = None) -> bool:
        """Login to LinkedIn and save session.

        If email/password provided, saves credentials first.
        Returns True if login successful.
        """
        from linkedin.automation.actions.login import login_action, setup_credentials
        from linkedin.automation.browser import BrowserManager

        if email and password:
            setup_credentials(email, password)

        with BrowserManager(self.config) as browser:
            return login_action(browser, email, password)

    def get_status(self) -> dict:
        """Return current safety limits summary."""
        safety = SafetyLimits()
        return safety.summary()
