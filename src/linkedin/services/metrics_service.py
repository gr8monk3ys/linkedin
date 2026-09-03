"""Account metrics over time: one row per day, None where a number could not be read.

The growth goal is measured here. A missing value stays None so a selector
that stopped matching shows up as a gap in the series, not as a collapse to
zero — the same rule as the unreadable invitation list, in a chart.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from linkedin.data.json_store import load_json, save_json

FIELDS = ("followers", "connections", "profile_views", "post_impressions", "search_appearances", "ssi")


class MetricsService:
    def __init__(self, metrics_file: Path, post_repo):
        self.path = metrics_file
        self.posts = post_repo

    def rows(self) -> list[dict]:
        raw = load_json(self.path, [])
        return sorted((r for r in raw if isinstance(r, dict) and r.get("date")), key=lambda r: r["date"])

    def record(self, row: dict, *, day: dt.date | None = None) -> dict:
        """Upsert today's row. Per-post impressions land on the post records."""
        day = (day or dt.date.today()).isoformat()
        entry = {"date": day, **{f: row.get(f) for f in FIELDS}}
        rows = [r for r in self.rows() if r["date"] != day] + [entry]
        save_json(self.path, sorted(rows, key=lambda r: r["date"]))
        for urn, impressions in (row.get("posts") or {}).items():
            for post in self.posts.list_all():
                if post.get("urn") == urn and impressions is not None:
                    post["impressions"] = impressions
                    post["impressions_at"] = day
                    self.posts.update(post)
        return entry

    def latest(self) -> dict | None:
        rows = self.rows()
        return rows[-1] if rows else None

    def delta(self, field: str, days: int = 7) -> int | None:
        """Change in `field` against the newest row at least `days` old, or None."""
        rows = self.rows()
        if not rows or rows[-1].get(field) is None:
            return None
        cutoff = (dt.date.fromisoformat(rows[-1]["date"]) - dt.timedelta(days=days)).isoformat()
        older = [r for r in rows if r["date"] <= cutoff and r.get(field) is not None]
        if not older:
            return None
        return rows[-1][field] - older[-1][field]

    def summary(self, days: int = 7) -> list[dict]:
        latest = self.latest()
        if not latest:
            return []
        return [{"metric": f, "value": latest.get(f), "delta": self.delta(f, days)} for f in FIELDS]

    def post_rows(self) -> list[dict]:
        return [p for p in self.posts.list_all() if p.get("urn")]
