"""Discover page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.discover_service import DiscoverService


class DiscoverState(rx.State):
    """State for the discover page."""

    suggestions: str = ""
    loading: bool = False
    role: str = ""
    company: str = ""
    industry: str = ""
    discover_type: str = "contacts"

    @rx.event
    def set_role(self, value: str):
        self.role = value

    @rx.event
    def set_company(self, value: str):
        self.company = value

    @rx.event
    def set_industry(self, value: str):
        self.industry = value

    @rx.event
    def set_discover_type(self, value: str):
        self.discover_type = value

    @rx.event
    def discover(self):
        """Run AI-powered discovery."""
        self.loading = True
        contact_repo, company_repo, profile_repo, *_ = create_repos()
        svc = DiscoverService(contact_repo, company_repo, profile_repo)

        if self.discover_type == "contacts":
            error, result = svc.discover_contacts(role=self.role, company=self.company, industry=self.industry)
        else:
            error, result = svc.discover_companies(industry=self.industry)

        if error:
            self.suggestions = f"Error: {error}"
        else:
            self.suggestions = result

        self.loading = False
