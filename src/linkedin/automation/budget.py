"""Daily action budgets, one table, persisted per calendar day.

`Budget.spend(kind, n)` and `Budget.remaining(kind)` over `{kind: cap}`. Caps
live in `limits.json` under the data dir so the ramp (low caps for the first
weeks on an account with no automated history, stepped up later) is a state
change, not a commit. There is no "no budget": a dry run gets an in-memory
budget with the same caps that spends nothing.

Replaces a class that published eight counters in four method families and
made every caller pick the matching pair by hand; one forgot.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from linkedin.data.json_store import load_json, save_json

# Every kind of action LinkedIn could count as activity, with the ramp cap:
# what an account with no automated history should look like for its first
# month. Step them up with `automate limits set <kind> <n>` once metrics are
# clean; LinkedIn's detection weights change in behaviour, not volume.
DEFAULT_CAPS: dict[str, int] = {
    "connection": 0,
    "message": 25,
    "post": 1,
    "reaction": 5,
    "comment": 2,
    "easy_apply": 15,
    "search": 30,
    "profile_view": 50,
    "metrics": 3,
}
KINDS = tuple(DEFAULT_CAPS)

# Counter names the previous usage file used, so today's counts carry over.
_LEGACY_NAMES = {
    "connections_sent": "connection",
    "messages_sent": "message",
    "posts_created": "post",
    "reactions": "reaction",
    "comments_posted": "comment",
    "easy_applies": "easy_apply",
    "searches": "search",
    "profile_views": "profile_view",
}


class UnknownKind(KeyError):
    """A kind not in the caps table — a typo, not a zero budget."""


class Budget:
    """Caps and today's usage for one data dir (or in memory)."""

    def __init__(self, caps: dict[str, int], usage_file: Path | None = None, limits_file: Path | None = None):
        unknown = set(caps) - set(KINDS)
        if unknown:
            raise UnknownKind(sorted(unknown))
        self.caps = {kind: int(caps.get(kind, DEFAULT_CAPS[kind])) for kind in KINDS}
        self.usage_file = usage_file
        self.limits_file = limits_file
        self.today = date.today().isoformat()
        self.used: dict[str, int] = {kind: 0 for kind in KINDS}
        self._load()

    # -- construction -------------------------------------------------------

    @classmethod
    def load(cls, data_dir) -> Budget:
        """Caps from `limits.json` (seeded with the defaults on first use), usage persisted."""
        caps = load_caps(data_dir.limits)
        return cls(caps, usage_file=data_dir.automation_usage, limits_file=data_dir.limits)

    @classmethod
    def in_memory(cls, caps: dict[str, int] | None = None) -> Budget:
        """Same caps, nothing written. What a dry run gets."""
        return cls(dict(caps or DEFAULT_CAPS))

    # -- the interface ------------------------------------------------------

    def can(self, kind: str, n: int = 1) -> bool:
        return self.remaining(kind) >= max(1, n)

    def remaining(self, kind: str) -> int:
        self._check(kind)
        return max(0, self.caps[kind] - self.used[kind])

    def spend(self, kind: str, n: int = 1) -> None:
        """Record `n` actions of `kind`. Persists immediately when file-backed."""
        self._check(kind)
        if n <= 0:
            return
        self.used[kind] += n
        self._persist()

    def set_cap(self, kind: str, cap: int) -> None:
        self._check(kind)
        self.caps[kind] = max(0, int(cap))
        if self.limits_file is not None:
            save_json(self.limits_file, self.caps)

    def summary(self) -> dict[str, dict[str, int]]:
        return {kind: {"cap": self.caps[kind], "used": self.used[kind], "remaining": self.remaining(kind)} for kind in KINDS}

    # -- persistence --------------------------------------------------------

    def _check(self, kind: str) -> None:
        if kind not in self.caps:
            raise UnknownKind(kind)

    def _load(self) -> None:
        if self.usage_file is None:
            return
        try:
            data = json.loads(self.usage_file.read_text())
        except (OSError, ValueError):
            return
        counts = data.get(self.today, {}) if isinstance(data, dict) else {}
        for name, value in counts.items():
            kind = _LEGACY_NAMES.get(name, name)
            if kind in self.used and isinstance(value, int) and value >= 0:
                self.used[kind] = value

    def _persist(self) -> None:
        if self.usage_file is None:
            return
        # Only today: history lives in run logs. Atomic, because a truncated
        # usage file reads back as "no usage today" and hands back a full day.
        try:
            save_json(self.usage_file, {self.today: dict(self.used)})
        except OSError:
            pass


def load_caps(limits_file: Path) -> dict[str, int]:
    """Read caps, seeding the file with the ramp defaults when it does not exist."""
    raw = load_json(limits_file, None)
    if not isinstance(raw, dict):
        save_json(limits_file, DEFAULT_CAPS)
        return dict(DEFAULT_CAPS)
    caps = dict(DEFAULT_CAPS)
    for kind, value in raw.items():
        if kind in caps and isinstance(value, int) and value >= 0:
            caps[kind] = value
    return caps
