"""Contact management service."""

import datetime as dt
import re
from datetime import datetime
from difflib import SequenceMatcher

from linkedin.constants import ContactStatus
from linkedin.data.repository import CompanyRepo, ContactRepo
from linkedin.types import ContactDict

# Statuses that end the pipeline; they carry no follow-up and generate no actions.
TERMINAL_STATUSES = frozenset({"hired", "rejected"})

# Everything the planner knows about a pipeline status, in one row per status:
# how long to wait before the contact is due (`cadence_days`, which seeds
# `follow_up_date` on add and on every status change), and what to do once that
# wait has elapsed. Keeping cadence and action in the same row is what makes a
# status with one and not the other unrepresentable — that hole is what made
# `messaged` contacts invisible to the planner. `_check_status_coverage()` closes
# the other half: a status added to `ContactStatus` and to neither table here.
STATUS_RULES: dict[str, dict] = {
    "not_contacted": {
        "cadence_days": 0,
        "after_days": 0,
        "priority": 60,
        "action": "send_connection",
        "reason": "Added {age} day(s) ago; send a connection request",
    },
    "connection_sent": {
        "cadence_days": 7,
        "after_days": 14,
        "priority": 85,
        "action": "stale_connection_sent",
        "reason": "Connection request sent {age} day(s) ago with no response",
    },
    "connected": {
        "cadence_days": 2,
        "after_days": 7,
        "priority": 70,
        "action": "send_first_message",
        "reason": "Connected {age} day(s) ago; send first message",
    },
    "messaged": {
        "cadence_days": 5,
        "after_days": 5,
        "priority": 75,
        "action": "follow_up_messaged",
        "reason": "Messaged {age} day(s) ago with no reply; follow up",
    },
    "responded": {
        "cadence_days": 2,
        "after_days": 3,
        "priority": 65,
        "action": "schedule_call",
        "reason": "Responded {age} day(s) ago; propose a call",
    },
    "call_scheduled": {
        "cadence_days": 7,
        "after_days": 7,
        "priority": 68,
        "action": "call_follow_up",
        "reason": "Call scheduled {age} day(s) ago; confirm or debrief",
    },
}


def _check_status_coverage() -> None:
    """Fail loudly if a pipeline status is neither terminal nor planned for.

    `ContactStatus` is where a new status gets added, and a status the planner has
    no rule for is invisible to it forever. Checking the tables against the enum
    rather than against each other is what makes that impossible to ship.
    """
    known = set(STATUS_RULES) | set(TERMINAL_STATUSES)
    declared = {status.value for status in ContactStatus}
    if known != declared:
        raise RuntimeError(
            "Pipeline status tables disagree with ContactStatus — a status with no "
            f"rule is invisible to the planner. Missing a rule: {sorted(declared - known)}; "
            f"rule for an unknown status: {sorted(known - declared)}"
        )


_check_status_coverage()

CAMPAIGN_LIBRARY: dict[str, list[dict]] = {
    "networking_21d": [
        {
            "index": 0,
            "label": "Send connection request",
            "day_offset": 0,
            "suggested_command": "linkedin-cli drafts connection {id}",
        },
        {
            "index": 1,
            "label": "Follow up #1",
            "day_offset": 7,
            "suggested_command": "linkedin-cli drafts follow-up {id} --attempt 1",
        },
        {
            "index": 2,
            "label": "Follow up #2",
            "day_offset": 14,
            "suggested_command": "linkedin-cli drafts follow-up {id} --attempt 2",
        },
        {
            "index": 3,
            "label": "Ask for a short call",
            "day_offset": 21,
            "suggested_command": "linkedin-cli drafts message {id} --context \"Ask for a short call\"",
        },
    ],
}


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
    def __init__(self, contact_repo: ContactRepo, company_repo: CompanyRepo):
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
            "campaign": {},
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
            contact["activities"].append({
                "date": datetime.now().isoformat(),
                "type": status,
                "note": f"Status changed from {old_status.replace('_', ' ')}",
            })
        if notes:
            contact["notes"] = (contact.get("notes", "") + f"\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}").strip()
            contact["activities"].append({
                "date": datetime.now().isoformat(),
                "type": "note_added",
                "note": notes,
            })
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

    def delete_contact(self, contact_id: int) -> bool:
        """Remove a contact. Returns False if it was not there.

        Merging was the only way to get rid of a record, which is wrong for a
        junk one: it folds the junk into a real contact rather than dropping it.
        """
        return self.contacts.delete(contact_id)

    def get_next_actions(self, limit: int = 10) -> list[dict]:
        """Return prioritized next actions across the pipeline."""
        today = datetime.now().date()
        all_contacts = self.contacts.list_all()
        due_data = self.get_due_contacts(days=0, contacts=all_contacts)
        actions: list[dict] = []

        for contact, _, days_overdue in due_data["overdue"]:
            actions.append(self._action(
                contact, 100 + min(days_overdue, 30), "follow_up_overdue",
                f"Follow-up overdue by {days_overdue} day(s)",
            ))

        for contact, _, _ in due_data["due_today"]:
            actions.append(self._action(contact, 95, "follow_up_today", "Follow-up due today"))

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
                actions.append(self._action(
                    contact, 50, "repair_contact",
                    "No created_at/last_contact; run `linkedin-cli contacts repair`",
                ))
                continue

            rule = STATUS_RULES.get(status)
            if rule and age_days >= rule["after_days"]:
                actions.append(self._action(
                    contact, rule["priority"] + min(age_days, 30), rule["action"],
                    rule["reason"].format(age=age_days),
                ))

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

            repaired.append({
                "contact_id": contact["id"],
                "name": contact.get("name", ""),
                "status": status,
                "fixes": fixes,
                "follow_up_date": contact.get("follow_up_date"),
            })

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
            for right in contacts[i + 1:]:
                score, signals = self._duplicate_score(left, right)
                if score < min_score:
                    continue

                primary_id, duplicate_id = self._preferred_merge_order(left, right)
                primary = left if left.get("id") == primary_id else right
                duplicate = right if right.get("id") == duplicate_id else left
                confidence = "high" if score >= 0.85 else "medium" if score >= 0.70 else "low"
                candidates.append({
                    "primary_id": primary_id,
                    "duplicate_id": duplicate_id,
                    "primary_name": primary.get("name", ""),
                    "duplicate_name": duplicate.get("name", ""),
                    "primary_company": primary.get("company", ""),
                    "duplicate_company": duplicate.get("company", ""),
                    "score": round(score, 2),
                    "confidence": confidence,
                    "signals": signals,
                })

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
        merged["status"] = self._best_status(primary.get("status", "not_contacted"), duplicate.get("status", "not_contacted"))
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

    def enroll_campaign(
        self,
        contact_id: int,
        campaign_name: str = "networking_21d",
        start_date: str | None = None,
    ) -> ContactDict | str | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        campaign_name = campaign_name.strip().lower() or "networking_21d"
        steps = CAMPAIGN_LIBRARY.get(campaign_name)
        if not steps:
            return f"Unknown campaign '{campaign_name}'."

        enrolled_at = start_date
        if enrolled_at:
            try:
                # Validate YYYY-MM-DD format.
                datetime.fromisoformat(enrolled_at)
            except ValueError:
                return "start_date must use YYYY-MM-DD format."
        else:
            enrolled_at = datetime.now().strftime("%Y-%m-%d")

        contact["campaign"] = {
            "name": campaign_name,
            "active": True,
            "step_index": 0,
            "enrolled_at": enrolled_at,
            "completed_at": None,
            "last_advanced_at": None,
        }
        self.contacts.update(contact)
        return contact

    def campaign_status(self, contact_id: int) -> dict | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        campaign = contact.get("campaign")
        if not isinstance(campaign, dict) or not campaign.get("name"):
            return {}

        steps = self._campaign_steps(str(campaign.get("name", "")))
        step_index = int(campaign.get("step_index", 0))
        active = bool(campaign.get("active", False))
        total_steps = len(steps)
        current_step = steps[step_index] if active and 0 <= step_index < total_steps else None
        due_date = self._campaign_step_due_date(campaign, current_step) if current_step else None

        return {
            "contact_id": contact.get("id"),
            "contact_name": contact.get("name", ""),
            "campaign_name": campaign.get("name", ""),
            "active": active,
            "step_index": step_index,
            "total_steps": total_steps,
            "current_step": current_step,
            "due_date": due_date.isoformat() if due_date else None,
            "completed_at": campaign.get("completed_at"),
            "enrolled_at": campaign.get("enrolled_at"),
        }

    def list_campaign_contacts(self, active_only: bool = False, campaign_name: str = "") -> list[dict]:
        result = []
        expected_name = campaign_name.strip().lower()
        for contact in self.contacts.list_all():
            status = self.campaign_status(int(contact.get("id", 0)))
            if not status:
                continue
            if expected_name and status.get("campaign_name") != expected_name:
                continue
            if active_only and not status.get("active", False):
                continue
            result.append(status)
        return result

    def get_due_campaign_steps(self, limit: int = 10, as_of: dt.date | None = None) -> list[dict]:
        today = as_of or datetime.now().date()
        due: list[dict] = []

        for contact in self.contacts.list_all():
            campaign = contact.get("campaign")
            if not isinstance(campaign, dict):
                continue
            if not campaign.get("active"):
                continue

            steps = self._campaign_steps(str(campaign.get("name", "")))
            if not steps:
                continue

            step_index = int(campaign.get("step_index", 0))
            if step_index < 0 or step_index >= len(steps):
                continue
            step = steps[step_index]
            due_date = self._campaign_step_due_date(campaign, step)
            if due_date is None:
                continue
            if due_date > today:
                continue

            days_overdue = (today - due_date).days
            due.append({
                "contact_id": contact.get("id"),
                "contact_name": contact.get("name", ""),
                "company": contact.get("company", ""),
                "campaign_name": campaign.get("name", ""),
                "step_index": step_index,
                "step_label": step.get("label", ""),
                "due_date": due_date.isoformat(),
                "days_overdue": days_overdue,
                "suggested_command": str(step.get("suggested_command", "linkedin-cli contacts view {id}")).format(id=contact.get("id")),
                "priority": 100 + min(days_overdue, 30),
            })

        due.sort(key=lambda row: (row["priority"], row["contact_id"]), reverse=True)
        return due[:limit]

    def advance_campaign(self, contact_id: int, complete: bool = False) -> ContactDict | str | None:
        contact = self.contacts.get(contact_id)
        if not contact:
            return None

        campaign = contact.get("campaign")
        if not isinstance(campaign, dict) or not campaign.get("name"):
            return "Contact is not enrolled in a campaign."

        steps = self._campaign_steps(str(campaign.get("name", "")))
        if not steps:
            return "Campaign definition not found."

        if complete:
            campaign["step_index"] = len(steps)
            campaign["active"] = False
            campaign["completed_at"] = datetime.now().isoformat()
            campaign["last_advanced_at"] = datetime.now().isoformat()
            contact["campaign"] = campaign
            self.contacts.update(contact)
            return contact

        step_index = int(campaign.get("step_index", 0))
        next_index = step_index + 1
        campaign["step_index"] = next_index
        campaign["last_advanced_at"] = datetime.now().isoformat()
        if next_index >= len(steps):
            campaign["active"] = False
            campaign["completed_at"] = datetime.now().isoformat()
        else:
            campaign["active"] = True
            campaign["completed_at"] = None

        contact["campaign"] = campaign
        self.contacts.update(contact)
        return contact

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

    def _campaign_steps(self, campaign_name: str) -> list[dict]:
        return CAMPAIGN_LIBRARY.get(campaign_name.strip().lower(), [])

    def _campaign_step_due_date(self, campaign: dict, step: dict | None) -> dt.date | None:
        if not step:
            return None
        enrolled_at = str(campaign.get("enrolled_at", "")).strip()
        if not enrolled_at:
            return None
        try:
            base_date = datetime.fromisoformat(enrolled_at.replace("Z", "+00:00")).date()
        except ValueError:
            return None
        try:
            offset = int(step.get("day_offset", 0))
        except (TypeError, ValueError):
            offset = 0
        return base_date + dt.timedelta(days=max(0, offset))
