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
        from linkedin.services.contact_service import ContactService

        svc = DashboardService(contact_repo, company_repo, draft_repo)
        data = svc.get_dashboard_data()

        self.total_contacts = data.get("total_contacts", 0)
        self.total_companies = data.get("total_companies", 0)
        self.total_drafts = data.get("total_drafts", 0)

        # Pipeline data for chart
        pipeline = data.get("pipeline", {})
        self.pipeline_data = [
            {"status": status.replace("_", " ").title(), "count": count}
            for status, count in pipeline.items()
            if count > 0
        ]

        # Response rate
        total = self.total_contacts
        responded = pipeline.get("responded", 0) + pipeline.get("call_scheduled", 0) + pipeline.get("hired", 0)
        self.response_rate = f"{(responded / total * 100):.0f}%" if total > 0 else "0%"

        # Overdue follow-ups
        contact_svc = ContactService(contact_repo, company_repo)
        due = contact_svc.get_due_contacts()
        self.overdue_followups = due[:5]

        # Suggested actions
        actions = []
        not_contacted = pipeline.get("not_contacted", 0)
        if not_contacted > 0:
            actions.append(f"Send connection requests to {not_contacted} uncontacted people")
        connection_sent = pipeline.get("connection_sent", 0)
        if connection_sent > 0:
            actions.append(f"Follow up with {connection_sent} pending connections")
        connected = pipeline.get("connected", 0)
        if connected > 0:
            actions.append(f"Send messages to {connected} connected contacts")
        if not actions:
            actions.append("Add new contacts to start building your pipeline")
        self.suggested_actions = actions
