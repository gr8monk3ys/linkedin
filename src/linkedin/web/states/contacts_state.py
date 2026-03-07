"""Contacts page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.contact_service import ContactService


class ContactsState(rx.State):
    """State for the contacts page."""

    contacts: list[dict] = []
    selected_contact: dict = {}
    show_add_modal: bool = False
    show_detail: bool = False
    filter_status: str = ""
    search_query: str = ""

    @rx.event
    def load_contacts(self):
        """Load all contacts."""
        contact_repo, company_repo, *_ = create_repos()
        svc = ContactService(contact_repo, company_repo)
        self.contacts = svc.list_contacts()

    @rx.event
    def filter_by_status(self, status: str):
        """Filter contacts by status."""
        self.filter_status = status
        self.load_contacts()
        if status:
            self.contacts = [c for c in self.contacts if c.get("status") == status]

    @rx.event
    def search_contacts(self, query: str):
        """Search contacts by name."""
        self.search_query = query
        self.load_contacts()
        if query:
            q = query.lower()
            self.contacts = [
                c for c in self.contacts
                if q in c.get("name", "").lower()
                or q in c.get("company", "").lower()
                or q in c.get("title", "").lower()
            ]

    @rx.event
    def select_contact(self, contact_id: int):
        """Select a contact for detail view."""
        contact_repo, company_repo, *_ = create_repos()
        svc = ContactService(contact_repo, company_repo)
        contact = svc.get_contact(contact_id)
        if contact:
            self.selected_contact = contact
            self.show_detail = True

    @rx.event
    def close_detail(self):
        """Close detail view."""
        self.show_detail = False
        self.selected_contact = {}

    @rx.event
    def toggle_add_modal(self):
        """Toggle add contact modal."""
        self.show_add_modal = not self.show_add_modal

    @rx.event
    def add_contact(self, form_data: dict):
        """Add a new contact."""
        contact_repo, company_repo, *_ = create_repos()
        svc = ContactService(contact_repo, company_repo)
        svc.add_contact(
            name=form_data.get("name", ""),
            title=form_data.get("title", ""),
            company=form_data.get("company", ""),
            linkedin=form_data.get("linkedin_url", ""),
            notes=form_data.get("notes", ""),
            source=form_data.get("source", "linkedin_search"),
        )
        self.show_add_modal = False
        self.load_contacts()

    @rx.event
    def update_status(self, contact_id: int, new_status: str):
        """Update a contact's status."""
        contact_repo, company_repo, *_ = create_repos()
        svc = ContactService(contact_repo, company_repo)
        svc.update_contact(contact_id, status=new_status)
        self.load_contacts()
        if self.selected_contact and self.selected_contact.get("id") == contact_id:
            self.select_contact(contact_id)

    @rx.event
    def delete_contact(self, contact_id: int):
        """Delete a contact."""
        contact_repo, *_ = create_repos()
        contact_repo.delete(contact_id)
        self.show_detail = False
        self.selected_contact = {}
        self.load_contacts()
