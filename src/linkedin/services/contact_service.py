"""Contact management service."""

import datetime as dt
import re
from datetime import datetime
from difflib import SequenceMatcher

from linkedin.data.json_store import JsonCompanyRepo, JsonContactRepo
from linkedin.services.planner import (
    FOLLOW_UP_OVERDUE,
    FOLLOW_UP_TODAY,
    REPAIR_CONTACT,
    SEND_CONNECTION,
    STATUS_RULES,
    TERMINAL_STATUSES,
    _check_status_coverage,
)
from linkedin.services.ranking_service import PINNED_FIELD, connection_bonus
from linkedin.types import ContactDict

__all__ = ["STATUS_RULES", "TERMINAL_STATUSES", "_check_status_coverage", "ContactService", "parse_iso_date"]


def parse_iso_date(value) -> dt.date | None:
    """Parse a stored ISO timestamp or date, returning None for anything unusable."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (ValueError, AttributeError, TypeError):
        return None


def cadence_follow_up_date(status: str, *, since: dt.date | None = None) -> str | None:
    """Return the follow-up date implied by `status`, or None for terminal statuses."""
    rule = STATUS_RULES.get(status)
    if rule is None:
        return None
    days = rule["cadence_days"]
    base = since or datetime.now().date()
    return (base + dt.timedelta(days=days)).strftime("%Y-%m-%d")


class ContactService:
    def __init__(self, contact_repo: JsonContactRepo, company_repo: JsonCompanyRepo):
        self.contacts = contact_repo
        self.companies = company_repo

    def list_contacts(
        self,
        status: str = "all",
        company: str | None = None,
        company_id: int | None = None,
        source: str = "all",
    ) -> list[ContactDict]:
        filtered = self.contacts.list_all()
        if status != "all":
            filtered = [c for c in filtered if c.get("status") == status]
        if company:
            filtered = [c for c in filtered if company.lower() in (c.get("company") or "").lower()]
        if company_id:
            filtered = [c for c in filtered if c.get("company_id") == company_id]
        if source != "all":
            filtered = [c for c in filtered if c.get("source") == source]
        return filtered

    def get_contact(self, contact_id: int) -> ContactDict | None:
        return self.contacts.get(contact_id)

    def add_contact(
        self,
        name: str,
        title: str,
        company: str,
        linkedin: str,
        notes: str = "",
        company_id: int | None = None,
        email: str = "",
        source: str = "linkedin_search",
        referral_id: int | None = None,
    ) -> ContactDict | str:
        if company_id:
            company_obj = self.companies.get(company_id)
            if not company_obj:
                return f"Company #{company_id} not found."
            company = company_obj["name"]

        if referral_id:
            referrer = self.contacts.get(referral_id)
            if not referrer:
                return f"Referral contact #{referral_id} not found."

        contact: ContactDict = {
            "id": self.contacts.next_id(),
            "name": name,
            "title": title,
            "company": company,
            "linkedin_url": linkedin,
            "notes": notes,
            "status": "not_contacted",
            "created_at": datetime.now().isoformat(),
            "last_contact": None,
            "follow_up_date": cadence_follow_up_date("not_contacted"),
            "company_id": company_id,
            "email": email,
            "source": source,
            "referral_contact_id": referral_id,
            "activities": [],
        }

        return self.contacts.add(contact)

    def update_contact(
        self,
        contact_id: int,
        status: str | None = None,
        notes: str | None = None,
        follow_up: str | None = None,
        email: str | None = None,
    ) -> ContactDict | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        if "activities" not in contact:
            contact["activities"] = []

        if status:
            old_status = contact.get("status", "not_contacted")
            contact["status"] = status
            contact["last_contact"] = datetime.now().isoformat()
            contact["follow_up_date"] = cadence_follow_up_date(status)
            contact["activities"].append(
                {
                    "date": datetime.now().isoformat(),
                    "type": status,
                    "note": f"Status changed from {old_status.replace('_', ' ')}",
                }
            )
        if notes:
            contact["notes"] = (contact.get("notes", "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}").strip()
            contact["activities"].append(
                {
                    "date": datetime.now().isoformat(),
                    "type": "note_added",
                    "note": notes,
                }
            )
        if follow_up:
            contact["follow_up_date"] = follow_up
        if email:
            contact["email"] = email

        self.contacts.update(contact)
        return contact

    def view_contact(self, contact_id: int) -> dict | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        result = dict(contact)

        if contact.get("company_id"):
            linked_company = self.companies.get(contact["company_id"])
            result["linked_company"] = linked_company

        if contact.get("referral_contact_id"):
            referrer = self.contacts.get(contact["referral_contact_id"])
            result["referrer"] = referrer

        return result

    def get_stats(self) -> dict:
        contacts = self.contacts.list_all()
        if not contacts:
            return {"total": 0, "status_counts": {}}

        status_counts: dict[str, int] = {}
        for c in contacts:
            status = c.get("status") or "not_contacted"
            status_counts[status] = status_counts.get(status, 0) + 1

        return {"total": len(contacts), "status_counts": status_counts}

    def get_activities(self, contact_id: int) -> list[dict] | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None
        return contact.get("activities", [])

    def link_company(self, contact_id: int, company_id: int) -> str | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return f"Contact #{contact_id} not found"

        company = self.companies.get(company_id)
        if not company:
            return f"Company #{company_id} not found"

        contact["company_id"] = company_id
        contact["company"] = company["name"]
        self.contacts.update(contact)
        return None

    def get_due_contacts(self, days: int = 0, contacts: list[ContactDict] | None = None) -> dict:
        all_contacts = self.contacts.list_all() if contacts is None else contacts
        if not all_contacts:
            return {"overdue": [], "due_today": [], "upcoming": [], "stale": []}

        today = datetime.now().date()
        threshold = today + dt.timedelta(days=days)

        due_contacts = []
        for contact in all_contacts:
            follow_up_date = parse_iso_date(contact.get("follow_up_date"))
            if follow_up_date is None or follow_up_date > threshold:
                continue
            due_contacts.append((contact, follow_up_date, (today - follow_up_date).days))

        stale_connections = []
        for contact in all_contacts:
            if contact.get("status") == "connection_sent":
                last_date = parse_iso_date(contact.get("last_contact"))
                if last_date is not None:
                    days_since = (today - last_date).days
                    if days_since >= STATUS_RULES["connection_sent"]["after_days"]:
                        stale_connections.append((contact, days_since))

        overdue = [(c, d, days_o) for c, d, days_o in due_contacts if days_o > 0]
        due_today = [(c, d, days_o) for c, d, days_o in due_contacts if days_o == 0]
        upcoming = [(c, d, days_o) for c, d, days_o in due_contacts if days_o < 0]

        overdue.sort(key=lambda x: x[2], reverse=True)
        upcoming.sort(key=lambda x: x[2], reverse=True)

        return {
            "overdue": overdue,
            "due_today": due_today,
            "upcoming": upcoming,
            "stale": stale_connections,
        }

    def set_reminder(self, contact_id: int, days: int | None = None, date: str | None = None) -> str | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        if date:
            follow_up_date = date
        else:
            follow_up_date = (datetime.now() + dt.timedelta(days=days or 7)).strftime("%Y-%m-%d")

        contact["follow_up_date"] = follow_up_date
        self.contacts.update(contact)
        return follow_up_date

    @staticmethod
    def _action(contact: ContactDict, priority: int, action: str, reason: str) -> dict:
        return {
            "priority": priority,
            "action": action,
            "contact_id": contact["id"],
            "name": contact.get("name", ""),
            "company": contact.get("company", ""),
            "reason": reason,
        }

    def set_pinned(self, contact_id: int, pinned: bool) -> ContactDict | None:
        """Pin (or unpin) a contact: exempt from ranking, always followed."""
        contact = self.contacts.get(contact_id)
        if not contact:
            return None
        contact[PINNED_FIELD] = pinned
        self.contacts.update(contact)
        return contact

    def pinned_contacts(self) -> list[ContactDict]:
        return [c for c in self.contacts.list_all() if c.get(PINNED_FIELD)]

    def delete_contact(self, contact_id: int) -> bool:
        """Remove a contact. Returns False if it was not there.

        Merging was the only way to get rid of a record, which is wrong for a
        junk one: it folds the junk into a real contact rather than dropping it.
        """
        return self.contacts.delete(contact_id)

    def get_next_actions(self, limit: int = 10, scores: dict[int, int] | None = None) -> list[dict]:
        """Return prioritized next actions across the pipeline.

        `scores` (contact id → rank score) raises the priority of each
        `send_connection` action by `connection_bonus`, so the day's scarce
        invitations go to the contacts that matter most for the target role.
        """
        scores = scores or {}
        today = datetime.now().date()
        all_contacts = self.contacts.list_all()
        due_data = self.get_due_contacts(days=0, contacts=all_contacts)
        actions: list[dict] = []

        def awaiting_first_contact(contact: ContactDict) -> bool:
            # A follow-up presumes a first contact. A `not_contacted` contact's
            # follow-up date is seeded on add (cadence 0), so without this the
            # date rules fired first as "follow-up overdue" for someone never
            # written to, outranked `send_connection`, and the ranking bonus for
            # the day's invitations never applied to anyone.
            return STATUS_RULES.get(contact.get("status", ""), {}).get("action") == SEND_CONNECTION

        for contact, _, days_overdue in due_data["overdue"]:
            if awaiting_first_contact(contact):
                continue
            actions.append(
                self._action(
                    contact,
                    100 + min(days_overdue, 30),
                    FOLLOW_UP_OVERDUE,
                    f"Follow-up overdue by {days_overdue} day(s)",
                )
            )

        for contact, _, _ in due_data["due_today"]:
            if awaiting_first_contact(contact):
                continue
            actions.append(self._action(contact, 95, FOLLOW_UP_TODAY, "Follow-up due today"))

        # No loop over due_data["stale"]: STATUS_RULES["connection_sent"] emits the
        # same action from the same threshold, and the dedupe below discarded one of
        # the two copies. One source for the action, one for its wording.
        for contact in all_contacts:
            status = contact.get("status")
            if status in TERMINAL_STATUSES:
                continue
            age_days = self._days_since_reference(contact, today)
            if age_days is None:
                # No timestamps at all — the contact is stranded rather than fresh.
                # Surface it so `contacts repair` gets run instead of it sitting invisible.
                actions.append(
                    self._action(
                        contact,
                        50,
                        REPAIR_CONTACT,
                        "No created_at/last_contact; run `linkedin-cli contacts repair`",
                    )
                )
                continue

            rule = STATUS_RULES.get(status)
            if rule and age_days >= rule["after_days"]:
                priority = rule["priority"] + min(age_days, 30)
                reason = rule["reason"].format(age=age_days)
                if rule["action"] == "send_connection" and contact["id"] in scores:
                    score = scores[contact["id"]]
                    priority += connection_bonus(score)
                    reason += f" (rank {score})"
                actions.append(self._action(contact, priority, rule["action"], reason))

        actions.sort(key=lambda a: a["priority"], reverse=True)

        # A contact can qualify under several rules at once (an overdue follow-up is
        # usually also due today). Keep only its highest-priority action so the daily
        # plan reads as one line per person.
        deduped: list[dict] = []
        seen: set[int] = set()
        for action in actions:
            if action["contact_id"] in seen:
                continue
            seen.add(action["contact_id"])
            deduped.append(action)

        return deduped[:limit]

    def stalled_contacts(self) -> list[ContactDict]:
        """Active contacts the planner should have had something to say about.

        Two shapes qualify, and both mean the planner is broken rather than idle:
        a contact with no usable `follow_up_date`, so it can never come due, and
        one whose follow-up date has already arrived. A contact scheduled for a
        future date is simply not due yet — a quiet day, not a stall.
        """
        today = datetime.now().date()
        stalled: list[ContactDict] = []
        for contact in self.contacts.list_all():
            if contact.get("status") in TERMINAL_STATUSES:
                continue
            due = parse_iso_date(contact.get("follow_up_date"))
            if due is None or due <= today:
                stalled.append(contact)
        return stalled

    def repair_contacts(self, dry_run: bool = False) -> dict:
        """Backfill missing timestamps and follow-up dates on existing contacts.

        Contacts written before the cadence existed (or imported without dates) are
        invisible to `get_next_actions`. This makes them actionable again.
        """
        repaired: list[dict] = []
        all_contacts = self.contacts.list_all()
        for contact in all_contacts:
            fixes: list[str] = []
            if not contact.get("status"):
                contact["status"] = "not_contacted"
                fixes.append("status")
            status = contact["status"]

            # Missing string fields crash the renderers and the list filters.
            for field in ("name", "company", "title", "linkedin_url", "notes", "email"):
                if field not in contact or contact[field] is None:
                    contact[field] = ""
                    fixes.append(field)

            if not contact.get("created_at"):
                activities = contact.get("activities") or []
                dates = [a.get("date") for a in activities if a.get("date")]
                contact["created_at"] = min(dates) if dates else datetime.now().isoformat()
                fixes.append("created_at")

            if status != "not_contacted" and not contact.get("last_contact"):
                contact["last_contact"] = contact["created_at"]
                fixes.append("last_contact")

            if status in TERMINAL_STATUSES:
                if contact.get("follow_up_date"):
                    contact["follow_up_date"] = None
                    fixes.append("follow_up_date cleared")
            elif not contact.get("follow_up_date"):
                reference = contact.get("last_contact") or contact["created_at"]
                since = parse_iso_date(reference) or datetime.now().date()
                contact["follow_up_date"] = cadence_follow_up_date(status, since=since)
                fixes.append("follow_up_date")

            if not fixes:
                continue

            repaired.append(
                {
                    "contact_id": contact["id"],
                    "name": contact.get("name", ""),
                    "status": status,
                    "fixes": fixes,
                    "follow_up_date": contact.get("follow_up_date"),
                }
            )

        # One write for the whole set — `update()` rewrites the entire file per
        # call, and every write now fsyncs.
        if repaired and not dry_run:
            self.contacts.save_all(all_contacts)

        return {"repaired": repaired, "total": len(repaired), "dry_run": dry_run}

    def _days_since_reference(self, contact: ContactDict, today: dt.date) -> int | None:
        ref = contact.get("last_contact") or contact.get("created_at")
        if not ref:
            return None
        try:
            ref_date = datetime.fromisoformat(ref.replace("Z", "+00:00")).date()
        except (ValueError, AttributeError):
            return None
        return (today - ref_date).days

    def find_duplicate_candidates(self, min_score: float = 0.65, limit: int = 20) -> list[dict]:
        """Find likely duplicate contacts with confidence scores."""
        contacts = self.contacts.list_all()
        candidates: list[dict] = []
        for i, left in enumerate(contacts):
            for right in contacts[i + 1 :]:
                score, signals = self._duplicate_score(left, right)
                if score < min_score:
                    continue

                primary_id, duplicate_id = self._preferred_merge_order(left, right)
                primary = left if left.get("id") == primary_id else right
                duplicate = right if right.get("id") == duplicate_id else left
                confidence = "high" if score >= 0.85 else "medium" if score >= 0.70 else "low"
                candidates.append(
                    {
                        "primary_id": primary_id,
                        "duplicate_id": duplicate_id,
                        "primary_name": primary.get("name", ""),
                        "duplicate_name": duplicate.get("name", ""),
                        "primary_company": primary.get("company", ""),
                        "duplicate_company": duplicate.get("company", ""),
                        "score": round(score, 2),
                        "confidence": confidence,
                        "signals": signals,
                    }
                )

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:limit]

    def merge_contacts(self, primary_id: int, duplicate_id: int, prefer: str = "primary") -> ContactDict | str:
        """Merge duplicate contact into a primary record and remove duplicate."""
        if primary_id == duplicate_id:
            return "Primary and duplicate contact IDs must differ."

        primary = self.contacts.get(primary_id)
        duplicate = self.contacts.get(duplicate_id)
        if not primary or not duplicate:
            return "One or both contacts were not found."

        if prefer == "duplicate":
            primary, duplicate = duplicate, primary
            primary_id, duplicate_id = duplicate_id, primary_id

        merged = dict(primary)

        for field in [
            "name",
            "title",
            "company",
            "linkedin_url",
            "company_id",
            "email",
            "source",
            "follow_up_date",
            "referral_contact_id",
        ]:
            if not merged.get(field) and duplicate.get(field):
                merged[field] = duplicate.get(field)

        merged["notes"] = self._merge_notes(primary.get("notes", ""), duplicate.get("notes", ""))
        merged["status"] = self._best_status(
            primary.get("status", "not_contacted"), duplicate.get("status", "not_contacted")
        )
        merged["created_at"] = self._earliest_iso(primary.get("created_at"), duplicate.get("created_at"))
        merged["last_contact"] = self._latest_iso(primary.get("last_contact"), duplicate.get("last_contact"))
        merged["activities"] = self._merge_activities(primary.get("activities", []), duplicate.get("activities", []))

        if merged.get("referral_contact_id") == duplicate_id:
            merged["referral_contact_id"] = primary_id

        merged["id"] = primary_id
        self.contacts.update(merged)
        self.contacts.delete(duplicate_id)

        for contact in self.contacts.list_all():
            if contact.get("referral_contact_id") == duplicate_id:
                contact["referral_contact_id"] = primary_id
                self.contacts.update(contact)

        return merged

    def _duplicate_score(self, left: ContactDict, right: ContactDict) -> tuple[float, list[str]]:
        score = 0.0
        signals: list[str] = []

        left_email = self._norm(left.get("email", ""))
        right_email = self._norm(right.get("email", ""))
        if left_email and right_email and left_email == right_email:
            score += 0.55
            signals.append("email")

        left_linkedin = self._norm(left.get("linkedin_url", ""))
        right_linkedin = self._norm(right.get("linkedin_url", ""))
        if left_linkedin and right_linkedin and left_linkedin == right_linkedin:
            score += 0.55
            signals.append("linkedin")

        left_name = self._norm(left.get("name", ""))
        right_name = self._norm(right.get("name", ""))
        if left_name and right_name:
            if left_name == right_name:
                score += 0.30
                signals.append("exact_name")
            else:
                ratio = SequenceMatcher(None, left_name, right_name).ratio()
                if ratio >= 0.92:
                    score += 0.25
                    signals.append("very_similar_name")
                elif ratio >= 0.80:
                    score += 0.15
                    signals.append("similar_name")

        left_company = self._norm(left.get("company", ""))
        right_company = self._norm(right.get("company", ""))
        if left_company and right_company and left_company == right_company:
            score += 0.15
            signals.append("same_company")

        left_title = self._norm(left.get("title", ""))
        right_title = self._norm(right.get("title", ""))
        if left_title and right_title and left_title == right_title:
            score += 0.10
            signals.append("same_title")

        return min(1.0, score), signals

    def _preferred_merge_order(self, left: ContactDict, right: ContactDict) -> tuple[int, int]:
        left_id = left.get("id")
        right_id = right.get("id")
        left_score = self._record_completeness(left)
        right_score = self._record_completeness(right)

        if left_score > right_score:
            return left_id, right_id
        if right_score > left_score:
            return right_id, left_id
        return (left_id, right_id) if left_id <= right_id else (right_id, left_id)

    def _record_completeness(self, contact: ContactDict) -> int:
        fields = ["name", "title", "company", "linkedin_url", "email", "notes", "follow_up_date", "last_contact"]
        score = 0
        for field in fields:
            if contact.get(field):
                score += 1
        if contact.get("activities"):
            score += 1
        return score

    def _merge_notes(self, left: str, right: str) -> str:
        left = (left or "").strip()
        right = (right or "").strip()
        if not left:
            return right
        if not right or right in left:
            return left
        if left in right:
            return right
        return f"{left}\n{right}"

    def _best_status(self, left: str, right: str) -> str:
        order = {
            "not_contacted": 0,
            "connection_sent": 1,
            "connected": 2,
            "messaged": 3,
            "responded": 4,
            "call_scheduled": 5,
            "rejected": 6,
            "hired": 7,
        }
        return left if order.get(left, -1) >= order.get(right, -1) else right

    def _merge_activities(self, left: list[dict], right: list[dict]) -> list[dict]:
        seen = set()
        merged = []
        for activity in [*(left or []), *(right or [])]:
            key = (activity.get("date"), activity.get("type"), activity.get("note"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(activity)
        merged.sort(key=lambda a: a.get("date", ""))
        return merged

    def _earliest_iso(self, left: str | None, right: str | None) -> str | None:
        values = [v for v in [left, right] if v]
        if not values:
            return None
        parsed = []
        for value in values:
            try:
                parsed.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                continue
        if not parsed:
            return values[0]
        return min(parsed).isoformat()

    def _latest_iso(self, left: str | None, right: str | None) -> str | None:
        values = [v for v in [left, right] if v]
        if not values:
            return None
        parsed = []
        for value in values:
            try:
                parsed.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                continue
        if not parsed:
            return values[0]
        return max(parsed).isoformat()

    def _norm(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value).strip().lower())


# -- importing what the browser read ------------------------------------------


def parse_headline(headline: str) -> tuple[str, str]:
    """Parse 'Title at Company' into (title, company). Best-effort."""
    for sep in (" at ", " @ "):
        if sep in headline:
            title, company = headline.split(sep, 1)
            return title.strip(), company.strip()
    return headline.strip(), ""


def import_search_results(
    results: list[dict[str, str]],
    contact_repo: JsonContactRepo,
    skip_existing_urls: bool = True,
) -> tuple[list[ContactDict], list[str]]:
    """Persist people-search rows as contacts. Returns (added, skipped_urls)."""
    existing_urls: set[str] = set()
    if skip_existing_urls:
        existing_urls = {c.get("linkedin_url", "") for c in contact_repo.list_all()}

    added: list[ContactDict] = []
    skipped: list[str] = []
    for result in results:
        url = result.get("linkedin_url", "")
        if skip_existing_urls and url and url in existing_urls:
            skipped.append(url)
            continue
        headline = result.get("headline", "")
        title, company = parse_headline(headline)
        contact: ContactDict = {
            "id": contact_repo.next_id(),
            "name": result.get("name", "Unknown"),
            "title": title,
            "company": company,
            "linkedin_url": url,
            "notes": f"Imported from search. Headline: {headline}",
            "status": "not_contacted",
            "follow_up_date": cadence_follow_up_date("not_contacted"),
            "source": "linkedin_search",
            "created_at": datetime.now().isoformat(),
            "activities": [],
        }
        contact_repo.add(contact)
        added.append(contact)
    return added, skipped


def import_scraped_profile(data: dict[str, str], url: str, contact_repo: JsonContactRepo) -> ContactDict | None:
    """Add or update one contact from a scraped profile. None when there is no name."""
    if not data.get("name"):
        return None
    title, company = parse_headline(data.get("headline", ""))
    existing = next((c for c in contact_repo.list_all() if c.get("linkedin_url") == url), None)
    if existing:
        existing["title"] = title or existing.get("title", "")
        existing["company"] = company or existing.get("company", "")
        contact_repo.update(existing)
        return existing
    contact: ContactDict = {
        "id": contact_repo.next_id(),
        "name": data["name"],
        "title": title,
        "company": company,
        "linkedin_url": url,
        "notes": data.get("about", ""),
        "status": "not_contacted",
        "follow_up_date": cadence_follow_up_date("not_contacted"),
        "source": "linkedin_scrape",
        "created_at": datetime.now().isoformat(),
        "activities": [],
    }
    contact_repo.add(contact)
    return contact
