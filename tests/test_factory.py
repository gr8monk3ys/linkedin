"""Tests for data backend factory."""

from linkedin.data.db_store import DbCompanyRepo, DbContactRepo, DbDraftRepo, DbProfileRepo, DbResearchRepo
from linkedin.data.factory import create_repos, get_backend
from linkedin.data.json_store import JsonCompanyRepo, JsonContactRepo, JsonDraftRepo, JsonProfileRepo, JsonResearchRepo
from linkedin.models.base import reset_engine


class TestFactory:
    def test_default_backend_is_json(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_BACKEND", raising=False)
        assert get_backend() == "json"

    def test_backend_from_env(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        assert get_backend() == "db"

    def test_create_json_repos(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_BACKEND", raising=False)
        repos = create_repos()
        assert isinstance(repos[0], JsonContactRepo)
        assert isinstance(repos[1], JsonCompanyRepo)
        assert isinstance(repos[2], JsonProfileRepo)
        assert isinstance(repos[3], JsonDraftRepo)
        assert isinstance(repos[4], JsonResearchRepo)

    def test_create_db_repos(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        reset_engine()
        repos = create_repos()
        assert isinstance(repos[0], DbContactRepo)
        assert isinstance(repos[1], DbCompanyRepo)
        assert isinstance(repos[2], DbProfileRepo)
        assert isinstance(repos[3], DbDraftRepo)
        assert isinstance(repos[4], DbResearchRepo)
        reset_engine()
