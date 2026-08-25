"""LinkedIn page object model using Playwright locators."""

import re

from playwright.sync_api import Page


class LinkedInPage:
    """Page object for LinkedIn interactions using accessible locators."""

    LINKEDIN_URL = "https://www.linkedin.com"
    LOGIN_URL = "https://www.linkedin.com/login"

    def __init__(self, page: Page):
        self.page = page

    # -------------------------------------------------------------------------
    # Navigation
    # -------------------------------------------------------------------------

    def goto_login(self) -> None:
        self.page.goto(self.LOGIN_URL)

    def goto_feed(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/feed/")

    def goto_my_network(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/mynetwork/")

    def goto_profile(self, linkedin_url: str) -> None:
        self.page.goto(linkedin_url)

    def goto_search(self, query: str, network: str = "") -> None:
        url = f"{self.LINKEDIN_URL}/search/results/people/?keywords={query}"
        if network:
            url += f"&network=%5B%22{network}%22%5D"
        self.page.goto(url)

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        """Log in to LinkedIn. Returns True if successful."""
        self.goto_login()
        self.page.get_by_label("Email or phone").fill(email)
        self.page.get_by_label("Password").fill(password)
        self.page.get_by_role("button", name="Sign in").click()

        # Wait for navigation to complete
        try:
            self.page.wait_for_url("**/feed/**", timeout=15000)
            return True
        except Exception:
            return False

    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        try:
            self.page.goto(f"{self.LINKEDIN_URL}/feed/")
            return "/login" not in self.page.url
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Connection Requests
    # -------------------------------------------------------------------------

    def send_connection_request(self, note: str = "") -> bool:
        """Send a connection request from a profile page.

        Assumes we're on a profile page.
        """
        try:
            connect_btn = self.page.get_by_role("button", name="Connect")
            if connect_btn.count() == 0:
                # Try "More" dropdown
                more_btn = self.page.get_by_role("button", name="More")
                if more_btn.count() > 0:
                    more_btn.first.click()
                    connect_option = self.page.get_by_role("menuitem", name="Connect")
                    if connect_option.count() == 0:
                        return False
                    connect_option.click()
                else:
                    return False
            else:
                connect_btn.first.click()

            if note:
                add_note_btn = self.page.get_by_role("button", name="Add a note")
                if add_note_btn.count() > 0:
                    add_note_btn.click()
                    self.page.get_by_role("textbox", name="Add a note").fill(note)

            send_btn = self.page.get_by_role("button", name="Send")
            if send_btn.count() > 0:
                send_btn.click()
                return True
            return False
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------

    def send_message(self, message: str) -> bool:
        """Send a message from a profile page.

        Assumes we're on a profile page of a connected user.
        """
        try:
            msg_btn = self.page.get_by_role("button", name="Message")
            if msg_btn.count() == 0:
                return False
            msg_btn.first.click()

            # Wait for message dialog
            msg_box = self.page.get_by_role("textbox", name="Write a message")
            msg_box.wait_for(timeout=5000)
            msg_box.fill(message)

            send_btn = self.page.get_by_role("button", name="Send")
            send_btn.click()
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Profile Info
    # -------------------------------------------------------------------------

    def get_profile_info(self) -> dict[str, str]:
        """Extract basic profile info from current profile page."""
        info = {}
        try:
            name_el = self.page.locator("h1").first
            if name_el.count() > 0:
                info["name"] = name_el.text_content().strip()

            headline_el = self.page.locator(".text-body-medium").first
            if headline_el.count() > 0:
                info["headline"] = headline_el.text_content().strip()

            location_el = self.page.locator(".text-body-small.inline").first
            if location_el.count() > 0:
                info["location"] = location_el.text_content().strip()
        except Exception:
            pass
        return info

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def get_search_results(self) -> list[dict[str, str]]:
        """Get search result entries from current search page."""
        results = []
        try:
            cards = self.page.locator(".reusable-search__result-container")
            for i in range(cards.count()):
                card = cards.nth(i)
                entry = {}
                name_link = card.locator("a.app-aware-link span[aria-hidden='true']").first
                if name_link.count() > 0:
                    entry["name"] = name_link.text_content().strip()

                headline = card.locator(".entity-result__primary-subtitle").first
                if headline.count() > 0:
                    entry["headline"] = headline.text_content().strip()

                link = card.locator("a.app-aware-link").first
                if link.count() > 0:
                    entry["linkedin_url"] = (link.get_attribute("href") or "").split("?")[0]

                if entry.get("name"):
                    results.append(entry)
        except Exception:
            pass
        return results

    # -------------------------------------------------------------------------
    # Posting
    # -------------------------------------------------------------------------

    def create_post(self, text: str) -> bool:
        """Publish a text post to the feed. Returns True on success."""
        try:
            self.goto_feed()
            start_btn = self.page.get_by_role("button", name=re.compile("Start a post", re.I))
            if start_btn.count() == 0:
                return False
            start_btn.first.click()

            editor = self.page.get_by_role("textbox", name=re.compile("Text editor", re.I))
            if editor.count() == 0:
                editor = self.page.locator("div.ql-editor[contenteditable='true']")
            if editor.count() == 0:
                return False
            editor.first.fill(text)

            post_btn = self.page.get_by_role("button", name=re.compile(r"^Post$", re.I))
            if post_btn.count() == 0:
                return False
            post_btn.first.click()
            self.page.wait_for_timeout(2000)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Reactions
    # -------------------------------------------------------------------------

    def goto_recent_activity(self, profile_url: str) -> None:
        base = profile_url.rstrip("/")
        self.page.goto(f"{base}/recent-activity/all/")

    def like_visible_posts(self, count: int = 1) -> int:
        """Like up to `count` visible, not-yet-liked posts on the current page.

        Works on the feed and on a profile's recent-activity page.
        Returns the number of posts actually liked.
        """
        liked = 0
        try:
            like_btns = self.page.get_by_role("button", name=re.compile(r"^React Like|^Like\b", re.I))
            for i in range(like_btns.count()):
                if liked >= count:
                    break
                btn = like_btns.nth(i)
                # aria-pressed=true means we already reacted — skip to avoid unliking
                if btn.get_attribute("aria-pressed") == "true":
                    continue
                btn.scroll_into_view_if_needed()
                btn.click()
                self.page.wait_for_timeout(800)
                liked += 1
        except Exception:
            pass
        return liked

    # -------------------------------------------------------------------------
    # Feed posts (index-addressed, for like + comment flows)
    # -------------------------------------------------------------------------

    FEED_CARD_SELECTOR = "div.feed-shared-update-v2"

    def get_feed_posts(self, max_posts: int = 10) -> list[dict]:
        """Scroll the feed and collect post data.

        Returns list of dicts: {"author", "headline", "content", "element_index"}.
        element_index addresses the card for like_post/comment_on_post.
        """
        posts: list[dict] = []
        seen: set[str] = set()

        try:
            self.goto_feed()
            self.page.wait_for_load_state("networkidle", timeout=10000)

            scroll_attempts = 0
            max_scrolls = max_posts * 2
            while len(posts) < max_posts and scroll_attempts < max_scrolls:
                cards = self.page.locator(self.FEED_CARD_SELECTOR)
                for i in range(cards.count()):
                    if len(posts) >= max_posts:
                        break
                    card = cards.nth(i)
                    entry: dict = {"element_index": i, "author": "", "headline": "", "content": ""}

                    author_el = card.locator(".update-components-actor__name span[aria-hidden='true']").first
                    if author_el.count() > 0:
                        entry["author"] = (author_el.text_content() or "").strip()

                    key = f"{entry['author']}_{i}"
                    if key in seen:
                        continue
                    seen.add(key)

                    headline_el = card.locator(".update-components-actor__description span[aria-hidden='true']").first
                    if headline_el.count() > 0:
                        entry["headline"] = (headline_el.text_content() or "").strip()

                    content_el = card.locator(".feed-shared-update-v2__description, .update-components-text").first
                    if content_el.count() > 0:
                        entry["content"] = (content_el.text_content() or "").strip()[:500]

                    posts.append(entry)

                self.page.evaluate("window.scrollBy(0, 800)")
                self.page.wait_for_timeout(1000)
                scroll_attempts += 1
        except Exception:
            pass
        return posts

    def like_post(self, post_index: int) -> bool:
        """Like a feed post by index. Skips already-liked posts. Returns True on success."""
        try:
            cards = self.page.locator(self.FEED_CARD_SELECTOR)
            if post_index >= cards.count():
                return False
            card = cards.nth(post_index)
            like_btn = card.get_by_role("button", name=re.compile(r"^React Like|^Like\b", re.I))
            if like_btn.count() == 0:
                return False
            if like_btn.first.get_attribute("aria-pressed") == "true":
                return False
            like_btn.first.click()
            return True
        except Exception:
            return False

    def comment_on_post(self, post_index: int, comment_text: str) -> bool:
        """Post a comment on a feed post by index. Returns True on success."""
        try:
            cards = self.page.locator(self.FEED_CARD_SELECTOR)
            if post_index >= cards.count():
                return False
            card = cards.nth(post_index)

            comment_btn = card.get_by_role("button", name=re.compile(r"^Comment\b", re.I))
            if comment_btn.count() == 0:
                return False
            comment_btn.first.click()

            textbox = card.get_by_role("textbox", name=re.compile("Add a comment", re.I))
            textbox.wait_for(timeout=5000)
            textbox.fill(comment_text)

            post_btn = card.get_by_role("button", name=re.compile(r"^Post\b", re.I))
            if post_btn.count() == 0:
                return False
            post_btn.first.click()
            self.page.wait_for_timeout(1000)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Profile editing (own profile)
    # -------------------------------------------------------------------------

    def goto_own_profile(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/in/me/")

    def update_headline(self, headline: str) -> bool:
        """Update own headline via the 'Edit intro' dialog. Returns True on success."""
        try:
            self.goto_own_profile()
            edit_btn = self.page.get_by_role("button", name=re.compile("Edit intro", re.I))
            if edit_btn.count() == 0:
                return False
            edit_btn.first.click()

            field = self.page.get_by_label(re.compile("Headline", re.I))
            if field.count() == 0:
                return False
            field.first.fill(headline)

            save_btn = self.page.get_by_role("button", name=re.compile(r"^Save$", re.I))
            if save_btn.count() == 0:
                return False
            save_btn.first.click()
            self.page.wait_for_timeout(2000)
            return True
        except Exception:
            return False

    def update_about(self, about: str) -> bool:
        """Update own About section. Returns True on success."""
        try:
            self.goto_own_profile()
            about_section = self.page.locator("#about")
            if about_section.count() == 0:
                return False
            edit_btn = self.page.get_by_role("button", name=re.compile("Edit about", re.I))
            if edit_btn.count() == 0:
                # Fallback: pencil button within the about section's parent block
                edit_btn = about_section.locator(
                    "xpath=ancestor::section//button[contains(@aria-label, 'about') or contains(@aria-label, 'About')]"
                )
            if edit_btn.count() == 0:
                return False
            edit_btn.first.click()

            field = self.page.get_by_role("textbox")
            if field.count() == 0:
                return False
            field.first.fill(about)

            save_btn = self.page.get_by_role("button", name=re.compile(r"^Save$", re.I))
            if save_btn.count() == 0:
                return False
            save_btn.first.click()
            self.page.wait_for_timeout(2000)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Easy Apply
    # -------------------------------------------------------------------------

    def easy_apply(self, resume_path: str = "", submit: bool = False, max_steps: int = 8) -> dict:
        """Attempt an Easy Apply flow on the current job page.

        Walks the modal via Next/Review, uploads `resume_path` when a file
        input appears, and only clicks 'Submit application' when submit=True —
        otherwise stops at the final step and reports 'ready_to_submit'.

        Returns {"status": ..., "detail": ...} where status is one of:
        submitted | ready_to_submit | no_easy_apply | needs_manual_input | error
        """
        try:
            apply_btn = self.page.get_by_role("button", name=re.compile("Easy Apply", re.I))
            if apply_btn.count() == 0:
                return {"status": "no_easy_apply", "detail": "No Easy Apply button on page"}
            apply_btn.first.click()
            self.page.wait_for_timeout(1500)

            for _ in range(max_steps):
                if resume_path:
                    file_input = self.page.locator("input[type='file']")
                    if file_input.count() > 0:
                        file_input.first.set_input_files(resume_path)
                        self.page.wait_for_timeout(1500)

                submit_btn = self.page.get_by_role("button", name=re.compile("Submit application", re.I))
                if submit_btn.count() > 0:
                    if not submit:
                        return {"status": "ready_to_submit", "detail": "Stopped before final submit (pass --submit)"}
                    submit_btn.first.click()
                    self.page.wait_for_timeout(2000)
                    return {"status": "submitted", "detail": "Application submitted"}

                # Required fields LinkedIn flags in red block progression
                errors = self.page.locator(".artdeco-inline-feedback--error")
                if errors.count() > 0:
                    return {
                        "status": "needs_manual_input",
                        "detail": "Form has required fields that need manual answers",
                    }

                next_btn = self.page.get_by_role("button", name=re.compile("Next|Review|Continue", re.I))
                if next_btn.count() == 0:
                    return {"status": "needs_manual_input", "detail": "Could not find a Next/Review button"}
                next_btn.first.click()
                self.page.wait_for_timeout(1500)

            return {"status": "needs_manual_input", "detail": f"Did not reach submit within {max_steps} steps"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    def scrape_profile(self) -> dict[str, str]:
        """Scrape basic profile info from the current profile page.

        Call goto_profile(url) first.
        Returns dict with name, headline, location, about.
        """
        data: dict[str, str] = {}
        try:
            name_el = self.page.locator("h1.text-heading-xlarge")
            if name_el.count():
                data["name"] = name_el.inner_text().strip()

            headline_el = self.page.locator(".text-body-medium.break-words")
            if headline_el.count():
                data["headline"] = headline_el.first.inner_text().strip()

            location_el = self.page.locator(".text-body-small.inline.t-black--light.break-words")
            if location_el.count():
                data["location"] = location_el.first.inner_text().strip()

            about_el = self.page.locator("#about ~ div .visually-hidden")
            if about_el.count():
                data["about"] = about_el.inner_text().strip()
        except Exception:
            pass
        return data
