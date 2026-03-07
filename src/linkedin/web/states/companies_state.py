"""Companies page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.company_service import CompanyService


class CompaniesState(rx.State):
    """State for the companies page."""

    companies: list[dict] = []
    selected_company: dict = {}
    company_contacts: list[dict] = []
    show_add_modal: bool = False
    show_detail: bool = False

    @rx.event
    def load_companies(self):
        """Load all companies."""
        contact_repo, company_repo, *_ = create_repos()
        svc = CompanyService(company_repo, contact_repo)
        self.companies = svc.list_companies()

    @rx.event
    def select_company(self, company_id: int):
        """Select a company for detail view."""
        contact_repo, company_repo, *_ = create_repos()
        svc = CompanyService(company_repo, contact_repo)
        company_payload = svc.get_company(company_id)
        company = company_payload.data if hasattr(company_payload, "data") else company_payload
        if not company:
            return

        contacts_payload = svc.get_company_contacts(company_id)
        if hasattr(contacts_payload, "ok"):
            contacts = contacts_payload.data["contacts"] if contacts_payload.ok and contacts_payload.data else []
        else:
            _company, contacts = contacts_payload

        self.selected_company = company
        self.company_contacts = contacts
        self.show_detail = True

    @rx.event
    def close_detail(self):
        self.show_detail = False
        self.selected_company = {}
        self.company_contacts = []

    @rx.event
    def toggle_add_modal(self):
        self.show_add_modal = not self.show_add_modal

    @rx.event
    def add_company(self, form_data: dict):
        """Add a new company."""
        contact_repo, company_repo, *_ = create_repos()
        svc = CompanyService(company_repo, contact_repo)
        svc.add_company(
            name=form_data.get("name", ""),
            industry=form_data.get("industry", ""),
            size=form_data.get("size", "51-200"),
            linkedin=form_data.get("linkedin_url", ""),
            website=form_data.get("website", ""),
            why=form_data.get("why_target", ""),
            priority=form_data.get("priority", "medium"),
        )
        self.show_add_modal = False
        self.load_companies()

    @rx.event
    def delete_company(self, company_id: int):
        """Delete a company."""
        contact_repo, company_repo, *_ = create_repos()
        svc = CompanyService(company_repo, contact_repo)
        svc.delete_company(company_id)
        self.show_detail = False
        self.selected_company = {}
        self.load_companies()
