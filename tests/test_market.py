"""Tests for market intelligence service."""

from unittest.mock import patch

from linkedin.services.market_service import MarketService
from tests.conftest import sample_profile


class TestMarketService:
    def test_analyze_no_role(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        error, result = svc.analyze_market()
        assert error is not None

    @patch("linkedin.services.market_service.generate_with_ai", return_value="Market analysis result")
    def test_analyze_with_role(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.analyze_market()
        assert error is None
        assert "Market analysis" in result

    @patch("linkedin.services.market_service.generate_with_ai", return_value="$120k - $180k")
    def test_salary_estimate(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.estimate_salary()
        assert error is None
        assert "$" in result

    def test_salary_no_role(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        error, result = svc.estimate_salary()
        assert error is not None

    @patch("linkedin.services.market_service.generate_with_ai", return_value="Trending: AI/ML roles")
    def test_trends(self, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.analyze_trends()
        assert error is None

    def test_trends_no_industry(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        error, result = svc.analyze_trends()
        assert error is not None

    def test_add_posting(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        posting = svc.add_posting({"title": "Senior Engineer", "company": "Google"})
        assert posting["id"] == 1
        assert svc.list_postings() == [posting]
