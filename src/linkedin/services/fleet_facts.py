"""What the fleet did this week, from public repositories only.

The content decision was building in public from real numbers: merged pull
requests, the repos that moved, what the merge gate let through. Everything
here comes from `gh search` with `--visibility public`, so a private repo's
name can never reach a prompt whose output is published under the user's name,
and every claim in a post is one a reader can verify by clicking through.

Pure apart from the `run` callable, which tests replace.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta

OWNER = "gr8monk3ys"
BOT_MARKERS = ("dependabot", "renovate", "github-actions", "[bot]")


def gh(args: list[str]) -> str:
    """Run `gh` and return stdout. Raises on a non-zero exit."""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=60).stdout


def collect_fleet_facts(days: int = 7, *, owner: str = OWNER, run: Callable[[list[str]], str] = gh, today: date | None = None) -> dict:
    """A week of public activity, shaped for a prompt and for a human to check."""
    today = today or date.today()
    since = (today - timedelta(days=days)).isoformat()

    repos = json.loads(run(["repo", "list", owner, "--visibility", "public", "--no-archived", "--limit", "200", "--json", "name,pushedAt,stargazerCount,description"]))
    merged = json.loads(run([
        "search", "prs", "--owner", owner, "--visibility", "public", "--merged", "--merged-at", f">={since}",
        "--limit", "200", "--json", "repository,title,author,url,number",
    ]))

    public_names = {r["name"] for r in repos}
    merged = [p for p in merged if (p.get("repository") or {}).get("name") in public_names]
    human = [p for p in merged if not _is_bot(p)]
    bots = [p for p in merged if _is_bot(p)]
    by_repo = Counter((p["repository"]["name"]) for p in merged)

    active = sorted(repos, key=lambda r: r.get("pushedAt", ""), reverse=True)[:6]
    return {
        "owner": owner,
        "window_days": days,
        "since": since,
        "until": today.isoformat(),
        "public_repos": len(repos),
        "merged_total": len(merged),
        "merged_by_human": len(human),
        "merged_by_bots": len(bots),
        "repos_touched": len(by_repo),
        "top_repos": [{"name": name, "merged": n} for name, n in by_repo.most_common(5)],
        "recently_pushed": [{"name": r["name"], "pushed_at": r.get("pushedAt", "")[:10], "stars": r.get("stargazerCount", 0), "description": (r.get("description") or "")[:120]} for r in active],
        "sample_titles": [{"repo": p["repository"]["name"], "title": p["title"][:100], "url": p.get("url", "")} for p in human[:8]],
    }


def _is_bot(pr: dict) -> bool:
    login = ((pr.get("author") or {}).get("login") or "").lower()
    return any(marker in login for marker in BOT_MARKERS)


def facts_digest(facts: dict) -> str:
    """The facts as fenced data for a prompt: numbers and names, nothing to obey."""
    lines = [
        f"window: {facts['since']} to {facts['until']} ({facts['window_days']} days)",
        f"public repositories: {facts['public_repos']}",
        f"pull requests merged: {facts['merged_total']} ({facts['merged_by_human']} authored, {facts['merged_by_bots']} from bots via the merge gate)",
        f"repositories that merged something: {facts['repos_touched']}",
    ]
    if facts["top_repos"]:
        lines.append("busiest: " + ", ".join(f"{r['name']} ({r['merged']})" for r in facts["top_repos"]))
    for r in facts["recently_pushed"][:4]:
        lines.append(f"recently pushed: {r['name']} — {r['description'] or 'no description'} (stars {r['stars']})")
    for t in facts["sample_titles"][:6]:
        lines.append(f"merged: [{t['repo']}] {t['title']}")
    return "\n".join(lines)
