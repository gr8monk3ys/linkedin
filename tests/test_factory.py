"""Tests for the repository factory."""

from linkedin.data.factory import Repos, create_repos
from linkedin.data.json_store import JsonContactRepo
from linkedin.data.paths import DataDir


class TestFactory:
    def test_repos_take_their_files_from_the_data_dir(self, tmp_path):
        repos = create_repos(DataDir(tmp_path))
        assert isinstance(repos, Repos)
        assert repos.contacts.path == tmp_path / "contacts.json"
        assert repos.interview_prep.path == tmp_path / "interview_prep.json"
        assert len(repos.as_tuple()) == 9  # the CRM set; posts hang off repos.posts
        assert repos.posts.path == tmp_path / "posts.json"

    def test_two_data_dirs_do_not_share_state(self, tmp_path):
        a = create_repos(DataDir(tmp_path / "a")).contacts
        b = create_repos(DataDir(tmp_path / "b")).contacts
        a.add({"id": 1, "name": "Only in A"})
        assert b.list_all() == []

    def test_backend_env_var_is_ignored(self, monkeypatch, tmp_path):
        """LINKEDIN_BACKEND=db used to build a split JSON/DB store; it is now inert."""
        monkeypatch.setenv("LINKEDIN_BACKEND", "db")
        assert isinstance(create_repos(DataDir(tmp_path)).contacts, JsonContactRepo)
