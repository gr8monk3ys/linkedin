"""LinkedInSession: one preamble for every verb, one result shape, one dry run."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from linkedin.automation.budget import Budget
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.session import ActionResult, AutomationUnavailable, LinkedInSession, LoginFailed
from linkedin.data.paths import DataDir


class NoPacer(RateLimiter):
    def __init__(self):
        super().__init__(0, 0)
        self.waits = 0

    def wait(self):
        self.waits += 1
        return 0.0


def make(caps=None, dry_run=False, page=None):
    page = page or MagicMock()
    return LinkedInSession(page, Budget.in_memory(caps), pacer=NoPacer(), dry_run=dry_run), page


# -- the result shape ------------------------------------------------------------


def test_result_is_truthy_only_on_ok():
    assert ActionResult("ok")
    assert not ActionResult("skipped", "no button")
    assert not ActionResult("refused", "limit")
    assert not ActionResult("failed", "boom")
    assert ActionResult("ok", "dry_run").dry_run


# -- writes ----------------------------------------------------------------------


def test_connect_navigates_paces_acts_records():
    s, page = make({"connection": 1})
    page.send_connection_request.return_value = True
    r = s.connect("https://li/in/a", note="hi")
    assert r
    page.goto_profile.assert_called_once_with("https://li/in/a")
    page.send_connection_request.assert_called_once_with(note="hi")
    assert s.pacer.waits == 1
    assert s.budget.remaining("connection") == 0


def test_connect_refused_before_navigating_when_budget_is_out():
    s, page = make({"connection": 0})
    r = s.connect("https://li/in/a")
    assert r.status == "refused" and "connection" in r.reason
    page.goto_profile.assert_not_called()
    page.send_connection_request.assert_not_called()


def test_a_missing_button_is_skipped_and_spends_nothing():
    s, page = make({"connection": 1})
    page.send_connection_request.return_value = False
    r = s.connect("u")
    assert r.status == "skipped"
    assert s.budget.remaining("connection") == 1


def test_a_raise_is_failed_not_skipped():
    """A strict-mode violation is a breakage; it must not read as 'no button'."""
    s, page = make({"connection": 1})
    page.send_connection_request.side_effect = RuntimeError("strict mode violation")
    r = s.connect("u")
    assert r.status == "failed" and "strict mode" in r.reason
    assert s.budget.remaining("connection") == 1


def test_dry_run_navigates_but_never_writes_or_spends():
    s, page = make({"connection": 1, "message": 1, "post": 1}, dry_run=True)
    assert s.connect("u").dry_run
    assert s.message("u", "hi").dry_run
    assert s.post("text").dry_run
    page.goto_profile.assert_called()
    page.send_connection_request.assert_not_called()
    page.send_message.assert_not_called()
    page.create_post.assert_not_called()
    assert s.budget.summary()["connection"]["used"] == 0
    assert s.budget.summary()["post"]["used"] == 0


def test_empty_text_is_refused_without_touching_the_page():
    s, page = make({"message": 1, "post": 1, "comment": 1})
    assert s.message("u", "  ").status == "refused"
    assert s.post("").status == "refused"
    assert s.comment(0, "").status == "refused"
    page.goto_profile.assert_not_called()


def test_post_records_on_success_only():
    s, page = make({"post": 1})
    page.create_post.return_value = False
    assert s.post("x").status == "skipped"
    assert s.budget.remaining("post") == 1
    page.create_post.return_value = True
    assert s.post("x")
    assert s.budget.remaining("post") == 0


def test_react_asks_for_no_more_than_the_budget_has_left():
    s, page = make({"reaction": 2})
    page.like_visible_posts.return_value = 2
    r = s.react(5, profile_url="u")
    assert r and r.data == 2
    page.goto_recent_activity.assert_called_once_with("u")
    page.like_visible_posts.assert_called_once_with(2)
    assert s.budget.remaining("reaction") == 0
    r = s.react(1)
    assert r.status == "refused" and r.data == 0
    page.goto_feed.assert_not_called()


def test_react_records_what_was_actually_liked():
    s, page = make({"reaction": 5})
    page.like_visible_posts.return_value = 1
    r = s.react(3)
    page.goto_feed.assert_called_once()
    assert r.data == 1 and s.budget.remaining("reaction") == 4


def test_react_dry_run_reports_the_would_be_count():
    s, page = make({"reaction": 5}, dry_run=True)
    r = s.react(3)
    assert r.dry_run and r.data == 3
    page.like_visible_posts.assert_not_called()


def test_sync_profile_reports_per_field_and_fails_if_any_did():
    s, page = make()
    page.update_headline.return_value = True
    page.update_about.return_value = False
    r = s.sync_profile(headline="h", about="a")
    assert r.status == "failed"
    assert r.data == {"headline": "updated", "about": "failed"}
    assert s.sync_profile().status == "refused"
    page.update_headline.return_value = True
    assert s.sync_profile(headline="h").data == {"headline": "updated"}


def test_easy_apply_spends_only_on_submitted():
    s, page = make({"easy_apply": 1})
    page.easy_apply.return_value = {"status": "ready_to_submit", "detail": "review"}
    r = s.easy_apply("https://li/jobs/1", resume_path="r.pdf", submit=False)
    assert r.status == "skipped" and r.reason == "ready_to_submit"
    assert s.budget.remaining("easy_apply") == 1
    page.easy_apply.return_value = {"status": "submitted", "detail": "ok"}
    assert s.easy_apply("https://li/jobs/1", submit=True)
    assert s.budget.remaining("easy_apply") == 0
    assert s.easy_apply("https://li/jobs/1", submit=True).status == "refused"
    assert s.easy_apply("").status == "refused"


def test_easy_apply_review_step_does_not_need_budget():
    """Filling the form without submitting costs nothing; only submit is gated."""
    s, page = make({"easy_apply": 0})
    page.easy_apply.return_value = {"status": "ready_to_submit"}
    assert s.easy_apply("u", submit=False).status == "skipped"


# -- reads -----------------------------------------------------------------------


def test_search_paces_reads_and_spends_the_search_budget():
    s, page = make({"search": 1})
    page.get_search_results.return_value = [{"name": "A"}, {"name": "B"}]
    r = s.search("ml", limit=1)
    assert r and r.data == [{"name": "A"}]
    page.goto_search.assert_called_once_with("ml", network="")
    assert s.budget.remaining("search") == 0
    assert s.search("ml").status == "refused"


def test_jobs_passes_the_limit_down():
    s, page = make({"search": 1})
    page.get_job_results.return_value = [{"title": "x"}]
    r = s.jobs("ml", location="LA", limit=7)
    page.goto_job_search.assert_called_once_with("ml", location="LA")
    page.get_job_results.assert_called_once_with(limit=7)
    assert r.data == [{"title": "x"}]


def test_reads_in_dry_run_happen_but_spend_nothing():
    s, page = make({"search": 1}, dry_run=True)
    page.get_search_results.return_value = [{"name": "A"}]
    assert s.search("ml").data == [{"name": "A"}]
    assert s.budget.remaining("search") == 1


def test_scrape_without_a_name_is_skipped():
    s, page = make({"profile_view": 2})
    page.scrape_profile.return_value = {}
    assert s.scrape("u").status == "skipped"
    page.scrape_profile.return_value = {"name": "Jane"}
    assert s.scrape("u").data == {"name": "Jane"}


def test_inbox_visits_both_surfaces_and_preserves_none():
    s, page = make({"search": 1})
    page.get_message_threads.return_value = [{"name": "R"}]
    page.get_pending_sent_invitations.return_value = None
    r = s.inbox(thread_limit=3)
    assert r
    page.goto_messaging.assert_called_once()
    page.get_message_threads.assert_called_once_with(limit=3)
    page.goto_sent_invitations.assert_called_once()
    assert r.data == {"threads": [{"name": "R"}], "pending_invitations": None}
    assert s.pacer.waits == 2


def test_inbox_refused_by_budget_reports_unreadable_invitations():
    """'We did not look' must never collapse into 'nothing is pending'."""
    s, page = make({"search": 0})
    r = s.inbox()
    assert r.status == "refused"
    assert r.data["pending_invitations"] is None
    page.goto_messaging.assert_not_called()


# -- open() ----------------------------------------------------------------------


def _fake_stack(monkeypatch, *, logged_in=True, login_ok=False):
    browser = MagicMock()
    page = MagicMock()
    page.is_logged_in.return_value = logged_in
    page.login.return_value = login_ok
    browser.start.return_value = MagicMock()
    import linkedin.automation.session as sess

    monkeypatch.setattr("linkedin.automation.browser.BrowserManager", lambda config: browser)
    monkeypatch.setattr("linkedin.automation.linkedin_page.LinkedInPage", lambda raw: page)
    monkeypatch.setattr(sess, "_login", lambda b, p: p.is_logged_in())
    return browser, page


def test_open_yields_a_logged_in_session_and_closes(monkeypatch, tmp_path):
    browser, page = _fake_stack(monkeypatch)
    with LinkedInSession.open(DataDir(tmp_path), headless=True) as s:
        assert s.page is page
        assert not s.dry_run
        assert s.budget.usage_file == DataDir(tmp_path).automation_usage
    browser.close.assert_called_once()


def test_open_dry_run_gets_an_in_memory_budget_with_the_same_caps(monkeypatch, tmp_path):
    _fake_stack(monkeypatch)
    d = DataDir(tmp_path)
    Budget.load(d).set_cap("reaction", 9)
    with LinkedInSession.open(d, dry_run=True) as s:
        assert s.dry_run
        assert s.budget.caps["reaction"] == 9
        assert s.budget.usage_file is None


def test_open_headless_login_failure_raises_and_closes(monkeypatch, tmp_path):
    browser, _ = _fake_stack(monkeypatch, logged_in=False)
    with pytest.raises(LoginFailed):
        with LinkedInSession.open(DataDir(tmp_path), headless=True):
            pass
    browser.close.assert_called_once()


def test_open_hands_the_window_to_a_person_and_saves_the_session(monkeypatch, tmp_path):
    browser, page = _fake_stack(monkeypatch, logged_in=False)
    seen = []

    def person_logs_in(p):
        seen.append(p)
        return True

    with LinkedInSession.open(DataDir(tmp_path), on_login_needed=person_logs_in) as s:
        assert s.page is page
    assert seen == [page]
    browser.save_session.assert_called_once()
    browser.close.assert_called_once()


def test_open_person_gives_up_raises(monkeypatch, tmp_path):
    browser, _ = _fake_stack(monkeypatch, logged_in=False)
    with pytest.raises(LoginFailed):
        with LinkedInSession.open(DataDir(tmp_path), on_login_needed=lambda p: False):
            pass
    browser.close.assert_called_once()


def test_open_closes_the_browser_when_the_body_raises(monkeypatch, tmp_path):
    """A raise at the page object must not leak a running Chromium."""
    browser, _ = _fake_stack(monkeypatch)
    with pytest.raises(RuntimeError):
        with LinkedInSession.open(DataDir(tmp_path)):
            raise RuntimeError("strict mode")
    browser.close.assert_called_once()


def test_open_without_playwright_is_a_named_error(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def no_playwright(name, *a, **k):
        if name == "linkedin.automation.browser":
            raise ImportError("No module named 'playwright'")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_playwright)
    with pytest.raises(AutomationUnavailable):
        with LinkedInSession.open(DataDir(tmp_path)):
            pass


# -- login ordering --------------------------------------------------------------


def test_login_checks_the_saved_session_before_the_keyring(monkeypatch):
    from linkedin.automation.session import _login

    page = MagicMock()
    page.is_logged_in.return_value = True
    called = []
    monkeypatch.setattr("linkedin.automation.credentials.get_credentials", lambda: called.append(1))
    assert _login(MagicMock(), page)
    assert called == []


def test_login_without_credentials_lands_on_the_login_page(monkeypatch):
    from linkedin.automation.session import _login

    page = MagicMock()
    page.is_logged_in.return_value = False
    monkeypatch.setattr("linkedin.automation.credentials.get_credentials", lambda: None)
    assert not _login(MagicMock(), page)
    page.goto_login.assert_called_once()


def test_failed_login_keeps_a_checkpoint_page(monkeypatch):
    """A 2FA challenge is the page the person needs; do not navigate away from it."""
    from linkedin.automation.session import _login

    page = MagicMock()
    page.is_logged_in.return_value = False
    page.login.return_value = False
    page.page.url = "https://www.linkedin.com/checkpoint/challenge"
    monkeypatch.setattr("linkedin.automation.credentials.get_credentials", lambda: ("e", "p"))
    assert not _login(MagicMock(), page)
    page.goto_login.assert_not_called()


@contextmanager
def _noop():
    yield
