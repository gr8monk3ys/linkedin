"""Research page state."""

import reflex as rx

from linkedin.data.factory import create_repos
from linkedin.services.research_service import ResearchService


class ResearchState(rx.State):
    """State for the research page."""

    engagement_content: str = ""
    post_ideas: str = ""
    post_draft: str = ""
    hashtags: str = ""
    loading: bool = False
    active_tab: str = "engagement"
    post_topic: str = ""
    post_style: str = "story"

    @rx.event
    def load_engagement(self):
        """Load engagement strategies (static content)."""
        contact_repo, company_repo, profile_repo, draft_repo, research_repo = create_repos()
        svc = ResearchService(profile_repo, research_repo, draft_repo)
        self.engagement_content = svc.get_engagement_strategies()

    @rx.event
    def set_active_tab(self, tab: str):
        self.active_tab = tab

    @rx.event
    def set_post_topic(self, value: str):
        self.post_topic = value

    @rx.event
    def set_post_style(self, value: str):
        self.post_style = value

    @rx.event
    def generate_ideas(self):
        """Generate post ideas with AI."""
        self.loading = True
        contact_repo, company_repo, profile_repo, draft_repo, research_repo = create_repos()
        svc = ResearchService(profile_repo, research_repo, draft_repo)
        _focus_topic, ideas = svc.generate_ideas(self.post_topic or None)
        self.post_ideas = ideas
        self.loading = False

    @rx.event
    def generate_draft_post(self):
        """Generate a draft post with AI."""
        self.loading = True
        contact_repo, company_repo, profile_repo, draft_repo, research_repo = create_repos()
        svc = ResearchService(profile_repo, research_repo, draft_repo)
        self.post_draft = svc.generate_post_draft(self.post_topic, self.post_style)
        self.loading = False

    @rx.event
    def generate_hashtags(self):
        """Generate hashtags with AI."""
        self.loading = True
        contact_repo, company_repo, profile_repo, draft_repo, research_repo = create_repos()
        svc = ResearchService(profile_repo, research_repo, draft_repo)
        self.hashtags = svc.generate_hashtags(self.post_topic or "professional networking")
        self.loading = False
