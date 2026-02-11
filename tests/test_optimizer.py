"""Tests for optimizer service."""

from unittest.mock import patch

from linkedin.services.optimizer_service import OptimizerService
from tests.conftest import sample_profile


class TestOptimizerService:
    def test_headline_no_profile(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = OptimizerService(profile_repo)
        error, result = svc.optimize_headline()
        assert error is not None
        assert "profile" in error.lower()

    @patch("linkedin.services.optimizer_service.generate_with_ai", return_value="1. Great headline\n2. Another headline")
    def test_headline_generates(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = OptimizerService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.optimize_headline()
        assert error is None
        assert "headline" in result.lower()

    @patch("linkedin.services.optimizer_service.generate_with_ai", return_value="About section text")
    def test_about_generates(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = OptimizerService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.optimize_about()
        assert error is None
        assert len(result) > 0

    @patch("linkedin.services.optimizer_service.generate_with_ai", return_value="Skills analysis")
    def test_skills_generates(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = OptimizerService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.optimize_skills()
        assert error is None
        assert len(result) > 0

    @patch("linkedin.services.optimizer_service.generate_with_ai", return_value="Full review")
    def test_full_generates(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = OptimizerService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.optimize_full()
        assert error is None
        assert len(result) > 0
