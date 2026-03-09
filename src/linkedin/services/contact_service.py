"""Contact management service."""

import datetime as dt
import re
from datetime import datetime
from difflib import SequenceMatcher

from linkedin.data.repository import CompanyRepo, ContactRepo
from linkedin.types import ContactDict, Result

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
            filtered = [c for c in filtered if c["status"] == status]
        if company:
            filtered = [c for c in filtered if company.lower() in c["company"].lower()]
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
    ) -> Result:
        if company_id:
            company_obj = self.companies.get(company_id)
            if not company_obj:
                return Result(f"Company #{company_id} not found.")
            company = company_obj["name"]

        if referral_id:
            referrer = self.contacts.get(referral_id)
            if not referrer:
                return Result(f"Referral contact #{referral_id} not found.")

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
            "follow_up_date": None,
            "company_id": company_id,
            "email": email,
            "source": source,
            "referral_contact_id": referral_id,
            "activities": [],
            "campaign": {},
        }

        return Result(None, self.contacts.add(contact))

    def update_contact(
        self,
        contact_id: int,
        status: str | None = None,
        notes: str | None = None,
        follow_up: str | None = None,
        email: str | None = None,
    ) -> Result:
        contact = self.contacts.get(contact_id)
        if not contact:
            return Result("Contact not found")

        if "activities" not in contact:
            contact["activities"] = []

        if status:
            old_status = contact.get("status", "not_contacted")
            contact["status"] = status
            contact["last_contact"] = datetime.now().isoformat()
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
        return Result(None, contact)

    def view_contact(self, contact_id: int) -> Result:
        contact = self.contacts.get(contact_id)
        if not contact:
            return Result("Contact not found")

        result = dict(contact)

        if contact.get("company_id"):
            linked_company = self.companies.get(contact["company_id"])
            result["linked_company"] = linked_company

        if contact.get("referral_contact_id"):
            referrer = self.contacts.get(contact["referral_contact_id"])
            result["referrer"] = referrer

        return Result(None, result)

    def get_stats(self) -> dict:
        contacts = self.contacts.list_all()
        if not contacts:
            return {"total": 0, "status_counts": {}}

        status_counts: dict[str, int] = {}
        for c in contacts:
            status = c["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        return {"total": len(contacts), "status_counts": status_counts}

    def get_activities(self, contact_id: int) -> Result:
        contact = self.contacts.get(contact_id)
        if not contact:
            return Result("Contact not found")
        return Result(None, contact.get("activities", []))

    def link_company(self, contact_id: int, company_id: int) -> Result:
        contact = self.contacts.get(contact_id)
        if not contact:
            return Result(f"Contact #{contact_id} not found")

        company = self.companies.get(company_id)
        if not company:
            return Result(f"Company #{company_id} not found")

        contact["company_id"] = company_id
        contact["company"] = company["name"]
        self.contacts.update(contact)
        return Result(None)

    def get_due_contacts(self, days: int = 0) -> dict:
        all_contacts = self.contacts.list_all()
        if not all_contacts:
            return {"overdue": [], "due_today": [], "upcoming": [], "stale": []}

        today = datetime.now().date()
        threshold = today + dt.timedelta(days=days)

        due_contacts = []
        for contact in all_contacts:
            follow_up = contact.get("follow_up_date")
            if not follow_up:
                continue
            try:
                follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
                if follow_up_date <= threshold:
                    days_overdue = (today - follow_up_date).days
                    due_contacts.append((contact, follow_up_date, days_overdue))
            except (ValueError, AttributeError):
                continue

        stale_connections = []
        for contact in all_contacts:
            if contact["status"] == "connection_sent":
                last_contact = contact.get("last_contact")
                if last_contact:
                    try:
                        last_date = datetime.fromisoformat(last_contact.replace("Z", "+00:00")).date()
                        days_since = (today - last_date).days
                        if days_since >= 14:
                            stale_connections.append((contact, days_since))
                    except (ValueError, AttributeError):
                        continue

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

    def set_reminder(self, contact_id: int, days: int | None = None, date: str | None = None) -> Result:
        contact = self.contacts.get(contact_id)
        if not contact:
            return Result("Contact not found")

        if date:
            follow_up_date = date
        else:
            follow_up_date = (datetime.now() + dt.timedelta(days=days or 7)).strftime("%Y-%m-%d")

        contact["follow_up_date"] = follow_up_date
        self.contacts.update(contact)
        return Result(None, follow_up_date)

    def get_next_actions(self, limit: int = 10) -> list[dict]:
        """Return prioritized next actions across the pipeline."""
        today = datetime.now().date()
        due_data = self.get_due_contacts(days=0)
        all_contacts = self.contacts.list_all()
        actions: list[dict] = []

        for contact, follow_date, days_overdue in due_data["overdue"]:
            actions.append({
                "priority": 100 + min(days_overdue, 30),
                "action": "follow_up_overdue",
                "contact_id": contact["id"],
                "name": contact.get("name", ""),
                "company": contact.get("company", ""),
                "reason": f"Follow-up overdue by {days_overdue} day(s)",
            })

        for contact, follow_date, _ in due_data["due_today"]:
            actions.append({
                "priority": 95,
                "action": "follow_up_today",
                "contact_id": contact["id"],
                "name": contact.get("name", ""),
                "company": contact.get("company", ""),
                "reason": "Follow-up due today",
            })

        for contact, days_since in due_data["stale"]:
            actions.append({
                "priority": 85 + min(days_since, 30),
                "action": "stale_connection_sent",
                "contact_id": contact["id"],
                "name": contact.get("name", ""),
                "company": contact.get("company", ""),
                "reason": f"Connection request sent {days_since} day(s) ago with no response",
            })

        for contact in all_contacts:
            status = contact.get("status")
            age_days = self._days_since_reference(contact, today)
            if age_days is None:
                continue

            if status == "connected" and age_days >= 7:
                actions.append({
                    "priority": 70 + min(age_days, 30),
                    "action": "send_first_message",
                    "contact_id": contact["id"],
                    "name": contact.get("name", ""),
                    "company": contact.get("company", ""),
                    "reason": f"Connected {age_days} day(s) ago; send first message",
                })

            if status == "responded" and age_days >= 3:
                actions.append({
                    "priority": 65 + min(age_days, 30),
                    "action": "schedule_call",
                    "contact_id": contact["id"],
                    "name": contact.get("name", ""),
                    "company": contact.get("company", ""),
                    "reason": f"Responded {age_days} day(s) ago; propose a call",
                })

        actions.sort(key=lambda a: a["priority"], reverse=True)
        return actions[:limit]

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
