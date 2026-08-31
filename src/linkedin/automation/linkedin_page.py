"""LinkedIn page object model using Playwright locators.

Import-safe without Playwright installed (`Page` is a type hint only), so the
selector logic can be tested in CI, which installs only `--extra dev`.

Every method here fails soft — a missing element returns 0/[]/False rather than
raising, because half of these elements are legitimately absent (no Connect
button on an existing connection). That makes a *selector breakage* look
identical to a quiet page, so the methods that cannot tell the difference record
the miss in `self.selector_misses` instead of staying silent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlencode

from linkedin.automation import selectors as sel

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


class LinkedInPage:
    """Page object for LinkedIn interactions using accessible locators."""

    LINKEDIN_URL = "https://www.linkedin.com"
    LOGIN_URL = "https://www.linkedin.com/login"

    def __init__(self, page: Page):
        self.page = page
        #: Names from `selectors.FRAGILE_SELECTORS` that matched nothing this
        #: session. Non-empty means "LinkedIn markup probably changed", not
        #: "there was nothing to do".
        self.selector_misses: list[str] = []

    def _record_miss(self, name: str) -> None:
        if name not in self.selector_misses:
            self.selector_misses.append(name)

    def _feed_cards(self) -> tuple[Locator, int]:
        """Locate the feed cards, recording a miss when none match.

        Every feed method goes through here so that adding one cannot silently
        opt out of health reporting — the omission would look like working code.
        """
        cards = self.page.locator(sel.FEED_CARD)
        count = cards.count()
        if count == 0:
            self._record_miss("feed_card")
        return cards, count

    def selector_health(self) -> dict:
        """Report which fragile selectors stopped matching during this session."""
        return {
            "healthy": not self.selector_misses,
            "misses": list(self.selector_misses),
            "selectors": {n: sel.FRAGILE_SELECTORS[n] for n in self.selector_misses if n in sel.FRAGILE_SELECTORS},
        }

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

    def goto_messaging(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/messaging/")

    def goto_sent_invitations(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/mynetwork/invitation-manager/sent/")

    def goto_job_search(self, keywords: str, location: str = "") -> None:
        params = {"keywords": keywords}
        if location:
            params["location"] = location
        self.page.goto(f"{self.LINKEDIN_URL}/jobs/search/?{urlencode(params)}")

    def goto_search(self, query: str, network: str = "") -> None:
        url = f"{self.LINKEDIN_URL}/search/results/people/?keywords={query}"
        if network:
            url += f"&network=%5B%22{network}%22%5D"
        self.page.goto(url)

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    def login(self, email: str, password: str) -> bool:
        """Log in to LinkedIn. Returns True if successful.

        Every locator here is narrowed to one element on purpose. LinkedIn
        renders duplicates of all three controls, and Playwright raises on an
        action against a multi-match locator — which this method used to swallow
        and report as a plain False.
        """
        self.goto_login()
        self._visible(sel.LOGIN_EMAIL_INPUT).fill(email)
        self._visible(sel.LOGIN_PASSWORD_INPUT).fill(password)
        self.page.get_by_role("button", name=sel.SIGN_IN_BUTTON, exact=True).last.click()

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
            connect_btn = self.page.get_by_role("button", name=sel.CONNECT_BUTTON)
            if connect_btn.count() == 0:
                # Try "More" dropdown
                more_btn = self.page.get_by_role("button", name=sel.MORE_BUTTON)
                if more_btn.count() > 0:
                    more_btn.first.click()
                    connect_option = self.page.get_by_role("menuitem", name=sel.CONNECT_MENU_ITEM)
                    if connect_option.count() == 0:
                        return False
                    connect_option.first.click()
                else:
                    return False
            else:
                connect_btn.first.click()

            if note:
                add_note_btn = self.page.get_by_role("button", name=sel.ADD_NOTE_BUTTON)
                if add_note_btn.count() > 0:
                    add_note_btn.first.click()
                    self.page.get_by_role("textbox", name=sel.ADD_NOTE_TEXTBOX).first.fill(note)

            send_btn = self.page.get_by_role("button", name=sel.SEND_BUTTON)
            if send_btn.count() > 0:
                send_btn.first.click()
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
            msg_btn = self.page.get_by_role("button", name=sel.MESSAGE_BUTTON)
            if msg_btn.count() == 0:
                return False
            msg_btn.first.click()

            # Wait for message dialog
            msg_box = self.page.get_by_role("textbox", name=sel.MESSAGE_TEXTBOX)
            msg_box.wait_for(timeout=5000)
            msg_box.first.fill(message)

            send_btn = self.page.get_by_role("button", name=sel.SEND_BUTTON)
            send_btn.first.click()
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Profile Info
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------

    def get_search_results(self) -> list[dict[str, str]]:
        """Get search result entries from current search page."""
        results = []
        try:
            cards = self.page.locator(sel.SEARCH_RESULT_CARD)
            card_count = cards.count()
            if card_count == 0:
                self._record_miss("search_result_card")
            for i in range(card_count):
                card = cards.nth(i)
                entry = {}
                name_link = card.locator(sel.SEARCH_RESULT_NAME).first
                if name_link.count() > 0:
                    entry["name"] = name_link.text_content().strip()
                else:
                    self._record_miss("search_result_name")

                headline = card.locator(sel.SEARCH_RESULT_HEADLINE).first
                if headline.count() > 0:
                    entry["headline"] = headline.text_content().strip()

                link = card.locator(sel.SEARCH_RESULT_LINK).first
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
            start_btn = self.page.get_by_role("button", name=sel.START_POST_BUTTON)
            if start_btn.count() == 0:
                return False
            start_btn.first.click()

            editor = self.page.get_by_role("textbox", name=sel.POST_EDITOR_TEXTBOX)
            if editor.count() == 0:
                editor = self.page.locator(sel.POST_EDITOR_FALLBACK)
            if editor.count() == 0:
                return False
            editor.first.fill(text)

            post_btn = self.page.get_by_role("button", name=sel.POST_SUBMIT_BUTTON)
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
            like_btns = self.page.get_by_role("button", name=sel.LIKE_BUTTON)
            button_count = like_btns.count()
            if button_count == 0:
                # FEED_CARD was never queried here; blaming it points the doctor
                # output at a selector that is fine.
                self._record_miss("like_button")
            for i in range(button_count):
                if liked >= count:
                    break
                btn = like_btns.nth(i)
                # aria-pressed=true means we already reacted — skip to avoid unliking
                if btn.get_attribute("aria-pressed") == "true":
                    continue
                btn.scroll_into_view_if_needed()
                btn.first.click()
                self.page.wait_for_timeout(800)
                liked += 1
        except Exception:
            pass
        return liked

    # -------------------------------------------------------------------------
    # Feed posts (index-addressed, for like + comment flows)
    # -------------------------------------------------------------------------

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
                cards, card_count = self._feed_cards()
                for i in range(card_count):
                    if len(posts) >= max_posts:
                        break
                    card = cards.nth(i)
                    entry: dict = {"element_index": i, "author": "", "headline": "", "content": ""}

                    author_el = card.locator(sel.FEED_AUTHOR).first
                    if author_el.count() > 0:
                        entry["author"] = (author_el.text_content() or "").strip()
                    else:
                        self._record_miss("feed_author")

                    key = f"{entry['author']}_{i}"
                    if key in seen:
                        continue
                    seen.add(key)

                    headline_el = card.locator(sel.FEED_AUTHOR_HEADLINE).first
                    if headline_el.count() > 0:
                        entry["headline"] = (headline_el.text_content() or "").strip()

                    content_el = card.locator(sel.FEED_CONTENT).first
                    if content_el.count() > 0:
                        entry["content"] = (content_el.text_content() or "").strip()[:500]
                    else:
                        self._record_miss("feed_content")

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
            cards, card_count = self._feed_cards()
            if post_index >= card_count:
                return False
            card = cards.nth(post_index)
            like_btn = card.get_by_role("button", name=sel.LIKE_BUTTON)
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
            cards, card_count = self._feed_cards()
            if post_index >= card_count:
                return False
            card = cards.nth(post_index)

            comment_btn = card.get_by_role("button", name=sel.COMMENT_BUTTON)
            if comment_btn.count() == 0:
                return False
            comment_btn.first.click()

            textbox = card.get_by_role("textbox", name=sel.COMMENT_TEXTBOX)
            textbox.wait_for(timeout=5000)
            textbox.first.fill(comment_text)

            post_btn = card.get_by_role("button", name=sel.COMMENT_SUBMIT_BUTTON)
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
            edit_btn = self.page.get_by_role("button", name=sel.EDIT_INTRO_BUTTON)
            if edit_btn.count() == 0:
                return False
            edit_btn.first.click()

            field = self.page.get_by_label(sel.HEADLINE_FIELD_LABEL)
            if field.count() == 0:
                return False
            field.first.fill(headline)

            save_btn = self.page.get_by_role("button", name=sel.SAVE_BUTTON)
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
            about_section = self.page.locator(sel.PROFILE_ABOUT_SECTION)
            if about_section.count() == 0:
                return False
            edit_btn = self.page.get_by_role("button", name=sel.EDIT_ABOUT_BUTTON)
            if edit_btn.count() == 0:
                # Fallback: pencil button within the about section's parent block
                edit_btn = about_section.locator(sel.PROFILE_ABOUT_EDIT_FALLBACK)
            if edit_btn.count() == 0:
                return False
            edit_btn.first.click()

            field = self.page.get_by_role("textbox")
            if field.count() == 0:
                return False
            field.first.fill(about)

            save_btn = self.page.get_by_role("button", name=sel.SAVE_BUTTON)
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
            apply_btn = self.page.get_by_role("button", name=sel.EASY_APPLY_BUTTON)
            if apply_btn.count() == 0:
                return {"status": "no_easy_apply", "detail": "No Easy Apply button on page"}
            apply_btn.first.click()
            self.page.wait_for_timeout(1500)

            for _ in range(max_steps):
                if resume_path:
                    file_input = self.page.locator(sel.FILE_INPUT)
                    if file_input.count() > 0:
                        file_input.first.set_input_files(resume_path)
                        self.page.wait_for_timeout(1500)

                submit_btn = self.page.get_by_role("button", name=sel.EASY_APPLY_SUBMIT_BUTTON)
                if submit_btn.count() > 0:
                    if not submit:
                        return {"status": "ready_to_submit", "detail": "Stopped before final submit (pass --submit)"}
                    submit_btn.first.click()
                    self.page.wait_for_timeout(2000)
                    return {"status": "submitted", "detail": "Application submitted"}

                # Required fields LinkedIn flags in red block progression
                errors = self.page.locator(sel.FORM_ERROR)
                if errors.count() > 0:
                    return {
                        "status": "needs_manual_input",
                        "detail": "Form has required fields that need manual answers",
                    }

                next_btn = self.page.get_by_role("button", name=sel.EASY_APPLY_NEXT_BUTTON)
                if next_btn.count() == 0:
                    return {"status": "needs_manual_input", "detail": "Could not find a Next/Review button"}
                next_btn.first.click()
                self.page.wait_for_timeout(1500)

            return {"status": "needs_manual_input", "detail": f"Did not reach submit within {max_steps} steps"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    # -------------------------------------------------------------------------
    # Inbound signals
    # -------------------------------------------------------------------------

    def get_message_threads(self, limit: int = 25) -> list[dict]:
        """Read the messaging pane.

        `last_from_them` is the load-bearing field: LinkedIn prefixes the
        snippet with "You:" when the last message is our own, and that prefix is
        the only thing separating a real reply from an echo of the message we
        sent. Losing it would turn every outbound message into a fake response.
        """
        threads: list[dict] = []
        self._wait_for_content(sel.THREAD_CARD)
        cards = self.page.locator(sel.THREAD_CARD)
        try:
            count = cards.count()
        except Exception:
            return threads
        if count == 0:
            self._record_miss("thread_card")
            return threads

        empty_cards = 0
        for i in range(min(count, limit)):
            card = cards.nth(i)
            try:
                name_el = card.locator(sel.THREAD_NAME).first
                if name_el.count() == 0:
                    # The list is virtualized: cards below the fold exist as
                    # empty shells. Those are not a markup change, so the miss
                    # is only recorded if *every* card came back empty.
                    empty_cards += 1
                    continue
                name = (name_el.text_content() or "").strip()
                if not name:
                    empty_cards += 1
                    continue

                snippet = self._text(card, sel.THREAD_SNIPPET)
                link = card.locator(sel.THREAD_LINK).first
                url = (link.get_attribute("href") or "") if link.count() else ""

                threads.append({
                    "name": name,
                    "url": self._absolute(url),
                    "snippet": sel.THREAD_OWN_MESSAGE_PREFIX.sub("", snippet).strip(),
                    "timestamp": self._text(card, sel.THREAD_TIMESTAMP),
                    "unread": card.locator(sel.THREAD_UNREAD_BADGE).count() > 0,
                    "last_from_them": not sel.THREAD_OWN_MESSAGE_PREFIX.match(snippet),
                })
            except Exception:
                continue

        if not threads and empty_cards:
            self._record_miss("thread_name")
        return threads

    def get_pending_sent_invitations(self) -> list[dict] | None:
        """Read still-pending sent invitations, or None if the list is unreadable.

        The caller infers acceptance from *absence* — an invitation that is no
        longer pending was accepted or withdrawn. That makes an empty list the
        most destructive possible misreading, since it would advance every
        outstanding invitation at once. So [] is returned only when LinkedIn's
        own "People (0)" count says so; anything else unreadable is None.

        Keyed on profile links rather than a card class: LinkedIn rebuilt this
        page with obfuscated class names, and the links are both stable and the
        thing the matcher actually compares on.
        """
        self._wait_for_content(sel.INVITATION_PROFILE_LINK)
        try:
            rows = self._settled_invitation_rows()
            stated = self._stated_invitation_count()
        except Exception:
            return None

        if rows:
            return rows
        # Nothing found. An empty list is the most destructive thing this method
        # can say, so it is only said when LinkedIn's own count agrees.
        if stated == 0:
            return []
        self._record_miss("invitation_profile_link")
        return None

    def _settled_invitation_rows(self, attempts: int = 3, pause_ms: int = 1500) -> list[dict]:
        """Read the list until two consecutive reads agree.

        A *partially* rendered list is more dangerous than an empty one: the
        invitations that did not render read as accepted, and those are exactly
        the ones still pending. Observed live — three of seven rendered, and the
        four missing were all real contacts, every one wrongly proposed as
        connected.

        Stability is the test rather than LinkedIn's own "People (N)" count,
        because that count renders stale: it read 0 while seven invitations were
        on the page. A list still filling in changes between reads; a complete
        one does not.
        """
        previous: list[dict] = []
        for attempt in range(attempts):
            rows = self._invitation_rows()
            if attempt and {r["url"] for r in rows} == {r["url"] for r in previous}:
                return rows
            previous = rows
            self.page.wait_for_timeout(pause_ms)
        return []

    def _stated_invitation_count(self) -> int | None:
        """LinkedIn's own count of pending invitations, e.g. "People (7)"."""
        try:
            text = self.page.locator("main").inner_text()
        except Exception:
            return None
        match = sel.INVITATION_COUNT_TEXT.search(text or "")
        return int(match.group(1)) if match else None

    def _invitation_rows(self) -> list[dict]:
        """One row per distinct profile linked from the invitation list.

        A card links the same profile more than once (avatar and name), so rows
        are deduped on URL, keeping the longest surrounding text as the name
        source — the avatar link carries no text.
        """
        links = self.page.locator(sel.INVITATION_PROFILE_LINK)
        best: dict[str, str] = {}
        for i in range(links.count()):
            link = links.nth(i)
            href = self._absolute(link.get_attribute("href") or "")
            if not href:
                continue
            name = self._invitation_name(link)
            # `setdefault` first: the anchors carry no text of their own, so a
            # plain "keep the longest" comparison never fired and the whole list
            # came back empty while seven links sat on the page.
            best.setdefault(href, name)
            if len(name) > len(best[href]):
                best[href] = name
        return [{"name": name, "url": url} for url, name in best.items()]

    @staticmethod
    def _invitation_name(link) -> str:
        try:
            ancestor = link.locator(sel.INVITATION_NAME_ANCESTOR)
            if ancestor.count() == 0:
                return ""
            return (ancestor.first.inner_text() or "").strip().split("\n")[0].strip()
        except Exception:
            return ""

    def get_job_results(self, limit: int = 25, max_scrolls: int = 12) -> list[dict]:
        """Read job cards from the current job-search page.

        The list is virtualized: about seven cards exist in the DOM at once and
        are recycled out as you scroll, so no single read can see more than a
        fraction of the results. Cards are therefore collected across scrolls
        and deduped, rather than counted once.
        """
        collected: dict[str, dict] = {}

        for scroll in range(max_scrolls + 1):
            found = self._visible_job_cards()
            if not found and scroll == 0:
                self._record_miss("job_card")
                return []
            before = len(collected)
            for job in found:
                collected.setdefault(self._job_key(job), job)
            if len(collected) >= limit:
                break
            # Nothing new after a scroll means the list is exhausted or static.
            if scroll and len(collected) == before:
                break
            if not self._scroll_job_list():
                break
            self.page.wait_for_timeout(900)

        return list(collected.values())[:limit]

    def _scroll_job_list(self) -> bool:
        """Scroll the results pane. False when it did not move."""
        try:
            return bool(self.page.evaluate(sel.JOB_LIST_SCROLL_SCRIPT))
        except Exception:
            return False

    @staticmethod
    def _job_key(job: dict) -> str:
        return job["url"] or f"{job['company']}|{job['title']}".lower()

    def _visible_job_cards(self) -> list[dict]:
        """Parse the job cards currently in the DOM."""
        jobs: list[dict] = []
        cards = self.page.locator(sel.JOB_CARD)
        try:
            count = cards.count()
        except Exception:
            return jobs

        for i in range(count):
            card = cards.nth(i)
            try:
                title = self._text(card, sel.JOB_TITLE)
                if not title:
                    self._record_miss("job_title")
                    continue
                link = card.locator(sel.JOB_LINK).first
                url = (link.get_attribute("href") or "") if link.count() else ""
                jobs.append({
                    "title": title,
                    "company": self._text(card, sel.JOB_COMPANY),
                    "location": self._text(card, sel.JOB_LOCATION),
                    "posted": self._text(card, sel.JOB_POSTED),
                    "url": self._absolute(url),
                    "easy_apply": card.locator(sel.JOB_EASY_APPLY).count() > 0,
                })
            except Exception:
                continue
        return jobs

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _wait_for_content(self, selector: str, timeout_ms: int = 15000) -> None:
        """Give a client-rendered list time to appear before counting it.

        `goto` returns on load, but the messaging and invitation panes are drawn
        afterwards. Counting immediately found zero every time and reported the
        selector as broken — the sync read a full inbox as an empty one.
        """
        try:
            self.page.wait_for_selector(selector, timeout=timeout_ms)
        except Exception:
            # Genuinely absent or genuinely broken; the caller's miss handling
            # tells those apart.
            pass

    def _visible(self, selector: str):
        """The first *visible* match, which is not always the first match.

        LinkedIn ships hidden duplicates of form fields for its responsive
        layouts, so a bare `.first` can land on one that cannot be filled.
        """
        return self.page.locator(selector).locator("visible=true").first

    @staticmethod
    def _text(scope, selector: str) -> str:
        element = scope.locator(selector).first
        if element.count() == 0:
            return ""
        return (element.text_content() or "").strip()

    def _absolute(self, href: str) -> str:
        """LinkedIn hrefs are relative; the CRM stores absolute profile URLs."""
        if not href:
            return ""
        if href.startswith("http"):
            return href.split("?")[0]
        return f"{self.LINKEDIN_URL}{href}".split("?")[0]

    def scrape_profile(self) -> dict[str, str]:
        """Scrape basic profile info from the current profile page.

        Call goto_profile(url) first.
        Returns dict with name, headline, location, about.
        """
        data: dict[str, str] = {}
        try:
            name_el = self.page.locator(sel.PROFILE_NAME)
            if name_el.count():
                data["name"] = name_el.inner_text().strip()
            else:
                self._record_miss("profile_name")

            headline_el = self.page.locator(sel.PROFILE_HEADLINE)
            if headline_el.count():
                data["headline"] = headline_el.first.inner_text().strip()
            else:
                self._record_miss("profile_headline")

            location_el = self.page.locator(sel.PROFILE_LOCATION)
            if location_el.count():
                data["location"] = location_el.first.inner_text().strip()

            about_el = self.page.locator(sel.PROFILE_ABOUT_TEXT)
            if about_el.count():
                data["about"] = about_el.inner_text().strip()
            else:
                self._record_miss("profile_about")
        except Exception:
            pass
        return data
