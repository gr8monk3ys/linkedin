"""Contact management service."""

import datetime as dt
from datetime import datetime

from linkedin.data.repository import CompanyRepo, ContactRepo
from linkedin.types import ContactDict


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
            "follow_up_date": None,
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
            status = c["status"]
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
