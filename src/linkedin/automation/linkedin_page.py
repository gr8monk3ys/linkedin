"""LinkedIn page object model using Playwright locators."""

from playwright.sync_api import Page, expect


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
                    entry["url"] = link.get_attribute("href") or ""

                if entry.get("name"):
                    results.append(entry)
        except Exception:
            pass
        return results
