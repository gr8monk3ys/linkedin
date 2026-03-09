"""Smoke tests for web state modules — verify service construction is correct."""

from unittest.mock import patch

import pytest

from linkedin.types import Result
from tests.conftest import sample_company, sample_contact, sample_profile

pytest.importorskip("reflex")


def _patch_repos(module_path, json_repos):
    """Return a patch that replaces create_repos in the given module."""
    return patch(f"{module_path}.create_repos", return_value=json_repos)


class TestDashboardState:
    def test_load_dashboard_empty(self, json_repos):
        from linkedin.web.states.dashboard_state import DashboardState

        state = DashboardState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.dashboard_state", json_repos):
            state.load_dashboard()
        assert state.total_contacts == 0

    def test_load_dashboard_with_data(self, json_repos):
        from linkedin.web.states.dashboard_state import DashboardState

        contact_repo, company_repo, profile_repo, draft_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(id=1, status="responded", follow_up_date="2020-01-01"))
        company_repo.add(sample_company(id=1))
        draft_repo.add({"id": 1, "type": "connection", "content": "Hello"})

        state = DashboardState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.dashboard_state", json_repos):
            state.load_dashboard()
        assert state.total_contacts == 1
        assert state.total_companies == 1
        assert state.total_drafts == 1
        assert state.pipeline_data == [{"status": "Responded", "count": 1}]
        assert state.overdue_followups[0]["name"] == "Test User"
        assert state.suggested_actions


class TestCompaniesState:
    def test_load_companies_empty(self, json_repos):
        from linkedin.web.states.companies_state import CompaniesState

        state = CompaniesState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.companies_state", json_repos):
            state.load_companies()
        assert state.companies == []

    def test_add_company(self, json_repos):
        from linkedin.web.states.companies_state import CompaniesState

        state = CompaniesState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.companies_state", json_repos):
            state.add_company({
                "name": "TestCo",
                "industry": "Tech",
                "size": "51-200",
                "linkedin_url": "",
                "website": "",
                "why_target": "Great culture",
                "priority": "high",
            })
        assert len(state.companies) == 1

    def test_select_company_unwraps_service_results(self, json_repos):
        from linkedin.web.states.companies_state import CompaniesState

        contact_repo, company_repo, *_ = json_repos
        company_repo.add(sample_company(id=1))
        contact_repo.add(sample_contact(id=1, company_id=1))

        state = CompaniesState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.companies_state", json_repos):
            state.select_company(1)

        assert state.selected_company["name"] == "TestCo"
        assert len(state.company_contacts) == 1
        assert state.company_contacts[0]["name"] == "Test User"


class TestContactsState:
    def test_add_contact(self, json_repos):
        from linkedin.web.states.contacts_state import ContactsState

        contact_repo, *_ = json_repos
        state = ContactsState()  # type: ignore[call-arg]

        with _patch_repos("linkedin.web.states.contacts_state", json_repos):
            state.add_contact({
                "name": "Jane Doe",
                "title": "Engineer",
                "company": "Acme",
                "linkedin_url": "https://linkedin.com/in/jane",
                "notes": "Met at meetup",
                "source": "linkedin_search",
            })

        assert len(contact_repo.list_all()) == 1
        assert contact_repo.list_all()[0]["linkedin_url"] == "https://linkedin.com/in/jane"
        assert len(state.contacts) == 1


class TestDiscoverState:
    @patch("linkedin.services.discover_service.generate_ai_text", return_value=("Suggestions here", None))
    def test_discover_contacts(self, _mock_ai, json_repos):
        from linkedin.web.states.discover_state import DiscoverState

        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        state = DiscoverState()  # type: ignore[call-arg]
        state.role = "Engineer"
        state.discover_type = "contacts"
        with _patch_repos("linkedin.web.states.discover_state", json_repos):
            state.discover()
        assert "Suggestions" in state.suggestions


class TestResearchState:
    def test_load_engagement(self, json_repos):
        from linkedin.web.states.research_state import ResearchState

        state = ResearchState()  # type: ignore[call-arg]
        with _patch_repos("linkedin.web.states.research_state", json_repos):
            state.load_engagement()
        assert len(state.engagement_content) > 0

    def test_generate_ideas_uses_service_contract(self, json_repos):
        from linkedin.web.states.research_state import ResearchState

        state = ResearchState()  # type: ignore[call-arg]
        with (
            _patch_repos("linkedin.web.states.research_state", json_repos),
            patch(
                "linkedin.services.research_service.ResearchService.generate_ideas",
                return_value=Result(None, ("AI roles", "Idea list")),
            ),
        ):
            state.generate_ideas()

        assert state.post_ideas == "Idea list"
        assert state.loading is False

    def test_generate_draft_post_uses_service_contract(self, json_repos):
        from linkedin.web.states.research_state import ResearchState

        state = ResearchState()  # type: ignore[call-arg]
        state.post_topic = "Networking lessons"
        with (
            _patch_repos("linkedin.web.states.research_state", json_repos),
            patch(
                "linkedin.services.research_service.ResearchService.generate_post_draft",
                return_value=Result(None, "Draft post"),
            ),
        ):
            state.generate_draft_post()

        assert state.post_draft == "Draft post"
        assert state.loading is False

    def test_generate_hashtags_uses_service_contract(self, json_repos):
        from linkedin.web.states.research_state import ResearchState

        state = ResearchState()  # type: ignore[call-arg]
        with (
            _patch_repos("linkedin.web.states.research_state", json_repos),
            patch(
                "linkedin.services.research_service.ResearchService.generate_hashtags",
                return_value=Result(None, "#python #ai"),
            ),
        ):
            state.generate_hashtags()

        assert state.hashtags == "#python #ai"
        assert state.loading is False
