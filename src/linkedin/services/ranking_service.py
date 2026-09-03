"""Rank contacts by how much they matter for the target role.

The connection budget is the scarcest thing this tool spends: a handful of
invitations a day, capped again by LinkedIn per week. Ranking decides who gets
them. A pinned contact is exempt — it ranks at the top and never appears in
the bottom list, whatever the score says, so the people you want to keep
following are never crowded out by the arithmetic.

Pure: dicts in, ranked rows out. Scores are 0–100 with named reasons, so the
plan can say *why* someone is first.
"""

from __future__ import annotations

import re

PINNED_FIELD = "pinned"

#: Titles on the hiring side of the target role. Weighted by how directly the
#: person can turn a conversation into an interview.
_HIRING_TITLES = (
    (re.compile(r"\b(hiring manager|head of|director|vp|vice president|cto|chief)\b", re.I), 30, "decision-maker title"),
    (re.compile(r"\b(engineering manager|manager, engineering|eng manager|team lead|staff|principal)\b", re.I), 25, "hiring-side engineering title"),
    (re.compile(r"\b(recruit|talent|sourcer|people ops)\w*", re.I), 25, "recruiter"),
)
_ENGINEER = re.compile(r"\b(engineer|developer|architect|scientist|sre|devops)\b", re.I)

_RELATIONSHIP = {
    "call_scheduled": (20, "already talking"),
    "responded": (20, "replied"),
    "connected": (15, "connected"),
    "messaged": (10, "messaged"),
    "connection_sent": (5, "invitation pending"),
    "not_contacted": (0, ""),
}
_COMPANY_PRIORITY = {"high": 30, "medium": 20, "low": 10}


_STOPWORDS = {"of", "in", "at", "and", "the", "to", "for", "on", "or", "ii", "iii"}


def _tokens(text: str) -> set[str]:
    """Words worth matching on. Two-letter tokens stay because "AI" and "ML" are industries."""
    return {w for w in re.findall(r"[a-z][a-z+#.]*", (text or "").lower()) if len(w) >= 2 and w not in _STOPWORDS}


def score_contact(contact: dict, profile: dict | None, companies: list[dict]) -> tuple[int, list[str]]:
    """(score 0–100, reasons). Pinned contacts score 100 with the reason 'pinned'."""
    if contact.get(PINNED_FIELD):
        return 100, ["pinned"]

    profile = profile or {}
    title = contact.get("title", "") or ""
    reasons: list[str] = []
    score = 0

    # -- role relevance (≤35)
    role = 0
    for pattern, points, why in _HIRING_TITLES:
        if pattern.search(title):
            role, reason = max(role, points), why
            if points == role:
                role_reason = reason
    target_tokens = _tokens(profile.get("target_role", ""))
    title_tokens = _tokens(title)
    if target_tokens and target_tokens <= title_tokens:
        if role < 20:
            role, role_reason = 20, "same role as target"
        else:
            role, role_reason = min(35, role + 5), f"{role_reason}, in the target role"
    elif role == 0 and _ENGINEER.search(title):
        role, role_reason = 10, "engineer"
    if role:
        score += role
        reasons.append(role_reason)

    # -- company (≤30)
    company_name = (contact.get("company") or "").strip().lower()
    match = None
    for company in companies:
        if contact.get("company_id") and company.get("id") == contact.get("company_id"):
            match = company
            break
        if company_name and (company.get("name") or "").strip().lower() == company_name:
            match = company
    if match:
        points = _COMPANY_PRIORITY.get(str(match.get("priority", "medium")).lower(), 20)
        score += points
        reasons.append(f"{match.get('priority', 'medium')}-priority company")

    # -- industry (≤15)
    industry_tokens = _tokens(profile.get("industries", "")) - {"and", "the"}
    haystack = _tokens(" ".join([title, contact.get("company", "") or "", contact.get("notes", "") or ""]))
    hits = industry_tokens & haystack
    if hits:
        score += min(15, 5 * len(hits))
        reasons.append("industry overlap: " + ", ".join(sorted(hits)[:3]))

    # -- relationship (≤20, +5 for a referral)
    points, why = _RELATIONSHIP.get(contact.get("status", ""), (0, ""))
    if points:
        score += points
        reasons.append(why)
    if contact.get("referral_contact_id"):
        score += 5
        reasons.append("referred")

    return min(100, score), reasons or ["no signal"]


def rank_contacts(contacts: list[dict], profile: dict | None, companies: list[dict]) -> list[dict]:
    """Every contact with its score and reasons, best first; pinned first of all."""
    rows = []
    for contact in contacts:
        score, reasons = score_contact(contact, profile, companies)
        rows.append({
            "contact_id": contact.get("id"),
            "name": contact.get("name", ""),
            "title": contact.get("title", ""),
            "company": contact.get("company", ""),
            "status": contact.get("status", ""),
            "pinned": bool(contact.get(PINNED_FIELD)),
            "score": score,
            "reasons": reasons,
        })
    rows.sort(key=lambda r: (not r["pinned"], -r["score"], r["name"].lower()))
    return rows


def bottom(rows: list[dict], limit: int) -> list[dict]:
    """The lowest-ranked contacts that are not pinned: candidates to stop spending on."""
    return sorted((r for r in rows if not r["pinned"]), key=lambda r: (r["score"], r["name"].lower()))[:limit]


def connection_bonus(score: int) -> int:
    """How much a `send_connection` action's priority rises with rank (0–25).

    The base priority is 60; a top-ranked stranger beats a mid-ranked one for
    the day's invitations, and a pinned one beats both.
    """
    return score // 4


class RankingService:
    """The ranker over this app's repos."""

    def __init__(self, contact_repo, company_repo, profile_repo):
        self.contacts = contact_repo
        self.companies = company_repo
        self.profiles = profile_repo

    def rank(self) -> list[dict]:
        return rank_contacts(self.contacts.list_all(), self.profiles.get(), self.companies.list_all())

    def scores(self) -> dict[int, int]:
        return {row["contact_id"]: row["score"] for row in self.rank()}

    def bottom(self, limit: int = 10) -> list[dict]:
        return bottom(self.rank(), limit)
