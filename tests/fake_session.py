"""A second adapter at the session port.

`LinkedInSession` is the interface the CLI drives; this fake satisfies it with
scripted results and records every call, so CLI tests check what a command
asked the session to do rather than which page methods a MagicMock answered
vacuously. Script a verb with `fake.results["connect"] = ActionResult(...)`;
anything unscripted returns `ok`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from linkedin.automation.budget import Budget
from linkedin.automation.session import ActionResult

VERBS = (
    "connect",
    "message",
    "post",
    "like_post",
    "comment",
    "react",
    "sync_profile",
    "easy_apply",
    "search",
    "jobs",
    "scrape",
    "inbox",
    "metrics",
)


class FakeSession:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.budget = Budget.in_memory()
        self.page = MagicMock()
        self.calls: list[tuple[str, tuple, dict]] = []
        self.results: dict[str, ActionResult] = {}
        self.health: dict = {"healthy": True, "misses": [], "selectors": {}}
        self.closed = False
        self.opened_with: dict[str, Any] = {}

    def selector_health(self) -> dict:
        return self.health

    def _verb(self, name, *args, **kwargs) -> ActionResult:
        self.calls.append((name, args, kwargs))
        if name in self.results:
            return self.results[name]
        if self.dry_run:
            return ActionResult("ok", "dry_run", None)
        return ActionResult("ok")

    def calls_to(self, name: str) -> list[tuple[tuple, dict]]:
        return [(a, k) for n, a, k in self.calls if n == name]

    def record_easy_apply_outcome(self, result: dict) -> ActionResult:
        status = result.get("status")
        if status == "submitted":
            self.budget.spend("easy_apply")
            return ActionResult("ok", data=result)
        if status in {"ready_to_submit", "needs_manual_input", "no_easy_apply"}:
            return ActionResult("skipped", status, result)
        return ActionResult("failed", result.get("detail", ""), result)


for _name in VERBS:
    setattr(FakeSession, _name, (lambda n: lambda self, *a, **k: self._verb(n, *a, **k))(_name))


def install(monkeypatch, fake: FakeSession) -> FakeSession:
    """Make `LinkedInSession.open` yield `fake`, recording how it was opened."""
    from linkedin.automation import session as session_mod

    @contextmanager
    def fake_open(data_dir, *, headless=False, dry_run=False, on_login_needed=None):
        fake.opened_with = {
            "data_dir": data_dir,
            "headless": headless,
            "dry_run": dry_run,
            "on_login_needed": on_login_needed,
        }
        fake.dry_run = dry_run
        try:
            yield fake
        finally:
            fake.closed = True

    monkeypatch.setattr(session_mod.LinkedInSession, "open", fake_open)
    return fake
