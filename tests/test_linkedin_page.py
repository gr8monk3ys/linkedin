"""Tests for the LinkedIn page object — the layer that talks to LinkedIn.

This was at 0% coverage: the module imported Playwright at module scope, and CI
installs only `--extra dev`. It is import-safe now, so the selector logic runs
here against a Page double (`tests/fake_page.py`).

The recurring theme: a LinkedIn markup change must not look like a quiet page.
"""

import pytest

from linkedin.automation import selectors as sel
from linkedin.automation.linkedin_page import LinkedInPage
from tests.fake_page import FakeCard, FakeElement, FakeLocator, FakePage, canonical


@pytest.fixture
def page():
    return FakePage()


def _feed_card(author="Ada Lovelace", headline="Engineer", content="A post about ML.", liked=False):
    return FakeCard(
        None,
        {
            canonical("css", sel.FEED_AUTHOR): [FakeElement(author)],
            canonical("css", sel.FEED_AUTHOR_HEADLINE): [FakeElement(headline)],
            canonical("css", sel.FEED_CONTENT): [FakeElement(content)],
            canonical("role", "button", sel.LIKE_BUTTON): [
                FakeElement(attributes={"aria-pressed": "true" if liked else "false"})
            ],
            canonical("role", "button", sel.COMMENT_BUTTON): [FakeElement()],
            canonical("role", "textbox", sel.COMMENT_TEXTBOX): [FakeElement()],
            canonical("role", "button", sel.COMMENT_SUBMIT_BUTTON): [FakeElement()],
        },
    )


def _with_feed(page, cards):
    for card in cards:
        card._page = page
    page.register_css(sel.FEED_CARD, cards)
    return page


class TestImportSafety:
    def test_importable_without_playwright(self):
        """CI installs only --extra dev; this module must still import."""
        import importlib
        import sys

        assert "playwright" not in sys.modules
        assert importlib.import_module("linkedin.automation.linkedin_page")


class TestNavigation:
    def test_goto_feed(self, page):
        LinkedInPage(page).goto_feed()
        assert page.visited == ["https://www.linkedin.com/feed/"]

    def test_goto_search_encodes_network_filter(self, page):
        LinkedInPage(page).goto_search("machine learning", network="S")
        assert page.visited[0].endswith("keywords=machine learning&network=%5B%22S%22%5D")

    def test_goto_search_without_network(self, page):
        LinkedInPage(page).goto_search("ml")
        assert "network=" not in page.visited[0]

    def test_goto_recent_activity_normalizes_trailing_slash(self, page):
        LinkedInPage(page).goto_recent_activity("https://www.linkedin.com/in/ada/")
        assert page.visited == ["https://www.linkedin.com/in/ada/recent-activity/all/"]


class TestLogin:
    def _prepare(self, page):
        page.register_css(sel.LOGIN_EMAIL_INPUT, FakeElement())
        page.register_css(sel.LOGIN_PASSWORD_INPUT, FakeElement())
        page.register_role("button", sel.SIGN_IN_BUTTON, FakeElement())
        return page

    def test_successful_login_fills_and_submits(self, page):
        self._prepare(page)
        assert LinkedInPage(page).login("a@b.c", "pw").outcome == "ok"
        assert page.registry[canonical("css", sel.LOGIN_EMAIL_INPUT)][0].filled == ["a@b.c"]
        assert page.registry[canonical("css", sel.LOGIN_PASSWORD_INPUT)][0].filled == ["pw"]
        assert page.registry[canonical("role", "button", sel.SIGN_IN_BUTTON)][0].clicked == 1

    def test_login_returns_false_when_navigation_never_lands(self, page):
        self._prepare(page)
        page.wait_for_url_fails = True
        result = LinkedInPage(page).login("a@b.c", "pw")
        assert result.outcome == "not_applicable" and "checkpoint" in result.detail

    def test_missing_login_fields_are_a_selector_miss_not_a_bad_password(self, page):
        lp = LinkedInPage(page)
        result = lp.login("a@b.c", "pw")
        assert result.outcome == "selector_missing"
        assert lp.selector_misses == ["login_email_input"]

    def test_is_logged_in_detects_login_redirect(self, page):
        page.url = "https://www.linkedin.com/login"

        class Redirecting(FakePage):
            def goto(self, url):
                super().goto(url)
                self.url = "https://www.linkedin.com/login"

        assert LinkedInPage(Redirecting()).is_logged_in() is False

    def test_is_logged_in_true_on_feed(self, page):
        assert LinkedInPage(page).is_logged_in() is True


class TestConnectionRequest:
    """Every lookup is scoped to the top card. The sidebar test is the important one."""

    def test_direct_connect_button(self, page):
        connect, send, dialog = FakeElement(), FakeElement(), FakeElement()
        page.register_top_card({("button", sel.CONNECT_BUTTON): connect})
        page.register_role("dialog", None, dialog)
        page.register_role("button", sel.SEND_BUTTON, page.close_dialog_on(send))

        assert LinkedInPage(page).send_connection_request().outcome == "ok"
        assert connect.clicked == 1 and send.clicked == 1

    def test_a_dialog_that_stays_open_is_an_unconfirmed_send(self, page):
        """Clicking Send is not evidence. The tool reported an invitation as
        sent that never reached the sent list; only the dialog closing says so."""
        page.register_top_card({("button", sel.CONNECT_BUTTON): FakeElement()})
        page.register_role("dialog", None, FakeElement())
        page.register_role("button", sel.SEND_BUTTON, FakeElement())

        result = LinkedInPage(page).send_connection_request()
        assert result.outcome == "degraded" and "unconfirmed" in result.detail

    def test_a_connect_button_outside_the_top_card_is_never_clicked(self, page):
        """The regression. LinkedIn shows "Invite <someone else> to connect" on
        every "People you may know" card; an unscoped `.first` clicked one of
        those and sent nine invitations to people who were not in the CRM."""
        stranger = FakeElement()
        page.register_role("button", sel.CONNECT_BUTTON, stranger)
        page.register_top_card({("button", sel.MESSAGE_BUTTON): FakeElement()})

        lp = LinkedInPage(page)
        result = lp.send_connection_request()
        assert stranger.clicked == 0
        assert result.outcome == "not_applicable" and lp.selector_misses == []

    def test_falls_back_to_the_more_menu(self, page):
        more, menu_item, send = FakeElement(), FakeElement(), FakeElement()
        page.register_top_card({("button", sel.MORE_BUTTON): more})
        page.register_role("menuitem", sel.CONNECT_MENU_ITEM, menu_item)
        page.register_role("dialog", None, FakeElement())
        page.register_role("button", sel.SEND_BUTTON, page.close_dialog_on(send))

        assert LinkedInPage(page).send_connection_request().outcome == "ok"
        assert more.clicked == 1 and menu_item.clicked == 1

    def test_no_top_card_is_a_selector_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.send_connection_request().outcome == "selector_missing"
        assert "profile_top_card" in lp.selector_misses

    def test_no_connect_affordance_at_all_is_a_selector_miss(self, page):
        """A top card with no Connect, More, Message or Pending is not a profile we know."""
        page.register_top_card({})
        lp = LinkedInPage(page)
        result = lp.send_connection_request()
        assert result.outcome == "selector_missing"
        assert "connect_button" in lp.selector_misses

    def test_already_connected_is_a_normal_absence(self, page):
        page.register_top_card({("button", sel.MESSAGE_BUTTON): FakeElement()})
        lp = LinkedInPage(page)
        result = lp.send_connection_request()
        assert result.outcome == "not_applicable"
        assert lp.selector_misses == []

    def test_pending_invitation_is_a_normal_absence(self, page):
        page.register_top_card({("button", sel.PENDING_BUTTON): FakeElement()})
        assert LinkedInPage(page).send_connection_request().outcome == "not_applicable"

    def test_more_menu_without_a_connect_item(self, page):
        """Verified live: a follow-only profile's More menu offers Follow, not Connect."""
        page.register_top_card({("button", sel.MORE_BUTTON): FakeElement()})
        lp = LinkedInPage(page)
        assert lp.send_connection_request().outcome == "not_applicable"
        assert lp.selector_misses == []

    def test_no_dialog_after_clicking_connect_is_a_miss_and_sends_nothing(self, page):
        """A stranger's card sends immediately with no dialog. If no dialog
        appears, the click was not an invitation flow: never hunt for a Send
        button on the page, the messaging composer has one."""
        page_send = FakeElement()
        page.register_top_card({("button", sel.CONNECT_BUTTON): FakeElement()})
        page.register_role("button", sel.SEND_BUTTON, page_send)

        lp = LinkedInPage(page)
        result = lp.send_connection_request()
        assert result.outcome == "selector_missing" and "connect_dialog" in lp.selector_misses
        assert page_send.clicked == 0

    def test_note_is_typed_before_sending(self, page):
        note_box = FakeElement()
        page.register_top_card({("button", sel.CONNECT_BUTTON): FakeElement()})
        page.register_role("dialog", None, FakeElement())
        page.register_role("button", sel.ADD_NOTE_BUTTON, FakeElement())
        page.register_role("textbox", sel.ADD_NOTE_TEXTBOX, note_box)
        page.register_role("button", sel.SEND_BUTTON, page.close_dialog_on(FakeElement()))

        assert LinkedInPage(page).send_connection_request(note="Hi Ada").outcome == "ok"
        assert note_box.filled == ["Hi Ada"]

    def test_missing_send_button_is_a_selector_miss(self, page):
        page.register_top_card({("button", sel.CONNECT_BUTTON): FakeElement()})
        page.register_role("dialog", None, FakeElement())
        lp = LinkedInPage(page)
        result = lp.send_connection_request()
        assert result.outcome == "selector_missing"
        assert "send_button" in lp.selector_misses


class TestSendMessage:
    def test_sends(self, page):
        box, send = FakeElement(), FakeElement()
        page.register_role("button", sel.MESSAGE_BUTTON, FakeElement())
        page.register_role("textbox", sel.MESSAGE_TEXTBOX, box)
        page.register_role("button", sel.SEND_BUTTON, send)

        assert LinkedInPage(page).send_message("hello").outcome == "ok"
        assert box.filled == ["hello"] and send.clicked == 1

    def test_no_message_button_is_a_selector_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.send_message("hello").outcome == "selector_missing"
        assert lp.selector_misses == ["message_button"]

    def test_not_connected_is_a_normal_absence(self, page):
        page.register_role("button", sel.CONNECT_BUTTON, FakeElement())
        lp = LinkedInPage(page)
        assert lp.send_message("hello").outcome == "not_applicable"
        assert lp.selector_misses == []

    def test_message_box_never_appears(self, page):
        page.register_role("button", sel.MESSAGE_BUTTON, FakeElement())
        lp = LinkedInPage(page)
        assert lp.send_message("hello").outcome == "selector_missing"
        assert "message_textbox" in lp.selector_misses


class TestCreatePost:
    URN = "urn:li:activity:7100000000000000000"

    def _prepare(self, page, with_editor=True, fallback_editor=False, success_link=True):
        page.register_role("button", sel.START_POST_BUTTON, FakeElement())
        if with_editor:
            page.register_role("textbox", sel.POST_EDITOR_TEXTBOX, FakeElement())
        if fallback_editor:
            page.register_css(sel.POST_EDITOR_FALLBACK, FakeElement())
        page.register_role("button", sel.POST_SUBMIT_BUTTON, FakeElement())
        if success_link:
            page.register_css(
                sel.POST_SUCCESS_LINK, FakeElement(href=f"https://www.linkedin.com/feed/update/{self.URN}/")
            )
        return page

    def test_publishes_and_reads_back_the_urn(self, page):
        self._prepare(page)
        result = LinkedInPage(page).create_post("Shipped a thing")
        assert result.outcome == "ok"
        assert result.detail == self.URN
        assert page.registry[canonical("role", "textbox", sel.POST_EDITOR_TEXTBOX)][0].filled == ["Shipped a thing"]

    def test_posted_but_urn_unreadable_is_degraded_and_recorded(self, page):
        """The post exists on LinkedIn; it can never be joined to its metrics."""
        self._prepare(page, success_link=False)
        lp = LinkedInPage(page)
        result = lp.create_post("Shipped")
        assert result.outcome == "degraded" and result
        assert result.detail.startswith("posted, but")
        assert lp.selector_misses == ["post_success_link"]

    def test_refuses_the_legacy_editor(self, page):
        """Typing a public post into an editor we no longer recognise is acting on
        a page we do not understand. It used to type into it and report success."""
        self._prepare(page, with_editor=False, fallback_editor=True)
        lp = LinkedInPage(page)
        result = lp.create_post("Shipped")
        assert result.outcome == "selector_missing"
        assert "legacy editor" in result.detail
        assert page.registry[canonical("css", sel.POST_EDITOR_FALLBACK)][0].filled == []
        assert lp.selector_misses == ["post_editor"]

    def test_no_start_post_button(self, page):
        lp = LinkedInPage(page)
        assert lp.create_post("x").outcome == "selector_missing"
        assert lp.selector_misses == ["start_post_button"]

    def test_no_editor_of_either_kind(self, page):
        self._prepare(page, with_editor=False)
        lp = LinkedInPage(page)
        assert lp.create_post("x").outcome == "selector_missing"
        assert lp.selector_misses == ["post_editor"]

    def test_no_post_button(self, page):
        page.register_role("button", sel.START_POST_BUTTON, FakeElement())
        page.register_role("textbox", sel.POST_EDITOR_TEXTBOX, FakeElement())
        lp = LinkedInPage(page)
        assert lp.create_post("x").outcome == "selector_missing"
        assert lp.selector_misses == ["post_submit_button"]


class TestLikeVisiblePosts:
    def test_likes_up_to_count(self, page):
        buttons = [FakeElement(attributes={"aria-pressed": "false"}) for _ in range(5)]
        page.register_role("button", sel.LIKE_BUTTON, buttons)

        assert LinkedInPage(page).like_visible_posts(count=3) == 3
        assert sum(b.clicked for b in buttons) == 3

    def test_skips_already_liked_posts(self, page):
        """aria-pressed=true means we already reacted; clicking would UNLIKE."""
        buttons = [
            FakeElement(attributes={"aria-pressed": "true"}),
            FakeElement(attributes={"aria-pressed": "false"}),
        ]
        page.register_role("button", sel.LIKE_BUTTON, buttons)

        assert LinkedInPage(page).like_visible_posts(count=2) == 1
        assert buttons[0].clicked == 0 and buttons[1].clicked == 1

    def test_scrolls_each_button_into_view(self, page):
        button = FakeElement(attributes={"aria-pressed": "false"})
        page.register_role("button", sel.LIKE_BUTTON, [button])
        LinkedInPage(page).like_visible_posts(count=1)
        assert button.scrolled == 1

    def test_no_like_buttons_records_a_selector_miss(self, page):
        """Zero likes with zero buttons is a breakage, not a quiet feed.

        The miss names LIKE_BUTTON, the selector that actually matched nothing —
        naming feed_card would send the reader to a selector that is fine.
        """
        lp = LinkedInPage(page)
        assert lp.like_visible_posts(count=3) == 0
        assert lp.selector_misses == ["like_button"]
        assert "like_button" in lp.selector_health()["selectors"]


class TestGetFeedPosts:
    def test_collects_author_headline_and_content(self, page):
        _with_feed(page, [_feed_card()])
        posts = LinkedInPage(page).get_feed_posts(max_posts=1)
        assert posts == [
            {"element_index": 0, "author": "Ada Lovelace", "headline": "Engineer", "content": "A post about ML."}
        ]

    def test_respects_max_posts(self, page):
        _with_feed(page, [_feed_card(author=f"A{i}") for i in range(5)])
        assert len(LinkedInPage(page).get_feed_posts(max_posts=2)) == 2

    def test_truncates_long_content(self, page):
        _with_feed(page, [_feed_card(content="x" * 900)])
        assert len(LinkedInPage(page).get_feed_posts(max_posts=1)[0]["content"]) == 500

    def test_element_index_addresses_the_card(self, page):
        _with_feed(page, [_feed_card(author="A"), _feed_card(author="B")])
        posts = LinkedInPage(page).get_feed_posts(max_posts=2)
        assert [p["element_index"] for p in posts] == [0, 1]

    def test_empty_feed_records_the_card_selector_miss(self, page):
        """The exact shape of a LinkedIn class rename."""
        lp = LinkedInPage(page)
        assert lp.get_feed_posts(max_posts=5) == []
        assert lp.selector_misses == ["feed_card"]
        assert lp.selector_health() == {
            "healthy": False,
            "misses": ["feed_card"],
            "selectors": {"feed_card": sel.FEED_CARD},
        }

    def test_cards_present_but_inner_selectors_broken(self, page):
        """Partial rename: cards match, author/content do not."""
        card = FakeCard(None, {})
        _with_feed(page, [card])
        lp = LinkedInPage(page)
        posts = lp.get_feed_posts(max_posts=1)
        assert posts[0]["author"] == "" and posts[0]["content"] == ""
        assert set(lp.selector_misses) == {"feed_author", "feed_content"}

    def test_healthy_feed_records_no_misses(self, page):
        _with_feed(page, [_feed_card()])
        lp = LinkedInPage(page)
        lp.get_feed_posts(max_posts=1)
        assert lp.selector_health()["healthy"] is True


class TestRebuiltFeed:
    """Verified 2026-09-03: no CSS card; cards are read by shape and tagged by index."""

    def test_script_rows_become_posts_and_tagged_cards_take_likes(self, page):
        # The fake cannot run the script, so the cards it would have tagged are registered up front.
        other = FakeCard(
            None,
            {
                canonical("role", "button", sel.LIKE_BUTTON): [
                    FakeElement(attributes={"aria-label": "Reaction button state: Like"})
                ]
            },
        )
        card = FakeCard(
            None,
            {
                canonical("role", "button", sel.LIKE_BUTTON): [
                    FakeElement(attributes={"aria-label": "Reaction button state: no reaction"})
                ]
            },
        )
        _with_feed(page, [])
        page.register_css(f"[{sel.FEED_CARD_TAG}]", [other, card])
        page.register_css(f'[{sel.FEED_CARD_TAG}="1"]', [card])
        other._page = card._page = page
        page.evaluate_result = [
            {"element_index": 0, "author": "Mo Zia", "headline": "CEO", "content": "A post about ops."}
        ]
        lp = LinkedInPage(page)
        posts = lp.get_feed_posts(max_posts=3)
        assert posts == [{"element_index": 0, "author": "Mo Zia", "headline": "CEO", "content": "A post about ops."}]
        assert lp.selector_misses == []
        assert page.evaluated == [sel.FEED_POSTS_SCRIPT]
        # the button patterns reach the script from the catalogue, not a JS copy
        (arg,) = page.evaluate_args[0]
        assert arg == {
            "maxPosts": 3,
            "tag": sel.FEED_CARD_TAG,
            "likePattern": sel.LIKE_BUTTON.pattern,
            "commentPattern": sel.COMMENT_BUTTON.pattern,
        }
        # like_post finds the card by its exact tag value, not by position
        assert lp.like_post(1).outcome == "ok"
        assert lp.like_post(7).outcome == "not_applicable"

    def test_a_script_that_throws_is_a_feed_card_miss(self, page):
        page.evaluate_result = RuntimeError("querySelectorAll is not a function")
        lp = LinkedInPage(page)
        assert lp.get_feed_posts(max_posts=3) == []
        assert lp.selector_misses == ["feed_card"]

    def test_a_reaction_state_other_than_none_is_already_liked(self, page):
        card = FakeCard(
            None,
            {
                canonical("role", "button", sel.LIKE_BUTTON): [
                    FakeElement(attributes={"aria-label": "Reaction button state: Like"})
                ]
            },
        )
        _with_feed(page, [card])
        assert LinkedInPage(page).like_post(0).outcome == "not_applicable"

    def test_no_css_cards_and_no_script_rows_is_a_miss(self, page):
        page.evaluate_result = []
        lp = LinkedInPage(page)
        assert lp.get_feed_posts(max_posts=3) == []
        assert lp.selector_misses == ["feed_card"]


class TestLikePost:
    def test_likes_by_index(self, page):
        cards = [_feed_card(author="A"), _feed_card(author="B")]
        _with_feed(page, cards)
        assert LinkedInPage(page).like_post(1).outcome == "ok"
        assert cards[1].children[canonical("role", "button", sel.LIKE_BUTTON)][0].clicked == 1

    def test_out_of_range_index(self, page):
        _with_feed(page, [_feed_card()])
        assert LinkedInPage(page).like_post(5).outcome == "not_applicable"

    def test_already_liked_is_not_unliked(self, page):
        card = _feed_card(liked=True)
        _with_feed(page, [card])
        assert LinkedInPage(page).like_post(0).outcome == "not_applicable"
        assert card.children[canonical("role", "button", sel.LIKE_BUTTON)][0].clicked == 0

    def test_no_cards_records_a_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.like_post(0).outcome == "selector_missing"
        assert "feed_card" in lp.selector_misses

    def test_card_without_a_like_button_is_a_selector_miss(self, page):
        _with_feed(page, [FakeCard(None, {})])
        lp = LinkedInPage(page)
        assert lp.like_post(0).outcome == "selector_missing"
        assert lp.selector_misses == ["like_button"]


class TestCommentOnPost:
    def test_posts_a_comment(self, page):
        card = _feed_card()
        _with_feed(page, [card])
        assert LinkedInPage(page).comment_on_post(0, "Nice work").outcome == "ok"
        assert card.children[canonical("role", "textbox", sel.COMMENT_TEXTBOX)][0].filled == ["Nice work"]
        assert card.children[canonical("role", "button", sel.COMMENT_SUBMIT_BUTTON)][0].clicked == 1

    def test_out_of_range_index(self, page):
        _with_feed(page, [_feed_card()])
        assert LinkedInPage(page).comment_on_post(3, "hi").outcome == "not_applicable"

    def test_missing_comment_button(self, page):
        _with_feed(page, [FakeCard(None, {})])
        lp = LinkedInPage(page)
        assert lp.comment_on_post(0, "hi").outcome == "selector_missing"
        assert lp.selector_misses == ["comment_button"]

    def test_comment_box_never_appears(self, page):
        card = FakeCard(None, {canonical("role", "button", sel.COMMENT_BUTTON): [FakeElement()]})
        _with_feed(page, [card])
        lp = LinkedInPage(page)
        assert lp.comment_on_post(0, "hi").outcome == "selector_missing"
        assert lp.selector_misses == ["comment_textbox"]


class TestSearchResults:
    def _card(self, name="Ada", headline="Engineer", href="https://www.linkedin.com/in/ada?trk=x"):
        return FakeCard(
            None,
            {
                canonical("css", sel.SEARCH_RESULT_NAME): [FakeElement(name)],
                canonical("css", sel.SEARCH_RESULT_HEADLINE): [FakeElement(headline)],
                canonical("css", sel.SEARCH_RESULT_LINK): [FakeElement(href=href)],
            },
        )

    def test_parses_results_and_strips_tracking_params(self, page):
        page.register_css(sel.SEARCH_RESULT_CARD, [self._card()])
        assert LinkedInPage(page).get_search_results() == [
            {"name": "Ada", "headline": "Engineer", "linkedin_url": "https://www.linkedin.com/in/ada"}
        ]

    def test_nameless_cards_are_dropped(self, page):
        page.register_css(sel.SEARCH_RESULT_CARD, [FakeCard(None, {})])
        assert LinkedInPage(page).get_search_results() == []

    def test_no_cards_and_no_script_rows_records_a_miss(self, page):
        page.evaluate_result = []
        lp = LinkedInPage(page)
        assert lp.get_search_results() == []
        assert "search_result_card" in lp.selector_misses

    def test_rebuilt_page_is_read_by_the_dom_shape_script(self, page):
        """Verified 2026-09-02: no CSS card matches; the script reads name/degree/headline lines."""
        page.evaluate_result = [
            {
                "name": "Neha Tammana",
                "headline": "Senior Solutions Engineer - AI Specialist",
                "location": "SF Bay Area",
                "degree": "2nd",
                "linkedin_url": "https://www.linkedin.com/in/neha",
            },
            {"name": "", "headline": "nameless", "linkedin_url": ""},
        ]
        lp = LinkedInPage(page)
        rows = lp.get_search_results()
        assert rows == [
            {
                "name": "Neha Tammana",
                "headline": "Senior Solutions Engineer - AI Specialist",
                "linkedin_url": "https://www.linkedin.com/in/neha",
                "location": "SF Bay Area",
                "degree": "2nd",
            }
        ]
        assert lp.selector_misses == []
        assert page.evaluated == [sel.SEARCH_RESULTS_SCRIPT]

    def test_broken_name_selector_is_recorded(self, page):
        page.register_css(sel.SEARCH_RESULT_CARD, [FakeCard(None, {})])
        lp = LinkedInPage(page)
        lp.get_search_results()
        assert "search_result_name" in lp.selector_misses


class TestScrapeProfile:
    def test_scrapes_all_fields(self, page):
        page.register_css(sel.PROFILE_NAME, FakeElement("Ada Lovelace"))
        page.register_css(sel.PROFILE_HEADLINE, FakeElement("Engineer"))
        page.register_css(sel.PROFILE_LOCATION, FakeElement("London"))
        page.register_css(sel.PROFILE_ABOUT_TEXT, FakeElement("I build things."))

        lp = LinkedInPage(page)
        assert lp.scrape_profile() == {
            "name": "Ada Lovelace",
            "headline": "Engineer",
            "location": "London",
            "about": "I build things.",
        }
        assert lp.selector_health()["healthy"] is True

    def test_a_blank_scrape_is_reported_as_broken_selectors(self, page):
        lp = LinkedInPage(page)
        assert lp.scrape_profile() == {}
        assert set(lp.selector_misses) == {"profile_name", "profile_headline", "profile_about"}


class TestRebuiltProfile:
    """Verified 2026-09-03: no h1, no class hooks; the page text has a fixed shape."""

    TEXT = "Ada Lovelace\nShe/Her\nML Engineer | pipelines\nLondon, UK\n·\nContact info\n500+ connections\nAbout\nFirst paragraph.\nSecond paragraph.\nActivity\n1,000 followers"

    def test_profile_is_read_from_text_when_css_matches_nothing(self, page):
        page.register_css("main", FakeElement(self.TEXT))
        lp = LinkedInPage(page)
        d = lp.scrape_profile()
        assert d["name"] == "Ada Lovelace" and d["headline"] == "ML Engineer | pipelines"
        assert d["location"] == "London, UK" and d["about"] == "First paragraph.\n\nSecond paragraph."
        assert lp.selector_misses == []

    def test_the_footer_about_line_is_not_an_about_section(self, page):
        # A stranger's profile with no About loaded: the only "About" is the footer's link list.
        page.register_css(
            "main",
            FakeElement(
                "Satya Nadella\n· 3rd\nChairman and CEO at Microsoft\nRedmond, Washington\nMessage\nAbout\nAccessibility\nTalent Solutions\nCareers"
            ),
        )
        d = LinkedInPage(page).scrape_profile()
        assert d["headline"] == "Chairman and CEO at Microsoft" and "about" not in d

    def test_body_is_read_when_the_page_has_no_main(self, page):
        page.register_css("body", FakeElement("Ada Lovelace\nShe/Her\nML Engineer\nLondon\nAbout\nHello.\nActivity"))
        assert LinkedInPage(page).scrape_profile()["about"] == "Hello."

    def test_a_profile_without_a_location_does_not_borrow_the_next_line(self, page):
        page.register_css("main", FakeElement("Bob Builder\nCTO at Acme\n·\nContact info\nAbout\nHi.\nExperience"))
        d = LinkedInPage(page).scrape_profile()
        assert d["headline"] == "CTO at Acme" and "location" not in d and d["about"] == "Hi."

    def test_scrape_scrolls_before_reading(self, page):
        page.register_css("main", FakeElement("Ada Lovelace\nEngineer\nLondon"))
        LinkedInPage(page).scrape_profile()
        assert page.evaluated[: len(sel.PROFILE_SCROLL_STOPS)] == [sel.PROFILE_SCROLL_SCRIPT] * len(
            sel.PROFILE_SCROLL_STOPS
        )
        assert [a for (a,) in page.evaluate_args[: len(sel.PROFILE_SCROLL_STOPS)]] == list(sel.PROFILE_SCROLL_STOPS)

    def test_degree_marker_is_skipped_like_pronouns(self, page):
        page.register_css("main", FakeElement("Bob Builder\n• 2nd\nCTO at Acme\nDenver"))
        assert LinkedInPage(page).scrape_profile()["headline"] == "CTO at Acme"


class TestProfileEditing:
    def test_update_headline(self, page):
        field = FakeElement()
        page.register_role("button", sel.EDIT_INTRO_BUTTON, FakeElement())
        page.register_label(sel.HEADLINE_FIELD_LABEL, field)
        page.register_role("button", sel.SAVE_BUTTON, FakeElement())

        assert LinkedInPage(page).update_headline("ML Engineer").outcome == "ok"
        assert field.filled == ["ML Engineer"]

    def test_update_headline_without_edit_button(self, page):
        lp = LinkedInPage(page)
        assert lp.update_headline("x").outcome == "selector_missing"
        assert lp.selector_misses == ["edit_intro_button"]

    def test_update_headline_without_save_button(self, page):
        page.register_role("button", sel.EDIT_INTRO_BUTTON, FakeElement())
        page.register_label(sel.HEADLINE_FIELD_LABEL, FakeElement())
        lp = LinkedInPage(page)
        assert lp.update_headline("x").outcome == "selector_missing"
        assert lp.selector_misses == ["save_button"]

    def test_update_about(self, page):
        box = FakeElement()
        page.register_css(sel.PROFILE_ABOUT_SECTION, FakeElement())
        page.register_role("button", sel.EDIT_ABOUT_BUTTON, FakeElement())
        page.register_role("textbox", None, box)
        page.register_role("button", sel.SAVE_BUTTON, FakeElement())

        assert LinkedInPage(page).update_about("About me").outcome == "ok"
        assert box.filled == ["About me"]

    def test_update_about_without_an_about_section_is_a_normal_absence(self, page):
        lp = LinkedInPage(page)
        assert lp.update_about("x").outcome == "not_applicable"
        assert lp.selector_misses == []


class TestEasyApply:
    def test_no_easy_apply_button(self, page):
        assert LinkedInPage(page).easy_apply()["status"] == "no_easy_apply"

    def test_stops_before_submitting_by_default(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        submit = FakeElement()
        page.register_role("button", sel.EASY_APPLY_SUBMIT_BUTTON, submit)

        result = LinkedInPage(page).easy_apply(submit=False)
        assert result["status"] == "ready_to_submit"
        assert submit.clicked == 0, "must never submit without an explicit opt-in"

    def test_submits_when_asked(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        submit = FakeElement()
        page.register_role("button", sel.EASY_APPLY_SUBMIT_BUTTON, submit)

        assert LinkedInPage(page).easy_apply(submit=True)["status"] == "submitted"
        assert submit.clicked == 1

    def test_uploads_the_resume(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        file_input = FakeElement()
        page.register_css(sel.FILE_INPUT, file_input)
        page.register_role("button", sel.EASY_APPLY_SUBMIT_BUTTON, FakeElement())

        LinkedInPage(page).easy_apply(resume_path="/tmp/cv.pdf", submit=True)
        assert file_input.uploaded == ["/tmp/cv.pdf"]

    def test_required_fields_stop_the_flow(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        page.register_css(sel.FORM_ERROR, FakeElement("This field is required"))

        assert LinkedInPage(page).easy_apply()["status"] == "needs_manual_input"

    def test_no_next_button_stops_the_flow(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        result = LinkedInPage(page).easy_apply()
        assert result["status"] == "needs_manual_input"
        assert "Next/Review" in result["detail"]

    def test_gives_up_after_max_steps(self, page):
        page.register_role("button", sel.EASY_APPLY_BUTTON, FakeElement())
        page.register_role("button", sel.EASY_APPLY_NEXT_BUTTON, FakeElement())

        result = LinkedInPage(page).easy_apply(max_steps=3)
        assert result["status"] == "needs_manual_input"
        assert "within 3 steps" in result["detail"]


class TestSelectorCatalogue:
    def test_every_fragile_name_is_reachable_from_a_miss(self):
        """`selector_health` must be able to name any selector it reports."""
        lp = LinkedInPage(FakePage())
        for name in sel.FRAGILE_SELECTORS:
            lp._record_miss(name)
        health = lp.selector_health()
        assert set(health["selectors"]) == set(sel.FRAGILE_SELECTORS)

    def test_every_write_path_records_a_miss_on_an_empty_page(self):
        """The health report covered 8 reads and 2 writes; a renamed Connect
        button was a bare False the report never mentioned."""
        expected = {
            "login": (lambda lp: lp.login("e", "p"), "login_email_input"),
            # An empty page has no top card, so that is the first thing missing.
            "connect": (lambda lp: lp.send_connection_request(), "profile_top_card"),
            "message": (lambda lp: lp.send_message("hi"), "message_button"),
            "post": (lambda lp: lp.create_post("x"), "start_post_button"),
            "headline": (lambda lp: lp.update_headline("x"), "edit_intro_button"),
        }
        for name, (act, miss) in expected.items():
            lp = LinkedInPage(FakePage())
            assert act(lp).outcome == "selector_missing", name
            assert miss in lp.selector_misses, name
            assert miss in lp.selector_health()["selectors"], name

    def test_misses_are_deduplicated(self):
        lp = LinkedInPage(FakePage())
        lp._record_miss("feed_card")
        lp._record_miss("feed_card")
        assert lp.selector_misses == ["feed_card"]


class TestSelectorWarningReachesTheUser:
    """A breakage must reach the terminal, not just an attribute."""

    def test_cli_warns_and_names_the_broken_selectors(self, capsys):
        from linkedin.cli import _report_selector_health

        page = FakePage()
        lp = LinkedInPage(page)
        lp.get_feed_posts(max_posts=3)  # empty feed -> feed_card miss

        _report_selector_health(lp.selector_health())
        out = capsys.readouterr().out
        assert "markup may have changed" in out
        assert sel.FEED_CARD in out
        assert "selectors.py" in out

    def test_healthy_session_says_nothing(self, capsys):
        from linkedin.cli import _report_selector_health

        page = FakePage()
        _with_feed(page, [_feed_card()])
        lp = LinkedInPage(page)
        lp.get_feed_posts(max_posts=1)

        _report_selector_health(lp.selector_health())
        assert capsys.readouterr().out == ""


def _thread_card(name="Ryan Barner", snippet="Happy to chat.", timestamp="Aug 29", href="/in/ryanbarner", unread=True):
    children = {
        canonical("css", sel.THREAD_NAME): [FakeElement(name)],
        canonical("css", sel.THREAD_SNIPPET): [FakeElement(snippet)],
        canonical("css", sel.THREAD_TIMESTAMP): [FakeElement(timestamp)],
        canonical("css", sel.THREAD_LINK): [FakeElement(href=href)],
    }
    if unread:
        children[canonical("css", sel.THREAD_UNREAD_BADGE)] = [FakeElement("1")]
    return FakeCard(None, children)


def _with_threads(page, cards):
    for card in cards:
        card._page = page
    page.register_css(sel.THREAD_CARD, cards)
    return page


class TestMessageThreads:
    def test_reads_name_snippet_and_url(self, page):
        _with_threads(page, [_thread_card()])
        threads = LinkedInPage(page).get_message_threads()

        assert len(threads) == 1
        assert threads[0]["name"] == "Ryan Barner"
        assert threads[0]["snippet"] == "Happy to chat."
        assert threads[0]["url"].endswith("/in/ryanbarner")

    def test_no_threads_records_a_selector_miss(self, page):
        """An empty messaging pane and a renamed class look identical."""
        lp = LinkedInPage(page)
        assert lp.get_message_threads() == []
        assert "thread_card" in lp.selector_misses

    def test_thread_without_a_name_records_a_miss(self, page):
        card = _thread_card()
        del card.children[canonical("css", sel.THREAD_NAME)]
        _with_threads(page, [card])

        lp = LinkedInPage(page)
        lp.get_message_threads()
        assert "thread_name" in lp.selector_misses

    def test_own_last_message_is_marked_not_from_them(self, page):
        card = _thread_card(snippet="You: sent you my resume")
        _with_threads(page, [card])
        threads = LinkedInPage(page).get_message_threads()
        assert threads[0]["last_from_them"] is False

    def test_their_message_is_marked_from_them(self, page):
        _with_threads(page, [_thread_card()])
        threads = LinkedInPage(page).get_message_threads()
        assert threads[0]["last_from_them"] is True

    def test_limit_caps_threads_read(self, page):
        _with_threads(page, [_thread_card(name=f"P{i}") for i in range(10)])
        assert len(LinkedInPage(page).get_message_threads(limit=3)) == 3

    def test_goto_messaging_navigates(self, page):
        LinkedInPage(page).goto_messaging()
        assert page.visited[-1].endswith("/messaging/")


class TestPendingInvitations:
    """Keyed on profile links: LinkedIn rebuilt this page with obfuscated class
    names, so `li.invitation-card` matches nothing on the live site."""

    @staticmethod
    def _link(name, href):
        """One invitation anchor: no text of its own, name on an ancestor."""
        card = FakeCard(
            None,
            {
                canonical("css", sel.INVITATION_NAME_ANCESTOR): [
                    FakeElement(f"{name}\nProduct Manager\nSent 3 days ago") if name else FakeElement("")
                ],
            },
        )
        card._elements = [FakeElement(href=href)]
        return card

    def _page_with(self, links, main_text="People (2)"):
        page = FakePage()
        for card in links:
            card._page = page
        page.register_css(sel.INVITATION_PROFILE_LINK, links)
        page.register_css("main", [FakeElement(main_text)])
        return page

    def test_reads_pending_invitations(self):
        page = self._page_with(
            [
                self._link("Andy Matsuzaki", "/in/andy"),
                self._link("Michele Chung", "/in/michele"),
            ]
        )
        pending = LinkedInPage(page).get_pending_sent_invitations()

        assert pending == [
            {"name": "Andy Matsuzaki", "url": "https://www.linkedin.com/in/andy"},
            {"name": "Michele Chung", "url": "https://www.linkedin.com/in/michele"},
        ]

    def test_the_same_profile_linked_twice_is_one_invitation(self):
        """A card links the profile from both the avatar and the name."""
        page = self._page_with(
            [
                self._link("", "/in/andy"),
                self._link("Andy Matsuzaki", "/in/andy"),
            ],
            main_text="People (1)",
        )
        pending = LinkedInPage(page).get_pending_sent_invitations()

        assert pending == [{"name": "Andy Matsuzaki", "url": "https://www.linkedin.com/in/andy"}]

    def test_a_still_rendering_list_is_refused(self):
        """The most dangerous shape: rows present, but not all of them yet.

        Every invitation that failed to render reads as accepted. Observed live
        — three of seven rendered, and the four missing were all real contacts.
        A list still filling in changes between reads, which is the tell.
        """
        page = self._page_with([], main_text="People (7)")
        growing = [
            [self._link("Sashank Gondala", "/in/sashank")],
            [self._link("Sashank Gondala", "/in/sashank"), self._link("Andy", "/in/andy")],
            [
                self._link("Sashank Gondala", "/in/sashank"),
                self._link("Andy", "/in/andy"),
                self._link("Michele", "/in/michele"),
            ],
        ]

        def next_batch(_selector):
            batch = growing.pop(0) if growing else []
            for card in batch:
                card._page = page
            return FakeLocator(page, batch)

        page.locator = next_batch
        lp = LinkedInPage(page)

        assert lp.get_pending_sent_invitations() is None
        assert "invitation_profile_link" in lp.selector_misses

    def test_a_list_that_stops_changing_is_trusted(self):
        """Two identical reads mean the page finished rendering."""
        page = self._page_with(
            [
                self._link("Andy Matsuzaki", "/in/andy"),
            ],
            main_text="People (0)",
        )  # count renders stale; stability is the test

        pending = LinkedInPage(page).get_pending_sent_invitations()
        assert pending == [{"name": "Andy Matsuzaki", "url": "https://www.linkedin.com/in/andy"}]

    def test_a_complete_list_matching_the_stated_count_is_accepted(self):
        page = self._page_with(
            [
                self._link("Andy Matsuzaki", "/in/andy"),
                self._link("Michele Chung", "/in/michele"),
            ],
            main_text="People (2)",
        )
        assert len(LinkedInPage(page).get_pending_sent_invitations()) == 2

    def test_unreadable_list_returns_none_not_empty(self):
        """The caller treats [] as 'all accepted'. A broken page must not say that.

        This is the one place in the package where failing soft to an empty list
        would advance every outstanding invitation at once.
        """
        page = self._page_with([], main_text="People (7)")
        lp = LinkedInPage(page)

        assert lp.get_pending_sent_invitations() is None
        assert "invitation_profile_link" in lp.selector_misses

    def test_no_count_at_all_is_also_unreadable(self):
        page = self._page_with([], main_text="something else entirely")
        assert LinkedInPage(page).get_pending_sent_invitations() is None

    def test_genuinely_empty_list_is_distinguishable(self):
        """Zero pending invitations is real, and must not read as a breakage.

        Only LinkedIn's own count makes it a fact rather than a guess.
        """
        page = self._page_with([], main_text="People (0)")
        lp = LinkedInPage(page)

        assert lp.get_pending_sent_invitations() == []
        assert lp.selector_misses == []


def _job_card(title="ML Engineer", company="Netflix", location="Los Angeles", href="/jobs/view/123", easy=True):
    children = {
        canonical("css", sel.JOB_TITLE): [FakeElement(title)],
        canonical("css", sel.JOB_COMPANY): [FakeElement(company)],
        canonical("css", sel.JOB_LOCATION): [FakeElement(location)],
        canonical("css", sel.JOB_LINK): [FakeElement(href=href)],
    }
    if easy:
        children[canonical("css", sel.JOB_EASY_APPLY)] = [FakeElement("Easy Apply")]
    return FakeCard(None, children)


class TestJobResults:
    def test_reads_job_cards(self, page):
        card = _job_card()
        card._page = page
        page.register_css(sel.JOB_CARD, [card])

        jobs = LinkedInPage(page).get_job_results()
        assert len(jobs) == 1
        assert jobs[0]["title"] == "ML Engineer"
        assert jobs[0]["company"] == "Netflix"
        assert jobs[0]["location"] == "Los Angeles"
        assert jobs[0]["easy_apply"] is True
        assert jobs[0]["url"].endswith("/jobs/view/123")

    def test_no_jobs_records_a_selector_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.get_job_results() == []
        assert "job_card" in lp.selector_misses

    def test_job_without_a_title_is_dropped_and_recorded(self, page):
        card = _job_card()
        del card.children[canonical("css", sel.JOB_TITLE)]
        card._page = page
        page.register_css(sel.JOB_CARD, [card])

        lp = LinkedInPage(page)
        assert lp.get_job_results() == []
        assert "job_title" in lp.selector_misses

    def test_goto_job_search_encodes_query_and_location(self, page):
        LinkedInPage(page).goto_job_search("Machine Learning Engineer", location="Los Angeles, CA")
        url = page.visited[-1]
        assert "keywords=Machine+Learning+Engineer" in url
        assert "location=Los+Angeles%2C+CA" in url


class TestLoginStrictMode:
    """The real login page renders duplicates of every field.

    Measured against linkedin.com/login on 2026-08-30: two inputs match the
    accessible name "Email or phone" (one hidden, one visible), four match
    "Password" (including the "Show password" toggle), and two buttons match
    "Sign in" — the first of which is "Sign in with Apple".

    Playwright raises on an action against a multi-match locator, and `login()`
    swallows exceptions, so this failed as a silent False from the day it was
    written.
    """

    @pytest.fixture
    def login_page(self):
        page = FakePage(url="https://www.linkedin.com/login")
        page.register_css(sel.LOGIN_EMAIL_INPUT, [FakeElement(), FakeElement()])
        page.register_css(sel.LOGIN_PASSWORD_INPUT, [FakeElement(), FakeElement()])
        page.register_role("button", sel.SIGN_IN_BUTTON, [FakeElement("Sign in with Apple"), FakeElement("Sign in")])
        return page

    def test_login_fills_credentials_despite_duplicate_fields(self, login_page):
        assert LinkedInPage(login_page).login("me@example.com", "hunter2").outcome == "ok"

    def test_login_types_into_the_field_it_selected(self, login_page):
        LinkedInPage(login_page).login("me@example.com", "hunter2")
        email = login_page.registry[canonical("css", sel.LOGIN_EMAIL_INPUT)][0]
        password = login_page.registry[canonical("css", sel.LOGIN_PASSWORD_INPUT)][0]
        assert email.filled == ["me@example.com"]
        assert password.filled == ["hunter2"]

    def test_login_uses_an_exact_sign_in_match(self, login_page):
        """A substring match on "Sign in" also matches "Sign in with Apple"."""
        LinkedInPage(login_page).login("me@example.com", "hunter2")
        buttons = login_page.registry[canonical("role", "button", sel.SIGN_IN_BUTTON)]
        assert buttons[0].clicked == 0, "clicked 'Sign in with Apple'"

    def test_login_reports_failure_when_navigation_never_completes(self, login_page):
        login_page.wait_for_url_fails = True
        assert not LinkedInPage(login_page).login("me@example.com", "hunter2")


class TestJobResultScrolling:
    """The job list is virtualized: `li[data-occludable-job-id]` renders about
    seven cards at a time and recycles them out of the DOM as you scroll, so a
    single read can never see more than a fraction of 1,000+ results.
    """

    def _card(self, title, company="Netflix"):
        return _job_card(title=title, company=company, href=f"/jobs/view/{title}")

    def test_accumulates_across_scrolls(self):
        page = FakePage()
        batches = [
            [self._card("A"), self._card("B")],
            [self._card("C")],  # A and B recycled out
            [self._card("D")],
        ]

        def locator(selector):
            if selector != sel.JOB_CARD:
                return FakeLocator(page, [])
            batch = batches.pop(0) if batches else []
            for card in batch:
                card._page = page
            return FakeLocator(page, batch)

        page.locator = locator
        jobs = LinkedInPage(page).get_job_results(limit=25)

        assert sorted(j["title"] for j in jobs) == ["A", "B", "C", "D"]

    def test_stops_when_scrolling_stops_yielding_new_cards(self):
        """A static list must terminate, not spin for the full scroll budget."""
        page = FakePage()
        card = self._card("Only")
        card._page = page
        page.register_css(sel.JOB_CARD, [card])

        jobs = LinkedInPage(page).get_job_results(limit=25)

        assert [j["title"] for j in jobs] == ["Only"]
        assert len(page.evaluated) <= 3

    def test_limit_stops_the_scrolling_early(self):
        page = FakePage()
        cards = [self._card(str(i)) for i in range(10)]
        for card in cards:
            card._page = page
        page.register_css(sel.JOB_CARD, cards)

        jobs = LinkedInPage(page).get_job_results(limit=4)
        assert len(jobs) == 4
        assert page.evaluated == []

    def test_the_same_job_seen_twice_is_one_result(self):
        page = FakePage()
        batches = [[self._card("A")], [self._card("A")], [self._card("A")]]

        def locator(selector):
            if selector != sel.JOB_CARD:
                return FakeLocator(page, [])
            batch = batches.pop(0) if batches else []
            for card in batch:
                card._page = page
            return FakeLocator(page, batch)

        page.locator = locator
        assert len(LinkedInPage(page).get_job_results(limit=25)) == 1
