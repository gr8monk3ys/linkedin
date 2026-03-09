"""Tests for data backend factory."""

from unittest.mock import patch

from linkedin.data.db_store import (
    DbCompanyRepo,
    DbContactRepo,
    DbDraftRepo,
    DbProfileRepo,
    DbResearchRepo,
    DbTemplateRepo,
)
from linkedin.data.factory import create_repos, create_template_repo, get_backend
from linkedin.data.json_store import (
    JsonCompanyRepo,
    JsonContactRepo,
    JsonDraftRepo,
    JsonProfileRepo,
    JsonResearchRepo,
    JsonTemplateRepo,
)
from linkedin.data.twenty_store import TwentyCompanyRepo, TwentyContactRepo, TwentyDraftRepo
from linkedin.models.base import reset_engine


class TestFactory:
    def test_default_backend_is_json(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_BACKEND", raising=False)
        assert get_backend() == "json"

    def test_backend_from_env(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        assert get_backend() == "db"

    def test_backend_twenty_from_env(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_BACKEND", "twenty")
        assert get_backend() == "twenty"

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

    def test_create_json_template_repo(self, monkeypatch):
        monkeypatch.delenv("LINKEDIN_BACKEND", raising=False)
        repo = create_template_repo()
        assert isinstance(repo, JsonTemplateRepo)

    def test_create_db_template_repo(self, monkeypatch):
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
        reset_engine()
        repo = create_template_repo()
        assert isinstance(repo, DbTemplateRepo)
        reset_engine()

    def test_create_twenty_repos(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LINKEDIN_BACKEND", "twenty")
        monkeypatch.setenv("TWENTY_API_URL", "http://test:3000")
        monkeypatch.setenv("TWENTY_API_KEY", "test-key")
        # Patch DATA_DIR so id_map.json goes to tmp
        import linkedin.data.factory as factory_mod
        monkeypatch.setattr(factory_mod, "DATA_DIR", tmp_path)

        with patch("linkedin.data.twenty_client.TwentyClient.health_check", return_value=True), \
             patch("linkedin.data.twenty_setup.ensure_custom_fields"):
            repos = create_repos()
            assert isinstance(repos[0], TwentyContactRepo)
            assert isinstance(repos[1], TwentyCompanyRepo)
            assert isinstance(repos[2], JsonProfileRepo)
            assert isinstance(repos[3], TwentyDraftRepo)
            assert isinstance(repos[4], JsonResearchRepo)

    def test_twenty_unreachable_exits(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LINKEDIN_BACKEND", "twenty")
        monkeypatch.setenv("TWENTY_API_URL", "http://dead:3000")
        monkeypatch.setenv("TWENTY_API_KEY", "test-key")
        import linkedin.data.factory as factory_mod
        monkeypatch.setattr(factory_mod, "DATA_DIR", tmp_path)

        with patch("linkedin.data.twenty_client.TwentyClient.health_check", return_value=False):
            import pytest
            with pytest.raises(SystemExit, match="Cannot reach Twenty"):
                create_repos()
