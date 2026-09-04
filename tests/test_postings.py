"""Tests for market intelligence service."""

import json

from linkedin.services.postings_service import PostingService
from tests.conftest import sample_profile


class TestPostingService:
    def test_add_posting(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = PostingService(profile_repo, profile_repo.path.parent / "job_postings.json")
        posting = svc.add_posting({"title": "Senior Engineer", "company": "Google"})
        assert posting["id"] == 1
        assert len(svc.list_postings()) == 1

    def test_list_postings_with_match_score(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        svc = PostingService(profile_repo, profile_repo.path.parent / "job_postings.json")
        profile_repo.save(sample_profile(skills="Python, SQL, Machine Learning", target_role="Senior Engineer"))
        svc.add_posting(
            {
                "title": "Senior Engineer",
                "company": "Acme",
                "location": "San Francisco, CA",
                "skills_required": "Python, SQL",
            }
        )

        postings = svc.list_postings()
        assert len(postings) == 1
        assert postings[0]["match_score"] >= 40
        assert postings[0]["match_reasons"]

    def test_import_postings_csv(self, json_repos, tmp_path):
        _, _, profile_repo, *_ = json_repos
        svc = PostingService(profile_repo, profile_repo.path.parent / "job_postings.json")
        csv_file = tmp_path / "postings.csv"
        csv_file.write_text('title,company,location,skills_required\nStaff Engineer,Acme,Remote,"Python, SQL"\n')

        imported, skipped = svc.import_postings(str(csv_file))
        assert imported == 1
        assert skipped == 0
        assert len(svc.list_postings()) == 1

    def test_import_postings_json_merge_skips_duplicates(self, json_repos, tmp_path):
        _, _, profile_repo, *_ = json_repos
        svc = PostingService(profile_repo, profile_repo.path.parent / "job_postings.json")
        svc.add_posting({"title": "Senior Engineer", "company": "Acme", "location": "Remote"})

        json_file = tmp_path / "postings.json"
        json_file.write_text(
            json.dumps(
                [
                    {"title": "Senior Engineer", "company": "Acme", "location": "Remote"},
                    {"title": "ML Engineer", "company": "Beta", "location": "NYC"},
                ]
            )
        )

        imported, skipped = svc.import_postings(str(json_file), merge=True)
        assert imported == 1
        assert skipped == 1
        assert len(svc.list_postings()) == 2
