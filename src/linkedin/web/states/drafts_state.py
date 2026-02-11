"""Drafts page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.draft_service import DraftService


class DraftsState(rx.State):
    """State for the drafts page."""

    drafts: list[dict] = []
    contacts: list[dict] = []
    generated_draft: str = ""
    loading: bool = False
    draft_type: str = "connection"
    selected_contact_id: int = 0
    target_contact_id: int = 0
    context_text: str = ""

    @rx.event
    def load_drafts(self):
        """Load all drafts and contacts for selection."""
        contact_repo, company_repo, profile_repo, draft_repo, _ = create_repos()
        svc = DraftService(draft_repo, contact_repo, profile_repo)
        self.drafts = svc.list_drafts()
        self.contacts = contact_repo.list_all()

    @rx.event
    def set_draft_type(self, value: str):
        self.draft_type = value

    @rx.event
    def set_contact_id(self, value: str):
        self.selected_contact_id = int(value) if value else 0

    @rx.event
    def set_target_id(self, value: str):
        self.target_contact_id = int(value) if value else 0

    @rx.event
    def set_context(self, value: str):
        self.context_text = value

    @rx.event
    def generate_draft(self):
        """Generate a draft using AI."""
        if not self.selected_contact_id:
            return

        self.loading = True
        contact_repo, company_repo, profile_repo, draft_repo, _ = create_repos()
        svc = DraftService(draft_repo, contact_repo, profile_repo)

        error = None
        draft_text = ""

        if self.draft_type == "connection":
            error, draft_text = svc.generate_connection(self.selected_contact_id)
        elif self.draft_type == "message":
            error, draft_text = svc.generate_message(self.selected_contact_id, self.context_text)
        elif self.draft_type == "intro":
            error, draft_text = svc.generate_intro_request(self.selected_contact_id, self.target_contact_id)
        elif self.draft_type == "thank_you":
            error, draft_text = svc.generate_thank_you(self.selected_contact_id, self.context_text)
        elif self.draft_type == "follow_up":
            error, draft_text = svc.generate_follow_up(self.selected_contact_id)

        if error:
            self.generated_draft = f"Error: {error}"
        else:
            self.generated_draft = draft_text

        self.loading = False

    @rx.event
    def save_current_draft(self):
        """Save the currently generated draft."""
        if not self.generated_draft or self.generated_draft.startswith("Error:"):
            return

        contact_repo, company_repo, profile_repo, draft_repo, _ = create_repos()
        svc = DraftService(draft_repo, contact_repo, profile_repo)
        extra = {}
        if self.draft_type == "intro" and self.target_contact_id:
            extra["target_contact_id"] = self.target_contact_id
        svc.save_draft(self.selected_contact_id or None, self.draft_type, self.generated_draft, **extra)
        self.load_drafts()
