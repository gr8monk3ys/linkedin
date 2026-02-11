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
    post_style: str = "professional"

    @rx.event
    def load_engagement(self):
        """Load engagement strategies (static content)."""
        _, _, profile_repo, _, research_repo = create_repos()
        svc = ResearchService(research_repo, profile_repo)
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
        _, _, profile_repo, _, research_repo = create_repos()
        svc = ResearchService(research_repo, profile_repo)
        error, ideas = svc.generate_post_ideas()
        self.post_ideas = ideas if not error else f"Error: {error}"
        self.loading = False

    @rx.event
    def generate_draft_post(self):
        """Generate a draft post with AI."""
        self.loading = True
        _, _, profile_repo, _, research_repo = create_repos()
        svc = ResearchService(research_repo, profile_repo)
        error, draft = svc.generate_draft_post(self.post_topic, self.post_style)
        self.post_draft = draft if not error else f"Error: {error}"
        self.loading = False

    @rx.event
    def generate_hashtags(self):
        """Generate hashtags with AI."""
        self.loading = True
        _, _, profile_repo, _, research_repo = create_repos()
        svc = ResearchService(research_repo, profile_repo)
        error, tags = svc.generate_hashtags()
        self.hashtags = tags if not error else f"Error: {error}"
        self.loading = False
