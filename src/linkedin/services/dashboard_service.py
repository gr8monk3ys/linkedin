"""Dashboard overview service."""

from datetime import datetime

from linkedin.data.repository import CompanyRepo, ContactRepo, DraftRepo, ProfileRepo


class DashboardService:
    def __init__(
        self,
        profile_repo: ProfileRepo,
        contact_repo: ContactRepo,
        company_repo: CompanyRepo,
        draft_repo: DraftRepo,
    ):
        self.profiles = profile_repo
        self.contacts = contact_repo
        self.companies = company_repo
        self.drafts = draft_repo

    def get_dashboard_data(self) -> dict:
        profile = self.profiles.get()
        all_contacts = self.contacts.list_all()
        companies_list = self.companies.list_all()
        drafts_list = self.drafts.list_all()

        # Status counts
        status_counts: dict[str, int] = {}
        for c in all_contacts:
            status = c["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Overdue follow-ups and stale connections
        today = datetime.now().date()
        overdue = []
        stale_connections = []

        for contact in all_contacts:
            follow_up = contact.get("follow_up_date")
            if follow_up:
                try:
                    follow_up_date = datetime.fromisoformat(follow_up.replace("Z", "+00:00")).date()
                    if follow_up_date < today:
                        days_overdue = (today - follow_up_date).days
                        overdue.append((contact, days_overdue))
                except (ValueError, AttributeError):
                    pass

            if contact["status"] == "connection_sent":
                last_contact = contact.get("last_contact")
                if last_contact:
                    try:
                        last_date = datetime.fromisoformat(last_contact.replace("Z", "+00:00")).date()
                        days_since = (today - last_date).days
                        if days_since >= 14:
                            stale_connections.append((contact, days_since))
                    except (ValueError, AttributeError):
                        pass

        overdue.sort(key=lambda x: x[1], reverse=True)

        # Company contact counts
        company_contacts: dict[int, int] = {}
        for contact in all_contacts:
            cid = contact.get("company_id")
            if cid:
                company_contacts[cid] = company_contacts.get(cid, 0) + 1

        # Draft type counts
        draft_types: dict[str, int] = {}
        for d in drafts_list:
            dtype = d.get("type", "unknown")
            draft_types[dtype] = draft_types.get(dtype, 0) + 1

        # Suggested actions
        suggestions = []
        if overdue:
            suggestions.append(f"Follow up with {overdue[0][0]['name']}")

        not_contacted = [c for c in all_contacts if c["status"] == "not_contacted"]
        if not_contacted:
            suggestions.append(f"{len(not_contacted)} contacts to reach out to")

        connected = [c for c in all_contacts if c["status"] == "connected"]
        if connected:
            suggestions.append(f"{len(connected)} connections to message")

        for company in companies_list[:3]:
            contact_count = company_contacts.get(company["id"], 0)
            if contact_count == 0:
                suggestions.append(f"Find contacts at {company['name']}")
                break

        if not profile:
            suggestions.append("Set up your profile for personalized drafts")

        if not suggestions:
            suggestions.append("Add more contacts or companies to track")

        return {
            "profile": profile,
            "contacts_total": len(all_contacts),
            "status_counts": status_counts,
            "overdue": overdue,
            "stale_connections": stale_connections,
            "companies": companies_list,
            "company_contacts": company_contacts,
            "drafts_total": len(drafts_list),
            "draft_types": draft_types,
            "suggestions": suggestions,
        }
