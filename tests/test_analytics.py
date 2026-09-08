"""Tests for analytics service."""

from linkedin.services.analytics_service import AnalyticsService
from tests.conftest import sample_contact


class TestAnalyticsService:
    def test_empty_summary(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)
        summary = svc.get_summary()
        assert summary["total_contacts"] == 0
        assert summary["response_rate"] == "0%"

    def test_summary_with_data(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)

        contact_repo.add(sample_contact(name="Alice", status="connected"))
        contact_repo.add(sample_contact(name="Bob", status="responded"))
        contact_repo.add(sample_contact(name="Carol", status="not_contacted"))

        summary = svc.get_summary()
        assert summary["total_contacts"] == 3
        assert summary["pipeline"]["connected"] == 1
        assert summary["pipeline"]["responded"] == 1

    def test_conversion_funnel_empty(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)
        funnel = svc.get_conversion_funnel()
        assert funnel == []

    def test_conversion_funnel_with_data(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)

        contact_repo.add(sample_contact(status="not_contacted"))
        contact_repo.add(sample_contact(status="connected"))
        contact_repo.add(sample_contact(status="responded"))

        funnel = svc.get_conversion_funnel()
        assert len(funnel) == 7  # all pipeline stages
        assert funnel[0]["stage"] == "Not Contacted"
        assert funnel[0]["remaining"] == 3

    def test_velocity(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)
        velocity = svc.get_velocity(weeks=4)
        assert len(velocity) == 4

    def test_source_effectiveness(self, json_repos):
        contact_repo, _, _, draft_repo, *_ = json_repos
        svc = AnalyticsService(contact_repo, draft_repo)

        contact_repo.add(sample_contact(source="linkedin_search", status="responded"))
        contact_repo.add(sample_contact(source="linkedin_search", status="connected"))
        contact_repo.add(sample_contact(source="referral", status="responded"))

        summary = svc.get_summary()
        se = summary["source_effectiveness"]
        assert "linkedin_search" in se
        assert se["linkedin_search"]["total"] == 2
        assert se["linkedin_search"]["responded"] == 1
