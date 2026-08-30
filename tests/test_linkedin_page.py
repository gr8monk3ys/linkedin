"""Tests for the LinkedIn page object — the layer that talks to LinkedIn.

This was at 0% coverage: the module imported Playwright at module scope, and CI
installs only `--extra dev`. It is import-safe now, so the selector logic runs
here against a Page double (`tests/fake_page.py`).

The recurring theme: a LinkedIn markup change must not look like a quiet page.
"""

import pytest

from linkedin.automation import selectors as sel
from linkedin.automation.linkedin_page import LinkedInPage
from tests.fake_page import FakeCard, FakeElement, FakePage, canonical


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
        page.register_label(sel.LOGIN_EMAIL_LABEL, FakeElement())
        page.register_label(sel.LOGIN_PASSWORD_LABEL, FakeElement())
        page.register_role("button", sel.SIGN_IN_BUTTON, FakeElement())
        return page

    def test_successful_login_fills_and_submits(self, page):
        self._prepare(page)
        assert LinkedInPage(page).login("a@b.c", "pw") is True
        assert page.registry[canonical("label", sel.LOGIN_EMAIL_LABEL)][0].filled == ["a@b.c"]
        assert page.registry[canonical("label", sel.LOGIN_PASSWORD_LABEL)][0].filled == ["pw"]
        assert page.registry[canonical("role", "button", sel.SIGN_IN_BUTTON)][0].clicked == 1

    def test_login_returns_false_when_navigation_never_lands(self, page):
        self._prepare(page)
        page.wait_for_url_fails = True
        assert LinkedInPage(page).login("a@b.c", "pw") is False

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
    def test_direct_connect_button(self, page):
        connect, send = FakeElement(), FakeElement()
        page.register_role("button", sel.CONNECT_BUTTON, connect)
        page.register_role("button", sel.SEND_BUTTON, send)

        assert LinkedInPage(page).send_connection_request() is True
        assert connect.clicked == 1 and send.clicked == 1

    def test_falls_back_to_the_more_menu(self, page):
        more, menu_item, send = FakeElement(), FakeElement(), FakeElement()
        page.register_role("button", sel.MORE_BUTTON, more)
        page.register_role("menuitem", sel.CONNECT_MENU_ITEM, menu_item)
        page.register_role("button", sel.SEND_BUTTON, send)

        assert LinkedInPage(page).send_connection_request() is True
        assert more.clicked == 1 and menu_item.clicked == 1

    def test_no_connect_affordance_at_all(self, page):
        assert LinkedInPage(page).send_connection_request() is False

    def test_more_menu_without_a_connect_item(self, page):
        page.register_role("button", sel.MORE_BUTTON, FakeElement())
        assert LinkedInPage(page).send_connection_request() is False

    def test_note_is_typed_before_sending(self, page):
        note_box = FakeElement()
        page.register_role("button", sel.CONNECT_BUTTON, FakeElement())
        page.register_role("button", sel.ADD_NOTE_BUTTON, FakeElement())
        page.register_role("textbox", sel.ADD_NOTE_TEXTBOX, note_box)
        page.register_role("button", sel.SEND_BUTTON, FakeElement())

        assert LinkedInPage(page).send_connection_request(note="Hi Ada") is True
        assert note_box.filled == ["Hi Ada"]

    def test_missing_send_button_reports_failure(self, page):
        page.register_role("button", sel.CONNECT_BUTTON, FakeElement())
        assert LinkedInPage(page).send_connection_request() is False


class TestSendMessage:
    def test_sends(self, page):
        box, send = FakeElement(), FakeElement()
        page.register_role("button", sel.MESSAGE_BUTTON, FakeElement())
        page.register_role("textbox", sel.MESSAGE_TEXTBOX, box)
        page.register_role("button", sel.SEND_BUTTON, send)

        assert LinkedInPage(page).send_message("hello") is True
        assert box.filled == ["hello"] and send.clicked == 1

    def test_no_message_button(self, page):
        assert LinkedInPage(page).send_message("hello") is False

    def test_message_box_never_appears(self, page):
        page.register_role("button", sel.MESSAGE_BUTTON, FakeElement())
        assert LinkedInPage(page).send_message("hello") is False


class TestCreatePost:
    def _prepare(self, page, with_editor=True, fallback_editor=False):
        page.register_role("button", sel.START_POST_BUTTON, FakeElement())
        if with_editor:
            page.register_role("textbox", sel.POST_EDITOR_TEXTBOX, FakeElement())
        if fallback_editor:
            page.register_css(sel.POST_EDITOR_FALLBACK, FakeElement())
        page.register_role("button", sel.POST_SUBMIT_BUTTON, FakeElement())
        return page

    def test_publishes(self, page):
        self._prepare(page)
        assert LinkedInPage(page).create_post("Shipped a thing") is True
        assert page.registry[canonical("role", "textbox", sel.POST_EDITOR_TEXTBOX)][0].filled == ["Shipped a thing"]

    def test_uses_the_quill_fallback_editor(self, page):
        self._prepare(page, with_editor=False, fallback_editor=True)
        assert LinkedInPage(page).create_post("Shipped") is True
        assert page.registry[canonical("css", sel.POST_EDITOR_FALLBACK)][0].filled == ["Shipped"]

    def test_no_start_post_button(self, page):
        assert LinkedInPage(page).create_post("x") is False

    def test_no_editor_of_either_kind(self, page):
        self._prepare(page, with_editor=False)
        assert LinkedInPage(page).create_post("x") is False

    def test_no_post_button(self, page):
        page.register_role("button", sel.START_POST_BUTTON, FakeElement())
        page.register_role("textbox", sel.POST_EDITOR_TEXTBOX, FakeElement())
        assert LinkedInPage(page).create_post("x") is False


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


class TestLikePost:
    def test_likes_by_index(self, page):
        cards = [_feed_card(author="A"), _feed_card(author="B")]
        _with_feed(page, cards)
        assert LinkedInPage(page).like_post(1) is True
        assert cards[1].children[canonical("role", "button", sel.LIKE_BUTTON)][0].clicked == 1

    def test_out_of_range_index(self, page):
        _with_feed(page, [_feed_card()])
        assert LinkedInPage(page).like_post(5) is False

    def test_already_liked_is_not_unliked(self, page):
        card = _feed_card(liked=True)
        _with_feed(page, [card])
        assert LinkedInPage(page).like_post(0) is False
        assert card.children[canonical("role", "button", sel.LIKE_BUTTON)][0].clicked == 0

    def test_no_cards_records_a_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.like_post(0) is False
        assert "feed_card" in lp.selector_misses


class TestCommentOnPost:
    def test_posts_a_comment(self, page):
        card = _feed_card()
        _with_feed(page, [card])
        assert LinkedInPage(page).comment_on_post(0, "Nice work") is True
        assert card.children[canonical("role", "textbox", sel.COMMENT_TEXTBOX)][0].filled == ["Nice work"]
        assert card.children[canonical("role", "button", sel.COMMENT_SUBMIT_BUTTON)][0].clicked == 1

    def test_out_of_range_index(self, page):
        _with_feed(page, [_feed_card()])
        assert LinkedInPage(page).comment_on_post(3, "hi") is False

    def test_missing_comment_button(self, page):
        _with_feed(page, [FakeCard(None, {})])
        assert LinkedInPage(page).comment_on_post(0, "hi") is False

    def test_comment_box_never_appears(self, page):
        card = FakeCard(None, {canonical("role", "button", sel.COMMENT_BUTTON): [FakeElement()]})
        _with_feed(page, [card])
        assert LinkedInPage(page).comment_on_post(0, "hi") is False


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

    def test_no_cards_records_a_miss(self, page):
        lp = LinkedInPage(page)
        assert lp.get_search_results() == []
        assert "search_result_card" in lp.selector_misses

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



class TestProfileEditing:
    def test_update_headline(self, page):
        field = FakeElement()
        page.register_role("button", sel.EDIT_INTRO_BUTTON, FakeElement())
        page.register_label(sel.HEADLINE_FIELD_LABEL, field)
        page.register_role("button", sel.SAVE_BUTTON, FakeElement())

        assert LinkedInPage(page).update_headline("ML Engineer") is True
        assert field.filled == ["ML Engineer"]

    def test_update_headline_without_edit_button(self, page):
        assert LinkedInPage(page).update_headline("x") is False

    def test_update_headline_without_save_button(self, page):
        page.register_role("button", sel.EDIT_INTRO_BUTTON, FakeElement())
        page.register_label(sel.HEADLINE_FIELD_LABEL, FakeElement())
        assert LinkedInPage(page).update_headline("x") is False

    def test_update_about(self, page):
        box = FakeElement()
        page.register_css(sel.PROFILE_ABOUT_SECTION, FakeElement())
        page.register_role("button", sel.EDIT_ABOUT_BUTTON, FakeElement())
        page.register_role("textbox", None, box)
        page.register_role("button", sel.SAVE_BUTTON, FakeElement())

        assert LinkedInPage(page).update_about("About me") is True
        assert box.filled == ["About me"]

    def test_update_about_without_an_about_section(self, page):
        assert LinkedInPage(page).update_about("x") is False


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

    def test_misses_are_deduplicated(self):
        lp = LinkedInPage(FakePage())
        lp._record_miss("feed_card")
        lp._record_miss("feed_card")
        assert lp.selector_misses == ["feed_card"]


class TestSelectorWarningReachesTheUser:
    """A breakage must reach the terminal, not just an attribute."""

    def test_cli_warns_and_names_the_broken_selectors(self, capsys):
        from linkedin.cli import _close_linkedin_session

        page = FakePage()
        lp = LinkedInPage(page)
        lp.get_feed_posts(max_posts=3)  # empty feed -> feed_card miss

        class Browser:
            closed = False

            def close(self):
                Browser.closed = True

        _close_linkedin_session(Browser(), lp)
        out = capsys.readouterr().out
        assert Browser.closed is True
        assert "markup may have changed" in out
        assert sel.FEED_CARD in out
        assert "selectors.py" in out

    def test_healthy_session_says_nothing(self, capsys):
        from linkedin.cli import _close_linkedin_session

        page = FakePage()
        _with_feed(page, [_feed_card()])
        lp = LinkedInPage(page)
        lp.get_feed_posts(max_posts=1)

        class Browser:
            def close(self):
                pass

        _close_linkedin_session(Browser(), lp)
        assert capsys.readouterr().out == ""

    def test_browser_is_closed_even_if_reporting_fails(self):
        from linkedin.cli import _close_linkedin_session

        class Broken:
            def selector_health(self):
                raise RuntimeError("boom")

        class Browser:
            closed = False

            def close(self):
                Browser.closed = True

        with pytest.raises(RuntimeError):
            _close_linkedin_session(Browser(), Broken())
        assert Browser.closed is True
