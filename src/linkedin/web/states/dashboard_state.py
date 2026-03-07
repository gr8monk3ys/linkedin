"""Dashboard page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.dashboard_service import DashboardService


class DashboardState(rx.State):
    """State for the dashboard page."""

    total_contacts: int = 0
    total_companies: int = 0
    total_drafts: int = 0
    response_rate: str = "0%"
    pipeline_data: list[dict] = []
    overdue_followups: list[dict] = []
    recent_activities: list[dict] = []
    suggested_actions: list[str] = []

    @rx.event
    def load_dashboard(self):
        """Load dashboard data from services."""
        contact_repo, company_repo, profile_repo, draft_repo, research_repo = create_repos()
        svc = DashboardService(profile_repo, contact_repo, company_repo, draft_repo)
        data = svc.get_dashboard_data()
        status_counts = data.get("status_counts", {})
        companies = data.get("companies", [])

        self.total_contacts = data.get("contacts_total", 0)
        self.total_companies = len(companies)
        self.total_drafts = data.get("drafts_total", 0)

        # Pipeline data for chart
        self.pipeline_data = [
            {"status": status.replace("_", " ").title(), "count": count}
            for status, count in status_counts.items()
            if count > 0
        ]

        # Response rate
        total = self.total_contacts
        responded = (
            status_counts.get("responded", 0)
            + status_counts.get("call_scheduled", 0)
            + status_counts.get("hired", 0)
        )
        self.response_rate = f"{(responded / total * 100):.0f}%" if total > 0 else "0%"

        # Overdue follow-ups
        self.overdue_followups = [
            {
                "name": contact.get("name", ""),
                "follow_up_date": contact.get("follow_up_date", ""),
                "days_overdue": days_overdue,
            }
            for contact, days_overdue in data.get("overdue", [])[:5]
        ]

        self.suggested_actions = data.get("suggestions", []) or [
            "Add new contacts to start building your pipeline"
        ]
