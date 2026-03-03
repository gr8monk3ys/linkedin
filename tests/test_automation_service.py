"""Tests for AutomationService."""

import sys
from unittest.mock import MagicMock, patch

# Mock optional dependencies (playwright, keyring) before importing automation modules
_pw_mock = MagicMock()
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", _pw_mock)
sys.modules.setdefault("keyring", MagicMock())

from tests.conftest import sample_company, sample_contact, sample_profile  # noqa: E402


class TestBuildSearchQueries:
    """Tests for _build_search_queries()."""

    def _svc(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo)

    def test_no_profile_returns_empty(self, json_repos):
        svc = self._svc(json_repos)
        queries = svc._build_search_queries()
        assert queries == []

    def test_no_target_role_returns_empty(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile(target_role=""))
        svc = self._svc(json_repos)
        queries = svc._build_search_queries()
        assert queries == []

    def test_company_queries_priority_1(self, json_repos):
        _, company_repo, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        company_repo.add(sample_company(id=1, name="Google"))
        company_repo.add(sample_company(id=2, name="Meta"))

        svc = self._svc(json_repos)
        queries = svc._build_search_queries()

        company_queries = [q for q in queries if q["priority"] == 1]
        assert len(company_queries) == 2
        assert any("Google" in q["query"] for q in company_queries)
        assert any("Meta" in q["query"] for q in company_queries)
        assert all("Senior Software Engineer" in q["query"] for q in company_queries)

    def test_second_degree_query_priority_2(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        svc = self._svc(json_repos)
        queries = svc._build_search_queries()

        second_deg = [q for q in queries if q["priority"] == 2]
        assert len(second_deg) == 1
        assert second_deg[0]["network"] == "S"
        assert second_deg[0]["query"] == "Senior Software Engineer"

    def test_industry_query_priority_3(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile(industries="Technology, SaaS"))

        svc = self._svc(json_repos)
        queries = svc._build_search_queries()

        industry = [q for q in queries if q["priority"] == 3]
        assert len(industry) == 1
        assert "Technology, SaaS" in industry[0]["query"]
        assert "Senior Software Engineer" in industry[0]["query"]

    def test_no_industries_skips_priority_3(self, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile(industries=""))

        svc = self._svc(json_repos)
        queries = svc._build_search_queries()

        industry = [q for q in queries if q["priority"] == 3]
        assert len(industry) == 0


class TestDeduplication:
    """Tests for deduplication in _search_and_collect()."""

    def _svc(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo)

    @patch("linkedin.automation.actions.search.search_people")
    def test_skips_existing_contacts(self, mock_search, json_repos):
        from linkedin.automation.rate_limiter import RateLimiter
        from linkedin.automation.safety import SafetyLimits

        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(id=1, linkedin_url="https://linkedin.com/in/alice"))

        mock_search.return_value = [
            {"name": "Alice", "headline": "Engineer", "url": "https://linkedin.com/in/alice"},
            {"name": "Bob", "headline": "Designer", "url": "https://linkedin.com/in/bob"},
        ]

        svc = self._svc(json_repos)
        linkedin_mock = MagicMock()
        candidates = svc._search_and_collect(
            linkedin_mock,
            [{"query": "test", "network": "", "priority": 1}],
            SafetyLimits(),
            RateLimiter(),
        )

        assert len(candidates) == 1
        assert candidates[0]["name"] == "Bob"

    @patch("linkedin.automation.actions.search.search_people")
    def test_deduplicates_across_queries(self, mock_search, json_repos):
        from linkedin.automation.rate_limiter import RateLimiter
        from linkedin.automation.safety import SafetyLimits

        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_search.return_value = [
            {"name": "Charlie", "headline": "PM", "url": "https://linkedin.com/in/charlie"},
        ]

        svc = self._svc(json_repos)
        linkedin_mock = MagicMock()
        candidates = svc._search_and_collect(
            linkedin_mock,
            [
                {"query": "query1", "network": "", "priority": 1},
                {"query": "query2", "network": "", "priority": 2},
            ],
            SafetyLimits(),
            RateLimiter(),
        )

        # Charlie appears in both queries but should only be collected once
        assert len(candidates) == 1

    @patch("linkedin.automation.actions.search.search_people")
    def test_skips_results_without_url(self, mock_search, json_repos):
        from linkedin.automation.rate_limiter import RateLimiter
        from linkedin.automation.safety import SafetyLimits

        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_search.return_value = [
            {"name": "NoUrl", "headline": "Engineer", "url": ""},
            {"name": "HasUrl", "headline": "Designer", "url": "https://linkedin.com/in/hasurl"},
        ]

        svc = self._svc(json_repos)
        candidates = svc._search_and_collect(
            MagicMock(),
            [{"query": "test", "network": "", "priority": 1}],
            SafetyLimits(),
            RateLimiter(),
        )

        assert len(candidates) == 1
        assert candidates[0]["name"] == "HasUrl"


class TestConnectionNoteGeneration:
    """Tests for _generate_connection_note()."""

    def _svc(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo)

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hi Jane, love your ML work!")
    def test_generates_note_with_profile_and_person_info(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        profile = sample_profile()
        person_info = {"name": "Jane", "headline": "ML Engineer at Google", "location": "NYC"}

        note = svc._generate_connection_note(profile, person_info)

        assert note == "Hi Jane, love your ML work!"
        mock_ai.assert_called_once()

        # Verify the prompt includes both profile and person info
        prompt = mock_ai.call_args[0][0]
        assert "Senior Software Engineer" in prompt  # target_role from profile
        assert "Jane" in prompt
        assert "ML Engineer at Google" in prompt
        assert "NYC" in prompt

    def test_returns_empty_without_profile(self, json_repos):
        svc = self._svc(json_repos)
        note = svc._generate_connection_note(None, {"name": "Jane"})
        assert note == ""


class TestExtractCompany:
    """Tests for _extract_company()."""

    def test_extracts_company_with_at(self):
        from linkedin.services.automation_service import AutomationService

        assert AutomationService._extract_company("Engineer at Google") == "Google"

    def test_extracts_company_with_at_sign(self):
        from linkedin.services.automation_service import AutomationService

        assert AutomationService._extract_company("Engineer @ Meta") == "Meta"

    def test_returns_empty_without_separator(self):
        from linkedin.services.automation_service import AutomationService

        assert AutomationService._extract_company("Software Engineer") == ""


class TestRunConnect:
    """Tests for the full run_connect() pipeline."""

    def _svc(self, json_repos, config=None):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo, config)

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hi there!")
    @patch("linkedin.automation.actions.connect.send_connection", return_value=True)
    @patch("linkedin.automation.actions.search.search_people")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_full_pipeline(self, mock_bm, mock_login, mock_search, mock_send, mock_ai, json_repos):
        _, company_repo, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        company_repo.add(sample_company(id=1, name="Google"))

        # Mock browser context manager
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        # Mock LinkedInPage methods
        mock_page_info = {"name": "Alice Smith", "headline": "Engineer at Google", "location": "SF"}
        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_profile_info.return_value = mock_page_info

            mock_search.return_value = [
                {"name": "Alice", "headline": "Engineer", "url": "https://linkedin.com/in/alice"},
            ]

            svc = self._svc(json_repos)
            results = svc.run_connect(limit=5)

        assert len(results) == 1
        assert results[0]["success"] is True
        assert results[0]["name"] == "Alice Smith"
        assert results[0]["company"] == "Google"
        assert results[0]["note"] == "Hi there!"
        mock_ai.assert_called_once()
        mock_send.assert_called_once()

    @patch("linkedin.automation.actions.login.login_action", return_value=False)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_login_failure(self, mock_bm, mock_login, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        svc = self._svc(json_repos)
        results = svc.run_connect()

        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["reason"] == "Login failed"

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hello!")
    @patch("linkedin.automation.actions.connect.send_connection", return_value=True)
    @patch("linkedin.automation.actions.search.search_people")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_respects_limit(self, mock_bm, mock_login, mock_search, mock_send, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_profile_info.return_value = {"name": "Person", "headline": "Dev", "location": ""}

            mock_search.return_value = [
                {"name": f"Person{i}", "headline": "Dev", "url": f"https://linkedin.com/in/person{i}"}
                for i in range(10)
            ]

            svc = self._svc(json_repos)
            results = svc.run_connect(limit=3)

        assert len(results) == 3

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hello!")
    @patch("linkedin.automation.actions.connect.send_connection", return_value=True)
    @patch("linkedin.automation.actions.search.search_people")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_adds_contacts_to_crm(self, mock_bm, mock_login, mock_search, mock_send, mock_ai, json_repos):
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_profile_info.return_value = {
                "name": "Bob Jones",
                "headline": "PM at Stripe",
                "location": "NYC",
            }

            mock_search.return_value = [
                {"name": "Bob", "headline": "PM", "url": "https://linkedin.com/in/bob"},
            ]

            svc = self._svc(json_repos)
            svc.run_connect(limit=5)

        # Verify contact was added to CRM
        contacts = contact_repo.list_all()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Bob Jones"
        assert contacts[0]["source"] == "automation"
        assert contacts[0]["status"] == "connection_sent"


class TestRunConnectDryRun:
    """Tests for dry_run mode."""

    def _svc(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo)

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hi!")
    @patch("linkedin.automation.actions.connect.send_connection", return_value=True)
    @patch("linkedin.automation.actions.search.search_people")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_dry_run_passes_flag_to_send_connection(self, mock_bm, mock_login, mock_search, mock_send, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_profile_info.return_value = {"name": "Eve", "headline": "Dev", "location": "LA"}

            mock_search.return_value = [
                {"name": "Eve", "headline": "Dev", "url": "https://linkedin.com/in/eve"},
            ]

            svc = self._svc(json_repos)
            results = svc.run_connect(limit=5, dry_run=True)

        assert len(results) == 1
        assert results[0]["success"] is True
        # Verify dry_run was passed through
        _, kwargs = mock_send.call_args
        assert kwargs["dry_run"] is True

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Hi!")
    @patch("linkedin.automation.actions.connect.send_connection", return_value=True)
    @patch("linkedin.automation.actions.search.search_people")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_dry_run_still_generates_notes(self, mock_bm, mock_login, mock_search, mock_send, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_profile_info.return_value = {"name": "Eve", "headline": "Dev", "location": "LA"}

            mock_search.return_value = [
                {"name": "Eve", "headline": "Dev", "url": "https://linkedin.com/in/eve"},
            ]

            svc = self._svc(json_repos)
            results = svc.run_connect(limit=5, dry_run=True)

        assert results[0]["note"] == "Hi!"
        mock_ai.assert_called_once()


class TestGetStatus:
    """Tests for get_status()."""

    def test_returns_safety_summary(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        svc = AutomationService(contact_svc, company_repo, profile_repo)

        status = svc.get_status()
        assert "connections_sent" in status
        assert "connections_remaining" in status
        assert "messages_sent" in status
        assert "messages_remaining" in status
        assert "profile_views" in status
        assert "searches" in status
        assert status["connections_sent"] == 0
        assert status["connections_remaining"] == 20


class TestLogin:
    """Tests for login()."""

    @patch("linkedin.automation.actions.login.setup_credentials")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_login_with_credentials(self, mock_bm, mock_login, mock_setup, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        svc = AutomationService(contact_svc, company_repo, profile_repo)

        mock_browser = MagicMock()
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.login(email="test@example.com", password="secret")

        assert result is True
        mock_setup.assert_called_once_with("test@example.com", "secret")
        mock_login.assert_called_once()

    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_login_without_credentials_uses_keyring(self, mock_bm, mock_login, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        svc = AutomationService(contact_svc, company_repo, profile_repo)

        mock_browser = MagicMock()
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        result = svc.login()

        assert result is True
        mock_login.assert_called_once_with(mock_browser, None, None)
