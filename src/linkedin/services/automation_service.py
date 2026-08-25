"""Feed engagement service — like posts and leave AI-personalized comments.

Salvaged from the ci-web-smoke-hardening branch (PR #10) and adapted to the
current automation stack: the service operates on an already-open
LinkedInPage session (the CLI owns browser lifecycle and login) and uses
the shared SafetyLimits budgets for reactions and comments.

Import-safe without Playwright: browser types are only type hints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from linkedin.ai.client import AIClientError, generate_with_ai
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits
from linkedin.data.repository import ProfileRepo
from linkedin.types import ProfileDict

if TYPE_CHECKING:
    from linkedin.automation.linkedin_page import LinkedInPage


class AutomationService:
    """Business logic for feed engagement runs."""

    def __init__(self, profile_repo: ProfileRepo):
        self.profiles = profile_repo

    def engage_feed(
        self,
        linkedin: LinkedInPage,
        limit: int = 10,
        comment_count: int = 0,
        safety: SafetyLimits | None = None,
        rate_limiter: RateLimiter | None = None,
        dry_run: bool = False,
    ) -> list[dict]:
        """Browse the feed, like up to `limit` posts, AI-comment on up to `comment_count`.

        Returns one result dict per post seen:
            {"author", "content_preview", "liked", "commented", "comment_text"}
        """
        from linkedin.automation.actions.engage import comment_on_post, like_post_by_index

        posts = linkedin.get_feed_posts(max_posts=limit)
        if not posts:
            return []

        profile = self.profiles.get()
        comments_left = comment_count
        results = []

        for post in posts:
            if safety and not safety.can_react():
                break

            liked = like_post_by_index(
                linkedin,
                post["element_index"],
                rate_limiter=rate_limiter,
                safety=safety,
                dry_run=dry_run,
            )

            commented = False
            comment_text = ""
            can_comment = safety.can_comment() if safety else True
            if comments_left > 0 and post.get("content") and can_comment:
                comment_text = self.generate_feed_comment(profile, post)
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
            results.append(
                {
                    "author": post.get("author", ""),
                    "content_preview": (content[:47] + "...") if len(content) > 50 else content,
                    "liked": liked,
                    "commented": commented,
                    "comment_text": comment_text,
                }
            )

        return results

    def generate_feed_comment(self, profile: ProfileDict | None, post: dict) -> str:
        """Generate an AI-personalized comment for a feed post. Empty string on failure."""
        my_context = ""
        if profile:
            my_context = f"""MY PROFILE:
- Name: {profile.get("name", "N/A")}
- Headline: {profile.get("headline", "N/A")}
- Target Role: {profile.get("target_role", "N/A")}
- Key Skills: {profile.get("skills", "N/A")}
"""

        prompt = f"""Write a LinkedIn comment on this post.

{my_context}
POST AUTHOR: {post.get("author", "Unknown")}
AUTHOR HEADLINE: {post.get("headline", "N/A")}
POST CONTENT: {post.get("content", "")}

Write a comment that:
1. Is 1-3 sentences, specific to the post content
2. Adds value — share an insight, ask a thoughtful question, or relate a brief experience
3. Sounds natural and conversational, not generic or salesy
4. Is under 200 characters preferred

Just write the comment, no explanations."""

        try:
            return generate_with_ai(prompt, max_tokens=150).strip()
        except AIClientError:
            return ""
