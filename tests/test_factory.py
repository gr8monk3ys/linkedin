"""Tests for the repository factory."""

from linkedin.data.factory import create_repos
from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonCalendarRepo,
    JsonCompanyRepo,
    JsonContactRepo,
    JsonConversationRepo,
    JsonDraftRepo,
    JsonInterviewPrepRepo,
    JsonProfileRepo,
    JsonResearchRepo,
)


class TestFactory:
    def test_creates_the_full_json_repo_set(self):
        expected = [
            JsonContactRepo,
            JsonCompanyRepo,
            JsonProfileRepo,
            JsonDraftRepo,
            JsonResearchRepo,
            JsonApplicationRepo,
            JsonConversationRepo,
            JsonCalendarRepo,
            JsonInterviewPrepRepo,
        ]
        repos = create_repos()
        assert len(repos) == len(expected)
        assert all(isinstance(repo, cls) for repo, cls in zip(repos, expected))

    def test_backend_env_var_is_ignored(self, monkeypatch):
        """LINKEDIN_BACKEND=db used to build a split JSON/DB store; it is now inert."""
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        assert isinstance(create_repos()[0], JsonContactRepo)
