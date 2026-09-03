"""One open browser logged into LinkedIn, with named verbs.

Every verb does the same six things: check the budget, pace, navigate, call
the page object, record on success, return an `ActionResult`. That preamble
used to be restated in eleven action files that disagreed on what a dry run
meant and returned five different shapes. Here it exists once.

Import-safe without Playwright or keyring: both are imported inside
`LinkedInSession.open`, so this module imports (and is tested) in CI, which
installs only `--extra dev`.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator, Literal

from linkedin.automation.budget import Budget
from linkedin.automation.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from linkedin.automation.browser import BrowserManager
    from linkedin.automation.linkedin_page import LinkedInPage
    from linkedin.data.paths import DataDir

Status = Literal["ok", "skipped", "refused", "failed"]


class AutomationUnavailable(RuntimeError):
    """Playwright is not installed: `uv sync --extra automation && uv run playwright install chromium`."""


class LoginFailed(RuntimeError):
    """No saved session, no working credentials, and nobody at the window."""


@dataclass(frozen=True)
class ActionResult:
    """What every verb returns.

    `ok`: it happened. `skipped`: a normal absence (no Connect button, already
    connected, LinkedIn's own empty state). `refused`: a rule said no (budget,
    empty text). `failed`: a raise or a selector miss. Truthy only on `ok`.
    """

    status: Status
    reason: str = ""
    data: Any = None

    def __bool__(self) -> bool:
        return self.status == "ok"

    @property
    def dry_run(self) -> bool:
        return self.reason == "dry_run"


def _ok(data: Any = None, reason: str = "") -> ActionResult:
    return ActionResult("ok", reason, data)


def _skipped(reason: str, data: Any = None) -> ActionResult:
    return ActionResult("skipped", reason, data)


def _refused(reason: str, data: Any = None) -> ActionResult:
    return ActionResult("refused", reason, data)


def _failed(reason: str, data: Any = None) -> ActionResult:
    return ActionResult("failed", reason, data)


class LinkedInSession:
    """The verbs. Construct through `open()`; tests hand in a page and a budget."""

    def __init__(self, page: LinkedInPage, budget: Budget, *, pacer: RateLimiter | None = None, dry_run: bool = False, browser: BrowserManager | None = None):
        self.page = page
        self.budget = budget
        self.pacer = pacer or RateLimiter()
        self.dry_run = dry_run
        self.browser = browser

    # -- lifecycle ----------------------------------------------------------

    @classmethod
    @contextmanager
    def open(
        cls,
        data_dir: DataDir,
        *,
        headless: bool = False,
        dry_run: bool = False,
        on_login_needed: Callable[[LinkedInPage], bool] | None = None,
    ) -> Iterator[LinkedInSession]:
        """Start a browser, establish a login, yield the session, always close.

        A dry run gets an in-memory budget with the same caps: it navigates and
        reads, never writes, never spends. When automatic login fails and
        `on_login_needed` is given, it is called with the page (the CLI pauses
        for a person at the window) and must return whether login succeeded.
        """
        try:
            from linkedin.automation.browser import BrowserManager
            from linkedin.automation.config import AutomationConfig
            from linkedin.automation.linkedin_page import LinkedInPage
        except ImportError as exc:
            raise AutomationUnavailable(str(exc)) from exc

        budget = Budget.in_memory(Budget.load(data_dir).caps) if dry_run else Budget.load(data_dir)
        browser = BrowserManager(AutomationConfig(headless=headless, cookies_path=str(data_dir.li_session)))
        try:
            page = LinkedInPage(browser.start())
            if not _login(browser, page):
                if headless or on_login_needed is None or not on_login_needed(page):
                    raise LoginFailed("Not logged in")
                browser.save_session()
            yield cls(page, budget, dry_run=dry_run, browser=browser)
        finally:
            browser.close()

    def selector_health(self) -> dict:
        return self.page.selector_health()

    # -- internals ----------------------------------------------------------

    def _write(
        self, kind: str, act: Callable[[], bool], *, skipped_reason: str, navigate: Callable[[], None] | None = None, n: int = 1
    ) -> ActionResult:
        """The preamble for a write: budget → pace → navigate → act → record on success.

        Budget before navigation: an exhausted budget must not cost a page load,
        and a dry run navigates so selector health still has something to report.
        """
        if not self.budget.can(kind, n):
            return _refused(f"daily {kind} limit reached")
        self.pacer.wait()
        try:
            if navigate is not None:
                navigate()
            if self.dry_run:
                return _ok(reason="dry_run")
            done = act()
        except Exception as exc:  # a raise from the page object is a breakage, not an absence
            return _failed(f"{type(exc).__name__}: {exc}")
        if not done:
            return _skipped(skipped_reason)
        self.budget.spend(kind, n)
        return _ok()

    def _read(self, kind: str, act: Callable[[], Any]) -> ActionResult:
        """The preamble for a read: budget → pace → read. A dry run reads but does not spend."""
        if not self.budget.can(kind):
            return _refused(f"daily {kind} limit reached")
        self.pacer.wait()
        try:
            data = act()
        except Exception as exc:
            return _failed(f"{type(exc).__name__}: {exc}")
        if not self.dry_run:
            self.budget.spend(kind)
        return _ok(data)

    # -- writes -------------------------------------------------------------

    def connect(self, profile_url: str, note: str = "") -> ActionResult:
        return self._write(
            "connection",
            lambda: self.page.send_connection_request(note=note),
            navigate=lambda: self.page.goto_profile(profile_url),
            skipped_reason="no Connect button, or already connected/pending",
        )

    def message(self, profile_url: str, text: str) -> ActionResult:
        if not text.strip():
            return _refused("empty message")
        return self._write(
            "message",
            lambda: self.page.send_message(text),
            navigate=lambda: self.page.goto_profile(profile_url),
            skipped_reason="not connected, or message dialog not found",
        )

    def post(self, text: str) -> ActionResult:
        if not text.strip():
            return _refused("empty post")
        return self._write("post", lambda: self.page.create_post(text), skipped_reason="post editor not found")

    def like_post(self, post_index: int) -> ActionResult:
        """Like one feed post already on screen (the feed pipeline)."""
        return self._write("reaction", lambda: self.page.like_post(post_index), skipped_reason="already liked, or no Like button")

    def comment(self, post_index: int, text: str) -> ActionResult:
        if not text.strip():
            return _refused("empty comment")
        return self._write("comment", lambda: self.page.comment_on_post(post_index, text), skipped_reason="comment box not found")

    def react(self, count: int, profile_url: str = "") -> ActionResult:
        """Like up to `count` posts: a contact's recent activity, or the home feed.

        Asks for no more than the budget has left rather than overshooting,
        and records exactly what was liked. `data` is the number liked.
        """
        count = min(count, self.budget.remaining("reaction"))
        if count <= 0:
            return _refused("daily reaction limit reached", data=0)
        self.pacer.wait()
        if profile_url:
            self.page.goto_recent_activity(profile_url)
        else:
            self.page.goto_feed()
        if self.dry_run:
            return _ok(count, reason="dry_run")
        try:
            liked = int(self.page.like_visible_posts(count))
        except Exception as exc:
            return _failed(f"{type(exc).__name__}: {exc}", data=0)
        self.budget.spend("reaction", liked)
        return _ok(liked) if liked else _skipped("no posts to like", data=0)

    def sync_profile(self, headline: str = "", about: str = "") -> ActionResult:
        """Push headline and/or About. `data` is {field: "updated" | "failed" | "dry_run"} for the fields given."""
        if not headline and not about:
            return _refused("nothing to sync")
        self.pacer.wait()
        results: dict[str, str] = {}
        for field, value, update in (("headline", headline, self.page.update_headline), ("about", about, self.page.update_about)):
            if not value:
                continue
            if self.dry_run:
                results[field] = "dry_run"
                continue
            try:
                results[field] = "updated" if update(value) else "failed"
            except Exception as exc:
                results[field] = f"failed: {type(exc).__name__}"
        if self.dry_run:
            return _ok(results, reason="dry_run")
        if any(v != "updated" for v in results.values()):
            return _failed("LinkedIn's profile editor did not accept every change", data=results)
        return _ok(results)

    def easy_apply(self, job_url: str, resume_path: str = "", submit: bool = False) -> ActionResult:
        """Run the Easy Apply flow. Budget is spent only on a submitted application.

        `data` is the page object's result dict; `status` maps its `status`:
        submitted → ok; ready_to_submit / needs_manual_input / no_easy_apply →
        skipped with that reason; anything else → failed.
        """
        if not job_url:
            return _refused("application has no job URL")
        if submit and not self.budget.can("easy_apply"):
            return _refused("daily easy_apply limit reached")
        self.pacer.wait()
        if self.dry_run:
            return _ok({"status": "dry_run", "detail": f"Would Easy Apply to {job_url}"}, reason="dry_run")
        self.page.goto_profile(job_url)  # generic navigation; any URL
        try:
            result = self.page.easy_apply(resume_path=resume_path, submit=submit)
        except Exception as exc:
            return _failed(f"{type(exc).__name__}: {exc}")
        return self.record_easy_apply_outcome(result)

    def record_easy_apply_outcome(self, result: dict) -> ActionResult:
        """Classify a page-object Easy Apply result and spend the budget if it was submitted.

        Also used by the CLI after a person finishes a wizard step by hand.
        """
        status = result.get("status", "error")
        if status == "submitted":
            self.budget.spend("easy_apply")
            return _ok(result)
        if status in {"ready_to_submit", "needs_manual_input", "no_easy_apply"}:
            return _skipped(status, data=result)
        return _failed(result.get("detail", status), data=result)

    # -- reads --------------------------------------------------------------

    def search(self, query: str, limit: int = 20, network: str = "") -> ActionResult:
        """People search. `data` is a list of {name, headline, linkedin_url}."""
        def act():
            self.page.goto_search(query, network=network)
            return self.page.get_search_results()[:limit]
        return self._read("search", act)

    def jobs(self, query: str, location: str = "", limit: int = 25) -> ActionResult:
        """Job search. `data` is a list of raw job dicts."""
        def act():
            self.page.goto_job_search(query, location=location)
            return self.page.get_job_results(limit=limit)
        return self._read("search", act)

    def scrape(self, profile_url: str) -> ActionResult:
        """One profile. `data` is {name, headline, location, about}; skipped when no name could be read."""
        def act():
            self.page.goto_profile(profile_url)
            return self.page.scrape_profile()
        result = self._read("profile_view", act)
        if result and not result.data.get("name"):
            return _skipped("no profile name on the page", data=result.data)
        return result

    def inbox(self, thread_limit: int = 25) -> ActionResult:
        """Message threads and sent invitations. `data` is {"threads": [...], "pending_invitations": [...] | None}.

        `pending_invitations` is None whenever the list was not read — including
        when the budget refused before we looked. Acceptance is inferred from an
        invitation's absence, so "did not look" and "nothing pending" must never
        collapse into the same value.
        """
        if not self.budget.can("search"):
            return _refused("daily search limit reached", data={"threads": [], "pending_invitations": None})

        def act():
            self.pacer.wait()
            self.page.goto_messaging()
            threads = self.page.get_message_threads(limit=thread_limit)
            self.pacer.wait()
            self.page.goto_sent_invitations()
            pending = self.page.get_pending_sent_invitations()
            return {"threads": threads, "pending_invitations": pending}

        try:
            data = act()
        except Exception as exc:
            return _failed(f"{type(exc).__name__}: {exc}", data={"threads": [], "pending_invitations": None})
        if not self.dry_run:
            self.budget.spend("search")
        return _ok(data)


# -- login ----------------------------------------------------------------------


def _login(browser: BrowserManager, page: LinkedInPage) -> bool:
    """Establish a login. On failure the browser is left on a page a human can use.

    A saved session is checked before credentials, not after: it is sufficient
    on its own, and the keyring is empty for anyone who logged in by hand.
    A failed login often lands on a 2FA or security checkpoint, and navigating
    back to /login would throw that challenge away — so only go there when we
    ended up off LinkedIn entirely.
    """
    if page.is_logged_in():
        return True
    from linkedin.automation.credentials import get_credentials

    creds = get_credentials()
    if not creds:
        page.goto_login()
        return False
    ok = page.login(*creds)
    if ok:
        browser.save_session()
    elif not _on_linkedin(page):
        page.goto_login()
    return ok


def _on_linkedin(page: LinkedInPage) -> bool:
    try:
        return "linkedin.com" in (page.page.url or "")
    except Exception:
        return False


def setup_credentials(email: str, password: str) -> None:
    """Store credentials in the system keyring."""
    from linkedin.automation.credentials import store_credentials

    store_credentials(email, password)
