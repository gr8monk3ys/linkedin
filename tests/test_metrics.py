"""Metrics: labels read from page text, None never zero, one row per day."""

import datetime as dt
from unittest.mock import MagicMock

from linkedin.automation import selectors as sel
from linkedin.automation.budget import Budget
from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.session import LinkedInSession
from linkedin.data.json_store import JsonPostRepo
from linkedin.services.metrics_service import MetricsService
from tests.fake_page import FakeElement, FakePage
from tests.test_session import NoPacer


def page_with_body(text: str) -> FakePage:
    page = FakePage()
    page.register_css("body", FakeElement(text))
    return page


class TestPageReads:
    def test_dashboard_numbers_are_read_by_label(self):
        lp = LinkedInPage(page_with_body("Track performance\n0\nPost impressions in 7 days\n2,498\nTotal followers\n46\nProfile views\n70\nSearch appearances"))
        assert lp.read_dashboard_metrics() == {"followers": 2498, "profile_views": 46, "post_impressions": 0, "search_appearances": 70}
        assert lp.selector_misses == []
        assert lp.page.visited[-1] == sel.DASHBOARD_URL

    def test_a_missing_label_is_none_not_zero(self):
        lp = LinkedInPage(page_with_body("Analytics\n1,240 profile views"))
        out = lp.read_dashboard_metrics()
        assert out["profile_views"] == 1240 and out["post_impressions"] is None
        assert lp.selector_misses == []  # something was read; the page is recognised

    def test_no_labels_at_all_records_a_miss(self):
        lp = LinkedInPage(page_with_body("Something else entirely"))
        assert lp.read_dashboard_metrics() == {"followers": None, "profile_views": None, "post_impressions": None, "search_appearances": None}
        assert lp.selector_misses == ["dashboard_metrics"]

    def test_network_counts_come_from_mynetwork_not_the_capped_profile(self):
        lp = LinkedInPage(page_with_body("Manage my network\nConnections\n2,506\nFollowing & followers\n500+ connections\n2,498 followers"))
        out = lp.read_network_counts()
        assert out["connections"] == 2506 and out["followers_on_profile"] == 2498
        assert lp.page.visited[0] == sel.MY_NETWORK_URL

    def test_ssi_is_read_as_a_score_out_of_100(self):
        assert LinkedInPage(page_with_body("Your Social Selling Index\nCurrent score\n43 out of 100")).read_ssi() == 43
        assert LinkedInPage(page_with_body("SSI 61/100")).read_ssi() == 61
        lp = LinkedInPage(page_with_body("Your Social Selling Index\n0 notifications total"))
        assert lp.read_ssi() is None and lp.selector_misses == ["ssi_score"]

    def test_ssi_discontinued_is_none_without_a_miss(self):
        """Verified live 2026-09-02: the page says access was discontinued. Not a markup change."""
        lp = LinkedInPage(page_with_body("Your Social Selling Index\nYou do not have access to SSI\n0 notifications total"))
        assert lp.read_ssi() is None and lp.selector_misses == []

    def test_post_impressions(self):
        lp = LinkedInPage(page_with_body("Post analytics\n3,201 impressions\n12 reactions"))
        assert lp.read_post_impressions("urn:li:activity:1") == 3201
        assert "urn:li:activity:1" in lp.page.visited[-1]


class TestSessionVerb:
    def test_metrics_reads_everything_and_spends_one(self):
        page = MagicMock()
        page.read_network_counts.return_value = {"connections": 9, "followers_on_profile": 10}
        page.read_dashboard_metrics.return_value = {"followers": None, "profile_views": 5, "post_impressions": None, "search_appearances": 2}
        page.read_ssi.return_value = 40
        page.read_post_impressions.return_value = 77
        s = LinkedInSession(page, Budget.in_memory({"metrics": 1}), pacer=NoPacer())
        r = s.metrics(post_urns=["urn:li:activity:1"])
        assert r and r.data["followers"] == 10 and r.data["connections"] == 9 and r.data["post_impressions"] is None
        assert r.data["posts"] == {"urn:li:activity:1": 77}
        assert s.budget.remaining("metrics") == 0
        assert s.metrics().status == "refused"

    def test_dry_run_reads_but_spends_nothing(self):
        page = MagicMock()
        page.read_network_counts.return_value = {}
        page.read_dashboard_metrics.return_value = {}
        page.read_ssi.return_value = None
        s = LinkedInSession(page, Budget.in_memory({"metrics": 1}), pacer=NoPacer(), dry_run=True)
        assert s.metrics()
        assert s.budget.remaining("metrics") == 1


class TestStore:
    def _svc(self, tmp_path):
        return MetricsService(tmp_path / "metrics.json", JsonPostRepo(tmp_path / "posts.json"))

    def test_record_upserts_one_row_per_day_and_keeps_none(self, tmp_path):
        svc = self._svc(tmp_path)
        day = dt.date(2026, 9, 2)
        svc.record({"followers": 10, "connections": None, "profile_views": 3}, day=day)
        svc.record({"followers": 11, "connections": None, "profile_views": 3}, day=day)
        (row,) = svc.rows()
        assert row["followers"] == 11 and row["connections"] is None and row["ssi"] is None

    def test_delta_uses_the_newest_row_at_least_n_days_old(self, tmp_path):
        svc = self._svc(tmp_path)
        svc.record({"followers": 100}, day=dt.date(2026, 8, 20))
        svc.record({"followers": 110}, day=dt.date(2026, 8, 26))
        svc.record({"followers": 125}, day=dt.date(2026, 9, 2))
        assert svc.delta("followers", 7) == 15
        assert svc.delta("followers", 30) is None
        assert svc.delta("ssi", 7) is None

    def test_post_impressions_land_on_the_post_record(self, tmp_path):
        svc = self._svc(tmp_path)
        svc.posts.add({"id": 1, "urn": "urn:li:activity:1", "text": "x", "posted_at": "2026-09-01T09:00:00"})
        svc.record({"posts": {"urn:li:activity:1": 42, "urn:li:activity:9": None}}, day=dt.date(2026, 9, 2))
        assert svc.posts.get(1)["impressions"] == 42
        assert svc.summary()[0]["metric"] == "followers"
