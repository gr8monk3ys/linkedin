"""LinkedIn page object model using Playwright locators."""

import time

from playwright.sync_api import Error as PlaywrightError, Page, TimeoutError as PlaywrightTimeoutError, expect


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
        except (PlaywrightTimeoutError, PlaywrightError):
            return False

    def is_logged_in(self) -> bool:
        """Check if currently logged in."""
        try:
            self.page.goto(f"{self.LINKEDIN_URL}/feed/")
            return "/login" not in self.page.url
        except (PlaywrightTimeoutError, PlaywrightError):
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
        except (PlaywrightTimeoutError, PlaywrightError):
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
        except (PlaywrightTimeoutError, PlaywrightError):
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
        except (PlaywrightTimeoutError, PlaywrightError):
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
                    entry["url"] = link.get_attribute("href") or ""

                if entry.get("name"):
                    results.append(entry)
        except (PlaywrightTimeoutError, PlaywrightError):
            pass
        return results

    # -------------------------------------------------------------------------
    # Feed Engagement
    # -------------------------------------------------------------------------

    def get_feed_posts(self, max_posts: int = 10) -> list[dict]:
        """Scroll feed and collect post data.

        Returns list of dicts: {"author", "headline", "content", "element_index"}
        """
        posts: list[dict] = []
        seen_authors: set[str] = set()

        try:
            self.goto_feed()
            self.page.wait_for_load_state("networkidle", timeout=10000)

            scroll_attempts = 0
            max_scrolls = max_posts * 2  # Allow enough scrolling to find posts

            while len(posts) < max_posts and scroll_attempts < max_scrolls:
                cards = self.page.locator("div.feed-shared-update-v2")
                count = cards.count()

                for i in range(count):
                    if len(posts) >= max_posts:
                        break

                    card = cards.nth(i)
                    entry: dict[str, str | int] = {"element_index": i}

                    # Extract author name
                    author_el = card.locator(".update-components-actor__name span[aria-hidden='true']").first
                    if author_el.count() > 0:
                        entry["author"] = author_el.text_content().strip()
                    else:
                        entry["author"] = ""

                    # Skip duplicates from re-scanning after scroll
                    author_key = f"{entry['author']}_{i}"
                    if author_key in seen_authors:
                        continue
                    seen_authors.add(author_key)

                    # Extract headline
                    headline_el = card.locator(".update-components-actor__description span[aria-hidden='true']").first
                    if headline_el.count() > 0:
                        entry["headline"] = headline_el.text_content().strip()
                    else:
                        entry["headline"] = ""

                    # Extract post content
                    content_el = card.locator(".feed-shared-update-v2__description, .update-components-text").first
                    if content_el.count() > 0:
                        text = content_el.text_content().strip()
                        entry["content"] = text[:500]
                    else:
                        entry["content"] = ""

                    posts.append(entry)

                # Scroll down to load more posts
                self.page.evaluate("window.scrollBy(0, 800)")
                time.sleep(1)
                scroll_attempts += 1

        except (PlaywrightTimeoutError, PlaywrightError):
            pass

        return posts

    def like_post(self, post_index: int) -> bool:
        """Like a post by its index in the feed.

        Skips if already liked. Returns True if liked successfully.
        """
        try:
            cards = self.page.locator("div.feed-shared-update-v2")
            if post_index >= cards.count():
                return False

            card = cards.nth(post_index)
            like_btn = card.get_by_role("button", name="Like")

            if like_btn.count() == 0:
                return False

            # Check if already liked
            if like_btn.first.get_attribute("aria-pressed") == "true":
                return False

            like_btn.first.click()
            return True
        except (PlaywrightTimeoutError, PlaywrightError):
            return False

    def comment_on_post(self, post_index: int, comment_text: str) -> bool:
        """Post a comment on a feed post by index.

        Returns True if comment was posted successfully.
        """
        try:
            cards = self.page.locator("div.feed-shared-update-v2")
            if post_index >= cards.count():
                return False

            card = cards.nth(post_index)

            # Click Comment button to open comment box
            comment_btn = card.get_by_role("button", name="Comment")
            if comment_btn.count() == 0:
                return False
            comment_btn.first.click()

            # Fill the comment textbox
            textbox = card.get_by_role("textbox", name="Add a comment")
            textbox.wait_for(timeout=5000)
            textbox.fill(comment_text)

            # Submit via Post button
            post_btn = card.get_by_role("button", name="Post")
            if post_btn.count() > 0:
                post_btn.first.click()
            else:
                textbox.press("Control+Enter")

            return True
        except (PlaywrightTimeoutError, PlaywrightError):
            return False
