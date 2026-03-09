"""Tests for market intelligence service."""

import json
from unittest.mock import patch

from linkedin.services.market_service import MarketService
from tests.conftest import sample_profile


class TestMarketService:
    def test_analyze_no_role(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        error, result = svc.analyze_market()
        assert error is not None

    @patch("linkedin.services.market_service.generate_ai_text", return_value=("Market analysis result", None))
    def test_analyze_with_role(self, _mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        profile_repo.save(sample_profile())

        error, result = svc.analyze_market()
        assert error is None
        assert "Market analysis" in result

    @patch("linkedin.services.market_service.generate_ai_text", return_value=("$120k - $180k", None))
    def test_salary_estimate(self, _mock_ai, json_repos):
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

    @patch("linkedin.services.market_service.generate_ai_text", return_value=("Trending: AI/ML roles", None))
    def test_trends(self, _mock_ai, json_repos):
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
        assert len(svc.list_postings()) == 1

    def test_list_postings_with_match_score(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        profile_repo.save(sample_profile(skills="Python, SQL, Machine Learning", target_role="Senior Engineer"))
        svc.add_posting({
            "title": "Senior Engineer",
            "company": "Acme",
            "location": "San Francisco, CA",
            "skills_required": "Python, SQL",
        })

        postings = svc.list_postings()
        assert len(postings) == 1
        assert postings[0]["match_score"] >= 40
        assert postings[0]["match_reasons"]

    def test_import_postings_csv(self, json_repos, tmp_path):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        csv_file = tmp_path / "postings.csv"
        csv_file.write_text("title,company,location,skills_required\nStaff Engineer,Acme,Remote,\"Python, SQL\"\n")

        imported, skipped = svc.import_postings(str(csv_file))
        assert imported == 1
        assert skipped == 0
        assert len(svc.list_postings()) == 1

    def test_import_postings_json_merge_skips_duplicates(self, json_repos, tmp_path):
        _, _, profile_repo, *_ = json_repos
        svc = MarketService(profile_repo)
        svc.add_posting({"title": "Senior Engineer", "company": "Acme", "location": "Remote"})

        json_file = tmp_path / "postings.json"
        json_file.write_text(json.dumps([
            {"title": "Senior Engineer", "company": "Acme", "location": "Remote"},
            {"title": "ML Engineer", "company": "Beta", "location": "NYC"},
        ]))

        imported, skipped = svc.import_postings(str(json_file), merge=True)
        assert imported == 1
        assert skipped == 1
        assert len(svc.list_postings()) == 2
