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

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from urllib.parse import urlencode

from linkedin.automation import selectors as sel

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

Outcome = Literal["ok", "not_applicable", "selector_missing", "degraded"]


@dataclass(frozen=True)
class WriteResult:
    """What every write returns.

    `ok`: it happened (`detail` may carry an identifier, e.g. the post URN).
    `not_applicable`: a normal absence — already connected, not connected,
    already liked, no About section. `selector_missing`: an affordance the
    page should have had is not there, and the miss is recorded for the
    health report. `degraded`: the write happened but something after it
    could not be read. Truthy on `ok` and `degraded`.
    """

    outcome: Outcome
    detail: str = ""

    def __bool__(self) -> bool:
        return self.outcome in ("ok", "degraded")


def _ok(detail: str = "") -> WriteResult:
    return WriteResult("ok", detail)


def _na(detail: str) -> WriteResult:
    return WriteResult("not_applicable", detail)


def _degraded(detail: str) -> WriteResult:
    return WriteResult("degraded", detail)


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

    def _missing(self, name: str, detail: str = "") -> WriteResult:
        """Record a write-side miss and say so. Every selector_missing goes through here."""
        self._record_miss(name)
        return WriteResult("selector_missing", detail or f"{name} not found")

    def _present(self, locator: Locator, name: str) -> bool:
        """True when the locator matches; otherwise records the miss."""
        if locator.count() > 0:
            return True
        self._record_miss(name)
        return False

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

    def login(self, email: str, password: str) -> WriteResult:
        """Log in to LinkedIn.

        Every locator here is narrowed to one *visible* element on purpose.
        LinkedIn renders duplicates of all three controls, and Playwright raises
        on an action against a multi-match locator. A missing field is a
        selector miss, not a wrong password: the health report must name it.
        """
        self.goto_login()
        email_input = self.page.locator(sel.LOGIN_EMAIL_INPUT).locator("visible=true")
        if not self._present(email_input, "login_email_input"):
            return self._missing("login_email_input")
        password_input = self.page.locator(sel.LOGIN_PASSWORD_INPUT).locator("visible=true")
        if not self._present(password_input, "login_password_input"):
            return self._missing("login_password_input")
        sign_in = self.page.get_by_role("button", name=sel.SIGN_IN_BUTTON, exact=True)
        if not self._present(sign_in, "sign_in_button"):
            return self._missing("sign_in_button")
        email_input.first.fill(email)
        password_input.first.fill(password)
        sign_in.last.click()

        try:
            self.page.wait_for_url("**/feed/**", timeout=15000)
            return _ok()
        except Exception:
            return _na("credentials rejected, or a checkpoint is waiting")

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

    def send_connection_request(self, note: str = "") -> WriteResult:
        """Send a connection request from a profile page (assumes we are on one).

        No Connect button beside a Message or Pending button is a normal
        absence (already connected or pending); no Connect, More, Message or
        Pending at all is a page we do not recognise.
        """
        try:
            connect_btn = self.page.get_by_role("button", name=sel.CONNECT_BUTTON)
            if connect_btn.count() > 0:
                connect_btn.first.click()
            else:
                more_btn = self.page.get_by_role("button", name=sel.MORE_BUTTON)
                if more_btn.count() == 0:
                    if self.page.get_by_role("button", name=sel.MESSAGE_BUTTON).count() > 0 or self.page.get_by_role("button", name=sel.PENDING_BUTTON).count() > 0:
                        return _na("already connected or pending")
                    return self._missing("connect_button", "no Connect, More, Message or Pending button on the page")
                more_btn.first.click()
                connect_option = self.page.get_by_role("menuitem", name=sel.CONNECT_MENU_ITEM)
                if connect_option.count() == 0:
                    return _na("no Connect item in the More menu (already connected or pending)")
                connect_option.first.click()

            if note:
                add_note_btn = self.page.get_by_role("button", name=sel.ADD_NOTE_BUTTON)
                if add_note_btn.count() > 0:
                    add_note_btn.first.click()
                    self.page.get_by_role("textbox", name=sel.ADD_NOTE_TEXTBOX).first.fill(note)

            send_btn = self.page.get_by_role("button", name=sel.SEND_BUTTON)
            if not self._present(send_btn, "send_button"):
                return self._missing("send_button")
            send_btn.first.click()
            return _ok()
        except Exception as exc:
            return self._missing("connect_button", f"{type(exc).__name__}: {exc}")

    # -------------------------------------------------------------------------
    # Messaging
    # -------------------------------------------------------------------------

    def send_message(self, message: str) -> WriteResult:
        """Send a message from the profile page of a connected user.

        No Message button beside a Connect button means not connected (a
        normal absence); no Message and no Connect is a page we do not know.
        """
        try:
            msg_btn = self.page.get_by_role("button", name=sel.MESSAGE_BUTTON)
            if msg_btn.count() == 0:
                if self.page.get_by_role("button", name=sel.CONNECT_BUTTON).count() > 0:
                    return _na("not connected")
                return self._missing("message_button")
            msg_btn.first.click()

            msg_box = self.page.get_by_role("textbox", name=sel.MESSAGE_TEXTBOX)
            try:
                msg_box.wait_for(timeout=5000)
            except Exception:
                return self._missing("message_textbox", "message dialog never appeared")
            if not self._present(msg_box, "message_textbox"):
                return self._missing("message_textbox")
            msg_box.first.fill(message)

            send_btn = self.page.get_by_role("button", name=sel.SEND_BUTTON)
            if not self._present(send_btn, "send_button"):
                return self._missing("send_button")
            send_btn.first.click()
            return _ok()
        except Exception as exc:
            return self._missing("message_button", f"{type(exc).__name__}: {exc}")

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

    def create_post(self, text: str) -> WriteResult:
        """Publish a text post to the feed. `detail` is the post URN on `ok`.

        Refuses the old Quill editor: typing a public post into an editor we no
        longer recognise is acting on a page we do not understand, and the
        health report must say the editor selector broke. `degraded` means the
        post went out but its URN could not be read back — it exists on
        LinkedIn and cannot be joined to its metrics.
        """
        try:
            self.goto_feed()
            start_btn = self.page.get_by_role("button", name=sel.START_POST_BUTTON)
            if not self._present(start_btn, "start_post_button"):
                return self._missing("start_post_button")
            start_btn.first.click()

            editor = self.page.get_by_role("textbox", name=sel.POST_EDITOR_TEXTBOX)
            if editor.count() == 0:
                if self.page.locator(sel.POST_EDITOR_FALLBACK).count() > 0:
                    return self._missing("post_editor", "only the legacy editor is present; refusing to type into an editor we do not recognise")
                return self._missing("post_editor")
            editor.first.fill(text)

            post_btn = self.page.get_by_role("button", name=sel.POST_SUBMIT_BUTTON)
            if not self._present(post_btn, "post_submit_button"):
                return self._missing("post_submit_button")
            post_btn.first.click()
            self.page.wait_for_timeout(2000)

            link = self.page.locator(sel.POST_SUCCESS_LINK)
            if link.count() == 0:
                self._record_miss("post_success_link")
                return _degraded("posted, but the post's URN could not be read back")
            href = link.first.get_attribute("href") or ""
            urn = _activity_urn(href)
            if not urn:
                self._record_miss("post_success_link")
                return _degraded("posted, but the success link carried no URN")
            return _ok(urn)
        except Exception as exc:
            return self._missing("post_editor", f"{type(exc).__name__}: {exc}")

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

    def like_post(self, post_index: int) -> WriteResult:
        """Like a feed post by index. Already-liked posts are left alone."""
        try:
            cards, card_count = self._feed_cards()
            if card_count == 0:
                return WriteResult("selector_missing", "feed_card not found")
            if post_index >= card_count:
                return _na(f"no post at index {post_index}")
            card = cards.nth(post_index)
            like_btn = card.get_by_role("button", name=sel.LIKE_BUTTON)
            if not self._present(like_btn, "like_button"):
                return self._missing("like_button")
            if like_btn.first.get_attribute("aria-pressed") == "true":
                return _na("already liked")
            like_btn.first.click()
            return _ok()
        except Exception as exc:
            return self._missing("like_button", f"{type(exc).__name__}: {exc}")

    def comment_on_post(self, post_index: int, comment_text: str) -> WriteResult:
        """Post a comment on a feed post by index."""
        try:
            cards, card_count = self._feed_cards()
            if card_count == 0:
                return WriteResult("selector_missing", "feed_card not found")
            if post_index >= card_count:
                return _na(f"no post at index {post_index}")
            card = cards.nth(post_index)

            comment_btn = card.get_by_role("button", name=sel.COMMENT_BUTTON)
            if not self._present(comment_btn, "comment_button"):
                return self._missing("comment_button")
            comment_btn.first.click()

            textbox = card.get_by_role("textbox", name=sel.COMMENT_TEXTBOX)
            try:
                textbox.wait_for(timeout=5000)
            except Exception:
                return self._missing("comment_textbox", "comment box never appeared")
            if not self._present(textbox, "comment_textbox"):
                return self._missing("comment_textbox")
            textbox.first.fill(comment_text)

            post_btn = card.get_by_role("button", name=sel.COMMENT_SUBMIT_BUTTON)
            if not self._present(post_btn, "comment_submit_button"):
                return self._missing("comment_submit_button")
            post_btn.first.click()
            self.page.wait_for_timeout(1000)
            return _ok()
        except Exception as exc:
            return self._missing("comment_button", f"{type(exc).__name__}: {exc}")

    # -------------------------------------------------------------------------
    # Profile editing (own profile)
    # -------------------------------------------------------------------------

    def goto_own_profile(self) -> None:
        self.page.goto(f"{self.LINKEDIN_URL}/in/me/")

    def update_headline(self, headline: str) -> WriteResult:
        """Update own headline via the 'Edit intro' dialog."""
        try:
            self.goto_own_profile()
            edit_btn = self.page.get_by_role("button", name=sel.EDIT_INTRO_BUTTON)
            if not self._present(edit_btn, "edit_intro_button"):
                return self._missing("edit_intro_button")
            edit_btn.first.click()

            field = self.page.get_by_label(sel.HEADLINE_FIELD_LABEL)
            if not self._present(field, "headline_field"):
                return self._missing("headline_field")
            field.first.fill(headline)

            save_btn = self.page.get_by_role("button", name=sel.SAVE_BUTTON)
            if not self._present(save_btn, "save_button"):
                return self._missing("save_button")
            save_btn.first.click()
            self.page.wait_for_timeout(2000)
            return _ok()
        except Exception as exc:
            return self._missing("edit_intro_button", f"{type(exc).__name__}: {exc}")

    def update_about(self, about: str) -> WriteResult:
        """Update own About section. A profile with no About section is a normal absence."""
        try:
            self.goto_own_profile()
            about_section = self.page.locator(sel.PROFILE_ABOUT_SECTION)
            if about_section.count() == 0:
                return _na("no About section on the profile")
            edit_btn = self.page.get_by_role("button", name=sel.EDIT_ABOUT_BUTTON)
            if edit_btn.count() == 0:
                # Fallback: pencil button within the about section's parent block
                edit_btn = about_section.locator(sel.PROFILE_ABOUT_EDIT_FALLBACK)
            if not self._present(edit_btn, "edit_about_button"):
                return self._missing("edit_about_button")
            edit_btn.first.click()

            field = self.page.get_by_role("textbox")
            if field.count() == 0:
                return self._missing("edit_about_button", "About editor opened but has no textbox")
            field.first.fill(about)

            save_btn = self.page.get_by_role("button", name=sel.SAVE_BUTTON)
            if not self._present(save_btn, "save_button"):
                return self._missing("save_button")
            save_btn.first.click()
            self.page.wait_for_timeout(2000)
            return _ok()
        except Exception as exc:
            return self._missing("edit_about_button", f"{type(exc).__name__}: {exc}")

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

    # -------------------------------------------------------------------------
    # Account metrics (read-only). Each returns None for a label not on the page.
    # -------------------------------------------------------------------------

    def _body_text(self) -> str:
        try:
            return self.page.locator("body").inner_text()
        except Exception:
            return ""

    def read_dashboard_metrics(self) -> dict[str, int | None]:
        """followers, profile_views, post_impressions, search_appearances from /dashboard/."""
        self.page.goto(sel.DASHBOARD_URL)
        self.page.wait_for_timeout(1500)
        text = self._body_text()
        out = {k: _metric_from_text(text, k) for k in ("followers", "profile_views", "post_impressions", "search_appearances")}
        if all(v is None for v in out.values()):
            self._record_miss("dashboard_metrics")
        return out

    def read_network_counts(self) -> dict[str, int | None]:
        """connections from /mynetwork/ (the profile caps it at "500+"); followers as a fallback from the profile."""
        self.page.goto(sel.MY_NETWORK_URL)
        self.page.wait_for_timeout(1500)
        out: dict[str, int | None] = {"connections": _metric_from_text(self._body_text(), "connections")}
        if out["connections"] is None:
            self._record_miss("network_counts")
        self.goto_own_profile()
        self.page.wait_for_timeout(1500)
        out["followers_on_profile"] = _metric_from_text(self._body_text(), "followers_on_profile")
        return out

    def read_ssi(self) -> int | None:
        """Social Selling Index, 0–100. None when LinkedIn says the account has no SSI access
        (a product decision, not a selector miss) or when no score is on the page."""
        self.page.goto(sel.SSI_URL)
        self.page.wait_for_timeout(1500)
        text = self._body_text()
        if sel.SSI_UNAVAILABLE.search(text):
            return None
        value = _metric_from_text(text, "ssi")
        if value is None or not 0 <= value <= 100:
            self._record_miss("ssi_score")
            return None
        return value

    def read_post_impressions(self, urn: str) -> int | None:
        """Impressions for one published post from its analytics page."""
        self.page.goto(sel.POST_ANALYTICS_URL.format(urn=urn))
        self.page.wait_for_timeout(1500)
        value = _metric_from_text(self._body_text(), "impressions")
        if value is None:
            self._record_miss("post_impressions")
        return value

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


def _activity_urn(href: str) -> str:
    """The `urn:li:activity:NNN` (or share/ugcPost) inside a LinkedIn post URL, or ''."""
    m = re.search(r"(urn:li:(?:activity|share|ugcPost):\d+)", href)
    return m.group(1) if m else ""


def _metric_from_text(text: str, name: str) -> int | None:
    match = sel.METRIC_LABELS[name].search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None
