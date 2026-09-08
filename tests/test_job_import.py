"""Job-search rows become scored postings, deduped so a daily search does not stack."""

import pytest

from linkedin.data.json_store import JsonProfileRepo
from linkedin.services.postings_service import PostingService


@pytest.fixture
def market(tmp_path):
    return PostingService(JsonProfileRepo(tmp_path / "profile.json"), tmp_path / "job_postings.json")


JOB = {
    "title": "ML Engineer",
    "company": "Netflix",
    "location": "Los Angeles",
    "url": "https://www.linkedin.com/jobs/view/1",
    "easy_apply": True,
}


def test_import_job_results_scores_against_the_profile(market):
    market.profiles.save({"target_role": "ML Engineer", "skills": "Python, SQL"})
    added, skipped = market.import_job_results([JOB])
    assert len(added) == 1 and skipped == 0
    stored = market.list_postings()
    assert stored[0]["company"] == "Netflix"
    assert stored[0]["source"] == "linkedin_jobs"
    assert stored[0]["notes"] == "Easy Apply"
    assert stored[0]["match_score"] > 0


def test_import_job_results_dedupes_on_url(market):
    results = [{"title": "ML Engineer", "company": "Netflix", "url": "https://x/jobs/view/1?trk=abc"}]
    market.import_job_results(results)
    added, skipped = market.import_job_results(
        [{"title": "ML Engineer", "company": "Netflix", "url": "https://x/jobs/view/1"}]
    )
    assert added == [] and skipped == 1
    assert len(market.list_postings()) == 1


def test_import_job_results_dedupes_on_company_and_title_without_a_url(market):
    results = [{"title": "ML Engineer", "company": "Netflix", "url": ""}]
    market.import_job_results(results)
    added, skipped = market.import_job_results(results)
    assert added == [] and skipped == 1


def test_import_job_results_skips_rows_with_no_title(market):
    added, skipped = market.import_job_results([{"title": "", "company": "Netflix"}])
    assert added == [] and skipped == 1
