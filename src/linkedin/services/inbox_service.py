"""Turn what LinkedIn shows into proposed pipeline transitions.

Every other automation action in this package is outbound. Without something
reading back, a contact is frozen at the status it was created with:
`connection_sent` can only become `connected` if a human types it, which is why
nine real contacts sat unchanged for days while the planner correctly reported
nothing to do.

This module is the inbound edge, and it is deliberately pure — dicts in,
proposals out, no browser and no repo. The matching logic here is the part that
can corrupt the CRM, so it is the part that has to be testable without a page.

Nothing here applies a transition. A misread page must not be able to rewrite
real contacts, so proposals are persisted and confirmed by a human, the same way
`automation_service.engage_feed` gates an AI comment before it is published.
"""

from __future__ import annotations

import datetime as dt
import re
from datetime import datetime

from linkedin.services.contact_service import parse_iso_date

#: Statuses a reply can advance. `responded` is excluded: a contact already
#: there has nothing to learn from another message.
REPLY_ADVANCES_FROM = frozenset({"not_contacted", "connection_sent", "connected", "messaged"})

#: LinkedIn's messaging pane never renders an ISO date. It shows a time of day
#: for today, "Yesterday", a weekday inside the last week, "Aug 29" inside the
#: last year, and only then a year. Feeding these to a strict ISO parser made
#: every thread unparseable, so a sync could read twenty threads and propose
#: nothing — which looks exactly like a quiet inbox.
_TIME_OF_DAY = re.compile(r"^\d{1,2}:\d{2}\s*(am|pm)?$", re.I)
_MONTH_DAY = re.compile(r"^([a-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$", re.I)
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_CREDENTIAL_SUFFIX = re.compile(r",.*$")
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_NON_NAME = re.compile(r"[^a-z ]")


def strip_url_query(url: str) -> str:
    """Reduce a LinkedIn URL to the identity it names.

    Tracking parameters and a trailing slash differ between the messaging pane
    and the invitation manager for the same person, so comparing raw hrefs
    silently fails to match.
    """
    if not url:
        return ""
    return url.split("?")[0].rstrip("/").lower()


def parse_thread_timestamp(raw, *, today: dt.date | None = None) -> dt.date | None:
    """Parse a LinkedIn messaging timestamp to a date, or None if unusable.

    A bare month and day is read as its most recent occurrence: "Dec 25" seen in
    August is last December, not four months from now.
    """
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    today = today or datetime.now().date()

    iso = parse_iso_date(text)
    if iso is not None:
        return iso

    if _TIME_OF_DAY.match(text):
        return today
    lowered = text.lower()
    if lowered == "yesterday":
        return today - dt.timedelta(days=1)
    if lowered == "today":
        return today
    if lowered[:3] in {day[:3] for day in _WEEKDAYS}:
        # A weekday name means within the last seven days.
        target = [d[:3] for d in _WEEKDAYS].index(lowered[:3])
        delta = (today.weekday() - target) % 7
        return today - dt.timedelta(days=delta or 7)

    match = _MONTH_DAY.match(text)
    if not match:
        return None
    month_name, day, year = match.groups()
    for fmt in ("%b", "%B"):
        try:
            month = datetime.strptime(month_name[:3] if fmt == "%b" else month_name, fmt).month
            break
        except ValueError:
            continue
    else:
        return None
    try:
        if year:
            return dt.date(int(year), month, int(day))
        candidate = dt.date(today.year, month, int(day))
        return candidate if candidate <= today else dt.date(today.year - 1, month, int(day))
    except ValueError:
        return None


def normalize_name(name: str) -> str:
    """Fold a display name to a comparable form.

    LinkedIn renders the same person as `Qiwei (Steve) Chen, MBA` in one place
    and `Qiwei Chen` in another.
    """
    if not name:
        return ""
    folded = _CREDENTIAL_SUFFIX.sub("", name.lower())
    folded = _PARENTHETICAL.sub(" ", folded)
    folded = _NON_NAME.sub(" ", folded)
    return " ".join(folded.split())


class InboxService:
    """Build proposed transitions from message threads and pending invitations."""

    def propose_transitions(
        self,
        threads: list[dict],
        pending_invitations: list[dict] | None,
        contacts: list[dict],
        today: dt.date | None = None,
    ) -> list[dict]:
        """Return proposed status changes, highest confidence first.

        `pending_invitations` of None means the list could not be read, which is
        not the same as nobody having a pending invitation — see
        `_invitation_proposals`.

        At most one proposal per contact: a reply from someone whose invitation
        also vanished is a single transition, and the reply is the stronger
        signal because it implies the acceptance.
        """
        by_id: dict[int, dict] = {}

        for proposal in self._reply_proposals(threads, contacts, today):
            by_id.setdefault(proposal["contact_id"], proposal)

        for proposal in self._invitation_proposals(pending_invitations, contacts):
            by_id.setdefault(proposal["contact_id"], proposal)

        order = {"high": 0, "low": 1}
        return sorted(by_id.values(), key=lambda p: (order[p["confidence"]], p["contact_id"]))

    # -- signals ---------------------------------------------------------------

    def _reply_proposals(self, threads: list[dict], contacts: list[dict], today: dt.date | None = None):
        for thread in threads:
            name = thread.get("name")
            timestamp = thread.get("timestamp")
            if not name or not timestamp:
                # A thread missing either is unusable, and one malformed row
                # must not abort the rest of the sync.
                continue
            if not thread.get("last_from_them"):
                continue

            replied_at = parse_thread_timestamp(timestamp, today=today)
            if replied_at is None:
                continue

            match, confidence = self._match(thread.get("url", ""), name, contacts)
            if match is None:
                continue
            if match.get("status") not in REPLY_ADVANCES_FROM:
                continue

            # A reply older than our last outbound touch is the conversation we
            # already knew about, not news.
            last_contact = parse_iso_date(match.get("last_contact")) or parse_iso_date(match.get("created_at"))
            if last_contact and replied_at <= last_contact:
                continue

            yield self._proposal(
                match,
                to_status="responded",
                source="messaging",
                confidence=confidence,
                evidence=self._evidence(confidence, thread.get("snippet", ""), name),
            )

    def _invitation_proposals(self, pending: list[dict] | None, contacts: list[dict]):
        """Propose `connected` for sent invitations that are no longer pending.

        The signal is an absence, which makes it dangerous: a selector that
        matched nothing produces an empty list, and reading that as "every
        invitation was accepted" would advance the whole pipeline at once. The
        page object reports an unreadable list as None, and None yields nothing.
        """
        if pending is None:
            return

        pending_urls = {strip_url_query(row.get("url", "")) for row in pending}
        pending_urls.discard("")
        pending_names = {normalize_name(row.get("name", "")) for row in pending}
        pending_names.discard("")

        for contact in contacts:
            if contact.get("status") != "connection_sent":
                continue
            url = strip_url_query(contact.get("linkedin_url", ""))
            name = normalize_name(contact.get("name", ""))
            if url and url in pending_urls:
                continue
            if not url and name in pending_names:
                continue

            yield self._proposal(
                contact,
                to_status="connected",
                source="invitations",
                confidence="high" if url else "low",
                evidence="Sent invitation is no longer pending — likely accepted",
            )

    # -- matching --------------------------------------------------------------

    def _match(self, url: str, name: str, contacts: list[dict]) -> tuple[dict | None, str]:
        """Resolve a thread participant to a contact.

        URL first, because it is the identity — a display name that differs from
        the stored one must not split the same person into two. Falling back to
        the name is a guess, so it is labelled `low` and, when it is ambiguous
        between two contacts, is no evidence about either.
        """
        target_url = strip_url_query(url)
        if target_url:
            for contact in contacts:
                if strip_url_query(contact.get("linkedin_url", "")) == target_url:
                    return contact, "high"
            return None, ""

        target_name = normalize_name(name)
        if not target_name:
            return None, ""
        hits = [c for c in contacts if normalize_name(c.get("name", "")) == target_name]
        if len(hits) != 1:
            return None, ""
        return hits[0], "low"

    # -- shaping ---------------------------------------------------------------

    def _proposal(self, contact: dict, *, to_status: str, source: str, confidence: str, evidence: str) -> dict:
        return {
            "contact_id": contact.get("id"),
            "name": contact.get("name", "Unknown"),
            "company": contact.get("company", ""),
            "from_status": contact.get("status", ""),
            "to_status": to_status,
            "source": source,
            "confidence": confidence,
            "evidence": evidence,
            "detected_at": datetime.now().isoformat(timespec="seconds"),
        }

    @staticmethod
    def _evidence(confidence: str, snippet: str, name: str) -> str:
        body = f'Replied: "{snippet.strip()[:120]}"' if snippet.strip() else "Replied in LinkedIn messaging"
        if confidence == "low":
            return f"{body} (matched on name '{name}' only — no profile URL on the thread)"
        return body
