"""Tests for service layer."""

from datetime import datetime, timedelta
from enum import Enum
from unittest.mock import patch

import pytest

from tests.conftest import sample_company, sample_contact, sample_profile


class TestContactService:
    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def test_add_and_list(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        contacts = svc.list_contacts()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Alice"

    def test_get_contact(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        contact = svc.get_contact(1)
        assert contact is not None
        assert contact["name"] == "Alice"

    def test_update_status(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, status="connected")
        contact = svc.get_contact(1)
        assert contact["status"] == "connected"

    def test_get_stats(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.add_contact(name="Bob", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, status="connected")
        stats = svc.get_stats()
        assert stats["total"] == 2
        assert stats["status_counts"]["not_contacted"] == 1
        assert stats["status_counts"]["connected"] == 1

    def test_get_stats_empty(self, json_repos):
        svc = self._svc(json_repos)
        stats = svc.get_stats()
        assert stats["total"] == 0

    def test_update_notes(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, notes="Had a great call")
        contact = svc.get_contact(1)
        assert "great call" in contact["notes"]

    def test_update_nonexistent(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.update_contact(999, status="connected") is None

    def test_view_contact(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        view = svc.view_contact(1)
        assert view is not None
        assert view["name"] == "Alice"

    def test_view_contact_not_found(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.view_contact(999) is None

    def test_view_contact_with_company_link(self, json_repos):
        from linkedin.services.company_service import CompanyService

        contact_repo, company_repo, *_ = json_repos
        svc = self._svc(json_repos)
        co_svc = CompanyService(company_repo, contact_repo)
        co_svc.add_company(name="Acme", industry="Tech")
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="", company_id=1)
        view = svc.view_contact(1)
        assert view["linked_company"] is not None
        assert view["linked_company"]["name"] == "Acme"

    def test_get_activities(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, status="connected")
        activities = svc.get_activities(1)
        assert len(activities) == 1
        assert activities[0]["type"] == "connected"

    def test_get_activities_not_found(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.get_activities(999) is None

    def test_link_company(self, json_repos):
        from linkedin.services.company_service import CompanyService

        contact_repo, company_repo, *_ = json_repos
        svc = self._svc(json_repos)
        CompanyService(company_repo, contact_repo).add_company(name="Acme", industry="Tech")
        svc.add_contact(name="Alice", title="Engineer", company="Other", linkedin="")
        error = svc.link_company(1, 1)
        assert error is None
        contact = svc.get_contact(1)
        assert contact["company"] == "Acme"
        assert contact["company_id"] == 1

    def test_link_company_not_found(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        assert svc.link_company(1, 999) is not None
        assert svc.link_company(999, 1) is not None

    def test_set_reminder(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        result = svc.set_reminder(1, days=7)
        assert result is not None
        contact = svc.get_contact(1)
        assert contact["follow_up_date"] is not None

    def test_set_reminder_with_date(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        result = svc.set_reminder(1, date="2025-06-15")
        assert result == "2025-06-15"

    def test_set_reminder_not_found(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.set_reminder(999, days=7) is None

    def test_get_due_contacts_empty(self, json_repos):
        svc = self._svc(json_repos)
        due = svc.get_due_contacts()
        assert due["overdue"] == []
        assert due["due_today"] == []

    def test_get_due_contacts_with_overdue(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        svc.set_reminder(1, date=yesterday)
        due = svc.get_due_contacts()
        assert len(due["overdue"]) == 1

    def test_get_next_actions_includes_overdue_followup(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        svc.set_reminder(1, date=yesterday)

        actions = svc.get_next_actions()
        assert len(actions) >= 1
        assert actions[0]["action"] == "follow_up_overdue"
        assert actions[0]["contact_id"] == 1

    def test_get_next_actions_includes_connected_message_prompt(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, status="connected")
        contact = svc.get_contact(1)
        contact["last_contact"] = (datetime.now() - timedelta(days=10)).isoformat()
        svc.contacts.update(contact)

        actions = svc.get_next_actions()
        assert any(a["action"] == "send_first_message" and a["contact_id"] == 1 for a in actions)

    def test_list_contacts_filter_status(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.add_contact(name="Bob", title="Engineer", company="TestCo", linkedin="")
        svc.update_contact(1, status="connected")
        filtered = svc.list_contacts(status="connected")
        assert len(filtered) == 1
        assert filtered[0]["name"] == "Alice"

    def test_list_contacts_filter_company(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.add_contact(name="Bob", title="Engineer", company="Other", linkedin="")
        filtered = svc.list_contacts(company="Acme")
        assert len(filtered) == 1

    def test_add_contact_with_company_id(self, json_repos):
        from linkedin.services.company_service import CompanyService

        contact_repo, company_repo, *_ = json_repos
        svc = self._svc(json_repos)
        CompanyService(company_repo, contact_repo).add_company(name="Acme", industry="Tech")
        result = svc.add_contact(name="Alice", title="Engineer", company="", linkedin="", company_id=1)
        assert result["company"] == "Acme"

    def test_add_contact_invalid_company_id(self, json_repos):
        svc = self._svc(json_repos)
        result = svc.add_contact(name="Alice", title="Engineer", company="", linkedin="", company_id=999)
        assert isinstance(result, str)  # error message

    def test_add_contact_with_referral(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        result = svc.add_contact(name="Bob", title="Designer", company="TestCo", linkedin="", referral_id=1)
        assert result["referral_contact_id"] == 1

    def test_add_contact_invalid_referral(self, json_repos):
        svc = self._svc(json_repos)
        result = svc.add_contact(name="Bob", title="Designer", company="TestCo", linkedin="", referral_id=999)
        assert isinstance(result, str)  # error message

    def test_find_duplicate_candidates(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(
            name="Alice Smith",
            title="Engineer",
            company="Acme",
            linkedin="https://linkedin.com/in/alice-smith",
            email="alice@example.com",
        )
        svc.add_contact(
            name="Alice S.",
            title="Engineer",
            company="Acme",
            linkedin="https://linkedin.com/in/alice-smith",
            email="alice@example.com",
        )

        candidates = svc.find_duplicate_candidates()
        assert len(candidates) >= 1
        assert candidates[0]["confidence"] in {"high", "medium"}
        assert "email" in candidates[0]["signals"]

    def test_merge_contacts_updates_referrals(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice Smith", title="Engineer", company="Acme", linkedin="", notes="Met at meetup")
        svc.add_contact(name="Alice S", title="Sr Engineer", company="Acme", linkedin="", notes="Had coffee chat")
        svc.add_contact(name="Bob", title="Manager", company="Acme", linkedin="", referral_id=2)

        merged = svc.merge_contacts(1, 2)
        assert isinstance(merged, dict)
        assert merged["id"] == 1
        assert svc.get_contact(2) is None
        assert "meetup" in merged["notes"]
        assert "coffee chat" in merged["notes"]
        referred = svc.get_contact(3)
        assert referred["referral_contact_id"] == 1

    def test_campaign_enroll_and_due(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        enrolled = svc.enroll_campaign(1, campaign_name="networking_21d", start_date=datetime.now().strftime("%Y-%m-%d"))
        assert isinstance(enrolled, dict)

        due = svc.get_due_campaign_steps(limit=5)
        assert len(due) == 1
        assert due[0]["contact_id"] == 1
        assert due[0]["step_label"] == "Send connection request"

    def test_campaign_advance_to_completion(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        svc.enroll_campaign(1, campaign_name="networking_21d")

        for _ in range(4):
            result = svc.advance_campaign(1)
            assert isinstance(result, dict)

        status = svc.campaign_status(1)
        assert status is not None
        assert status["active"] is False
        assert status["completed_at"] is not None

    def test_campaign_enroll_unknown_campaign(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="TestCo", linkedin="")
        result = svc.enroll_campaign(1, campaign_name="unknown_campaign")
        assert isinstance(result, str)


class TestCompanyService:
    def _svc(self, json_repos):
        from linkedin.services.company_service import CompanyService

        _, company_repo, *_ = json_repos
        contact_repo = json_repos[0]
        return CompanyService(company_repo, contact_repo)

    def test_add_and_list(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme Corp", industry="Tech")
        companies = svc.list_companies()
        assert len(companies) == 1
        assert companies[0]["name"] == "Acme Corp"

    def test_delete(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme Corp", industry="Tech")
        assert svc.delete_company(1) is not None
        assert svc.list_companies() == []

    def test_delete_nonexistent(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.delete_company(999) is None

    def test_get_company(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme Corp", industry="Tech")
        company = svc.get_company(1)
        assert company is not None
        assert company["name"] == "Acme Corp"
        assert "contacts" in company

    def test_get_company_not_found(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.get_company(999) is None

    def test_update_company(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme Corp", industry="Tech")
        updated = svc.update_company(1, priority="high", notes="Top target")
        assert updated is not None
        assert updated["priority"] == "high"
        assert "Top target" in updated["notes"]

    def test_update_add_role(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme Corp", industry="Tech")
        updated = svc.update_company(1, add_role="Senior Engineer")
        assert "Senior Engineer" in updated["key_people_to_find"]

    def test_update_nonexistent(self, json_repos):
        svc = self._svc(json_repos)
        assert svc.update_company(999, priority="high") is None

    def test_list_filter_priority(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme", industry="Tech", priority="high")
        svc.add_company(name="Beta", industry="Finance", priority="low")
        high = svc.list_companies(priority="high")
        assert len(high) == 1
        assert high[0]["name"] == "Acme"

    def test_list_filter_industry(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_company(name="Acme", industry="Tech")
        svc.add_company(name="Beta", industry="Finance")
        tech = svc.list_companies(industry="Tech")
        assert len(tech) == 1

    def test_get_company_contacts(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        svc = self._svc(json_repos)
        c_svc = ContactService(contact_repo, company_repo)
        svc.add_company(name="Acme", industry="Tech")
        c_svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="", company_id=1)
        company, contacts = svc.get_company_contacts(1)
        assert company is not None
        assert len(contacts) == 1


class TestProfileService:
    def test_save_and_get(self, json_repos):
        from linkedin.services.profile_service import ProfileService

        _, _, profile_repo, *_ = json_repos
        svc = ProfileService(profile_repo)
        svc.save_profile(sample_profile())
        profile = svc.get_profile()
        assert profile["name"] == "Test User"
        assert profile["target_role"] == "Senior Software Engineer"


class TestDraftService:
    def _svc(self, json_repos):
        from linkedin.services.draft_service import DraftService

        contact_repo, _, profile_repo, draft_repo, *_= json_repos
        return DraftService(draft_repo, contact_repo, profile_repo)

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Hi Alice!")
    def test_generate_connection(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        error, draft = svc.generate_connection(1)
        assert error is None
        assert draft == "Hi Alice!"

    def test_generate_connection_no_profile(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo = json_repos[0]
        contact_repo.add(sample_contact(id=1))

        error, draft = svc.generate_connection(1)
        assert error is not None
        assert "profile" in error.lower()

    def test_generate_connection_contact_not_found(self, json_repos):
        svc = self._svc(json_repos)
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        error, draft = svc.generate_connection(999)
        assert error is not None
        assert "not found" in error.lower()

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Great message")
    def test_generate_message(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        error, draft = svc.generate_message(1, context="Discuss job opening")
        assert error is None
        assert draft == "Great message"

    def test_generate_message_contact_not_found(self, json_repos):
        svc = self._svc(json_repos)
        error, draft = svc.generate_message(999)
        assert error is not None

    def test_generate_connection_fallback_when_ai_unavailable(self, json_repos, monkeypatch):
        from linkedin.services.draft_service import AIClientError

        monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "1")
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        with patch("linkedin.services.draft_service.generate_with_ai", side_effect=AIClientError("AI down")):
            error, draft = svc.generate_connection(1)
        assert error is None
        assert "Alice" in draft

    def test_generate_connection_fallback_disabled_returns_error(self, json_repos, monkeypatch):
        from linkedin.services.draft_service import AIClientError

        monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "0")
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        with patch("linkedin.services.draft_service.generate_with_ai", side_effect=AIClientError("AI down")):
            error, draft = svc.generate_connection(1)
        assert error is not None
        assert draft == ""

    def test_fallback_is_reported_not_silent(self, json_repos, monkeypatch):
        """A template must never be handed back as if the AI wrote it.

        The API key lives in cron.env, so scheduled runs get real drafts while
        every interactive command quietly degrades — with no way to tell.
        """
        from linkedin.services.draft_service import AIClientError

        monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "1")
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        with patch("linkedin.services.draft_service.generate_with_ai", side_effect=AIClientError("AI down")):
            svc.generate_connection(1)
        assert svc.last_draft_was_fallback is True
        assert "AI down" in (svc.last_draft_error or "")

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Real draft")
    def test_ai_success_is_not_flagged_as_fallback(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        svc.generate_connection(1)
        assert svc.last_draft_was_fallback is False

    def test_fallback_does_not_paste_context_into_the_message(self, json_repos, monkeypatch):
        """`context` is prompt input, not body text.

        With AI up it steers the model; with AI down the template spliced it in
        verbatim, so a --context of instructions became the message itself —
        addressed to a real person, under the user's real name.
        """
        from linkedin.services.draft_service import AIClientError

        monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "1")
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))
        instructions = "Keep it brief and warm — thank him and give three days"

        with patch("linkedin.services.draft_service.generate_with_ai", side_effect=AIClientError("AI down")):
            error, draft = svc.generate_message(1, context=instructions)

        assert error is None
        assert instructions not in draft
        assert "Keep it brief" not in draft
        assert "Alice" in draft

    def test_fallback_thank_you_also_drops_context(self, json_repos, monkeypatch):
        from linkedin.services.draft_service import AIClientError

        monkeypatch.setenv("LINKEDIN_AI_FALLBACK_ENABLED", "1")
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        with patch("linkedin.services.draft_service.generate_with_ai", side_effect=AIClientError("AI down")):
            _, draft = svc.generate_thank_you(1, context="mention the ML platform team specifically")

        assert "mention the ML platform team" not in draft

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Intro message")
    def test_generate_intro_request(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))
        contact_repo.add(sample_contact(name="Bob", id=2))

        error, draft = svc.generate_intro_request(1, 2)
        assert error is None
        assert draft == "Intro message"

    def test_generate_intro_no_profile(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo = json_repos[0]
        contact_repo.add(sample_contact(id=1))
        error, _ = svc.generate_intro_request(1, 1)
        assert error is not None

    def test_generate_intro_target_not_found(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(id=1))
        error, _ = svc.generate_intro_request(1, 999)
        assert error is not None

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Thanks!")
    def test_generate_thank_you(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        error, draft = svc.generate_thank_you(1)
        assert error is None

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Follow up")
    def test_generate_follow_up(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))

        error, draft = svc.generate_follow_up(1, attempt=2)
        assert error is None

    @patch("linkedin.services.draft_service.generate_with_ai", return_value="Connect!")
    def test_generate_batch_connections(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        contact_repo, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())
        contact_repo.add(sample_contact(name="Alice", id=1))
        contact_repo.add(sample_contact(name="Bob", id=2))

        error, results = svc.generate_batch_connections(limit=2)
        assert error is None
        assert len(results) == 2

    def test_generate_batch_no_profile(self, json_repos):
        svc = self._svc(json_repos)
        error, results = svc.generate_batch_connections()
        assert error is not None

    def test_list_drafts(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo = json_repos[0]
        contact_repo.add(sample_contact(name="Alice", id=1))
        svc.save_draft(1, "connection", "Hello!")
        drafts = svc.list_drafts()
        assert len(drafts) == 1
        assert drafts[0]["contact_name"] == "Alice"

    def test_save_draft(self, json_repos):
        svc = self._svc(json_repos)
        saved = svc.save_draft(1, "connection", "Hello!")
        assert saved["content"] == "Hello!"
        assert svc.get_draft(saved["id"]) is not None


class TestDiscoverService:
    @patch("linkedin.services.discover_service.generate_with_ai", return_value="Suggestion 1\nSuggestion 2")
    def test_discover_contacts_by_role(self, mock_ai, json_repos):
        from linkedin.services.discover_service import DiscoverService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        svc = DiscoverService(profile_repo, company_repo, contact_repo)
        profile_repo.save(sample_profile())

        error, result = svc.discover_contacts(role="Engineer")
        assert error is None
        assert "Suggestion" in result

    @patch("linkedin.services.discover_service.generate_with_ai", return_value="People at Google")
    def test_discover_contacts_by_company(self, mock_ai, json_repos):
        from linkedin.services.discover_service import DiscoverService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        svc = DiscoverService(profile_repo, company_repo, contact_repo)
        profile_repo.save(sample_profile())

        error, result = svc.discover_contacts(company="Google")
        assert error is None

    def test_discover_contacts_no_profile(self, json_repos):
        from linkedin.services.discover_service import DiscoverService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        svc = DiscoverService(profile_repo, company_repo, contact_repo)
        error, _ = svc.discover_contacts(role="Engineer")
        assert error is not None

    def test_discover_contacts_no_args(self, json_repos):
        from linkedin.services.discover_service import DiscoverService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        svc = DiscoverService(profile_repo, company_repo, contact_repo)
        profile_repo.save(sample_profile())
        error, _ = svc.discover_contacts()
        assert error is not None

    @patch("linkedin.services.discover_service.generate_with_ai", return_value="Company suggestions")
    def test_discover_companies(self, mock_ai, json_repos):
        from linkedin.services.discover_service import DiscoverService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        svc = DiscoverService(profile_repo, company_repo, contact_repo)
        profile_repo.save(sample_profile())

        error, result = svc.discover_companies()
        assert error is None


class TestResearchService:
    def _svc(self, json_repos):
        from linkedin.services.research_service import ResearchService

        _, _, profile_repo, draft_repo, research_repo, *_ = json_repos
        return ResearchService(profile_repo, research_repo, draft_repo)

    def test_engagement_strategies(self, json_repos):
        svc = self._svc(json_repos)
        content = svc.get_engagement_strategies()
        assert len(content) > 0

    @patch("linkedin.services.research_service.generate_with_ai", return_value="Post idea 1")
    def test_generate_ideas(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        topic, ideas = svc.generate_ideas()
        assert "idea" in ideas.lower()

    @patch("linkedin.services.research_service.generate_with_ai", return_value="Ideas about AI")
    def test_generate_ideas_with_topic(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        topic, ideas = svc.generate_ideas(topic="AI")
        assert topic == "AI"

    @patch("linkedin.services.research_service.generate_with_ai", return_value="A great post about tech")
    def test_generate_post_draft(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        content = svc.generate_post_draft("AI trends", style="story")
        assert len(content) > 0

    def test_save_ideas(self, json_repos):
        svc = self._svc(json_repos)
        svc.save_ideas("AI", "Some ideas about AI")
        _, _, _, _, research_repo, *_ = json_repos
        data = research_repo.get()
        assert len(data["ideas"]) == 1
        assert data["ideas"][0]["topic"] == "AI"

    @patch("linkedin.services.research_service.generate_with_ai", return_value="A great post")
    def test_save_post_draft(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        svc.save_post_draft("AI", "story", "A great post")
        _, _, _, draft_repo, *_= json_repos
        drafts = draft_repo.list_all()
        assert len(drafts) == 1
        assert drafts[0]["type"] == "post_story"

    @patch("linkedin.services.research_service.generate_with_ai", return_value="#AI #ML #Tech")
    def test_generate_hashtags(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        result = svc.generate_hashtags("artificial intelligence")
        assert "#" in result


class TestDashboardService:
    def _svc(self, json_repos):
        from linkedin.services.dashboard_service import DashboardService

        contact_repo, company_repo, profile_repo, draft_repo, *_= json_repos
        return DashboardService(profile_repo, contact_repo, company_repo, draft_repo)

    def test_empty_dashboard(self, json_repos):
        svc = self._svc(json_repos)
        data = svc.get_dashboard_data()
        assert data["contacts_total"] == 0
        assert len(data["companies"]) == 0
        assert "suggestions" in data

    def test_dashboard_with_data(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo, company_repo, *_ = json_repos

        contact_repo.add(sample_contact(name="Alice", id=1, status="connected"))
        contact_repo.add(sample_contact(name="Bob", id=2, status="responded"))
        company_repo.add(sample_company(name="Acme", id=1))

        data = svc.get_dashboard_data()
        assert data["contacts_total"] == 2
        assert len(data["companies"]) == 1
        assert data["status_counts"]["connected"] == 1

    def test_dashboard_with_overdue(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo = json_repos[0]

        yesterday = (datetime.now() - timedelta(days=2)).isoformat()
        contact_repo.add(sample_contact(
            name="Alice", id=1, status="connected",
            follow_up_date=yesterday,
        ))

        data = svc.get_dashboard_data()
        assert len(data["overdue"]) == 1

    def test_dashboard_with_stale(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo = json_repos[0]

        old_date = (datetime.now() - timedelta(days=15)).isoformat()
        contact_repo.add(sample_contact(
            name="Alice", id=1, status="connection_sent",
            last_contact=old_date,
        ))

        data = svc.get_dashboard_data()
        assert len(data["stale_connections"]) == 1

    def test_dashboard_suggestions(self, json_repos):
        svc = self._svc(json_repos)
        contact_repo, company_repo, *_ = json_repos

        contact_repo.add(sample_contact(name="Alice", id=1, status="not_contacted"))
        company_repo.add(sample_company(name="Acme", id=1))

        data = svc.get_dashboard_data()
        assert len(data["suggestions"]) > 0


class TestFollowUpCadence:
    """The planner must never come up empty while contacts are still in play.

    Regression cover for the five-month window where `run-daily` reported 136
    consecutive successes with zero actions: `messaged` had no rule, nothing set
    `follow_up_date`, and contacts missing timestamps were skipped forever.
    """

    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def _age(self, svc, contact_id, days):
        contact = svc.get_contact(contact_id)
        contact["last_contact"] = (datetime.now() - timedelta(days=days)).isoformat()
        contact["follow_up_date"] = None
        svc.contacts.update(contact)

    def test_add_seeds_follow_up_date(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        assert svc.get_contact(1)["follow_up_date"] is not None

    def test_status_change_seeds_follow_up_date(self, json_repos):
        from linkedin.services.contact_service import STATUS_RULES

        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="messaged")

        expected = (datetime.now() + timedelta(days=STATUS_RULES["messaged"]["cadence_days"])).strftime("%Y-%m-%d")
        assert svc.get_contact(1)["follow_up_date"] == expected

    def test_explicit_follow_up_beats_cadence(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="messaged", follow_up="2030-01-01")
        assert svc.get_contact(1)["follow_up_date"] == "2030-01-01"

    def test_terminal_status_clears_follow_up(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="hired")
        assert svc.get_contact(1)["follow_up_date"] is None

    def test_messaged_contact_produces_an_action(self, json_repos):
        """The gap that hid 4 of 11 real contacts from the planner."""
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="messaged")
        self._age(svc, 1, days=6)

        actions = svc.get_next_actions()
        assert [a["action"] for a in actions] == ["follow_up_messaged"]

    def test_recently_messaged_contact_is_left_alone(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="messaged")
        self._age(svc, 1, days=1)
        assert svc.get_next_actions() == []

    def test_not_contacted_produces_an_action(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        actions = svc.get_next_actions()
        assert any(a["action"] in ("send_connection", "follow_up_today") for a in actions)

    def test_terminal_contacts_generate_no_actions(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="rejected")
        assert svc.get_next_actions() == []

    def test_one_action_per_contact(self, json_repos):
        """An overdue follow-up is usually also a stale connection; show it once."""
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="connection_sent")
        contact = svc.get_contact(1)
        contact["last_contact"] = (datetime.now() - timedelta(days=40)).isoformat()
        contact["follow_up_date"] = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
        svc.contacts.update(contact)

        actions = svc.get_next_actions()
        assert [a["contact_id"] for a in actions] == [1]

    def test_every_pipeline_status_is_terminal_or_planned_for(self):
        """The root cause: `messaged` had a status but no rule, so those contacts
        were invisible to the planner for five months. A status declared in
        `ContactStatus` and planned for nowhere must fail loudly."""
        from linkedin.constants import ContactStatus
        from linkedin.services.contact_service import (
            STATUS_RULES,
            TERMINAL_STATUSES,
            _check_status_coverage,
        )

        assert set(STATUS_RULES) | set(TERMINAL_STATUSES) == {s.value for s in ContactStatus}
        _check_status_coverage()

    def test_a_status_missing_its_rule_raises(self, monkeypatch):
        """Adding a status to the enum and to neither table is what must fail."""
        from linkedin.services import contact_service

        class Ghosted(str, Enum):
            GHOSTED = "ghosted"
            HIRED = "hired"

        monkeypatch.setattr(contact_service, "ContactStatus", Ghosted)
        with pytest.raises(RuntimeError, match="invisible to the planner"):
            contact_service._check_status_coverage()

    def test_cadence_and_action_cannot_drift_apart(self):
        """Both live in one row, so a status can never have one without the other."""
        from linkedin.services.contact_service import STATUS_RULES

        for status, rule in STATUS_RULES.items():
            assert {"cadence_days", "after_days", "priority", "action", "reason"} <= set(rule), status

    def test_every_rule_action_is_renderable_by_the_cli(self):
        """A rule whose action has no label/command renders as a bare slug."""
        from linkedin.cli import NEXT_ACTION_COMMANDS, NEXT_ACTION_LABELS
        from linkedin.services.contact_service import STATUS_RULES

        actions = {r["action"] for r in STATUS_RULES.values()} | {
            "follow_up_overdue",
            "follow_up_today",
            "repair_contact",
        }
        assert actions <= set(NEXT_ACTION_LABELS)
        assert actions <= set(NEXT_ACTION_COMMANDS)


class TestRepairContacts:
    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def test_timestampless_contact_is_surfaced_not_skipped(self, json_repos):
        """Two of the user's real contacts had no dates and were invisible forever."""
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add(sample_contact(id=1, status="connected", created_at=None, last_contact=None, follow_up_date=None))

        actions = self._svc(json_repos).get_next_actions()
        assert [a["action"] for a in actions] == ["repair_contact"]

    def test_repair_backfills_and_makes_actionable(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add(sample_contact(id=1, status="connected", created_at=None, last_contact=None, follow_up_date=None))
        svc = self._svc(json_repos)

        result = svc.repair_contacts()
        assert result["total"] == 1
        assert "created_at" in result["repaired"][0]["fixes"]

        contact = svc.get_contact(1)
        assert contact["created_at"] and contact["last_contact"] and contact["follow_up_date"]
        assert all(a["action"] != "repair_contact" for a in svc.get_next_actions())

    def test_repair_dry_run_writes_nothing(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add(sample_contact(id=1, status="connected", created_at=None, last_contact=None, follow_up_date=None))
        svc = self._svc(json_repos)

        assert svc.repair_contacts(dry_run=True)["total"] == 1
        assert svc.get_contact(1)["created_at"] is None

    def test_repair_is_idempotent(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        assert svc.repair_contacts()["total"] == 0


class TestStalledContacts:
    """`stalled_contacts` separates a broken planner from a quiet day."""

    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def _set(self, svc, contact_id, **fields):
        contact = svc.get_contact(contact_id)
        contact.update(fields)
        svc.contacts.update(contact)

    def test_missing_follow_up_date_is_stalled(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        self._set(svc, 1, status="messaged", follow_up_date=None)
        assert [c["id"] for c in svc.stalled_contacts()] == [1]

    def test_unparseable_follow_up_date_is_stalled(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        self._set(svc, 1, status="messaged", follow_up_date="not-a-date")
        assert [c["id"] for c in svc.stalled_contacts()] == [1]

    def test_past_due_follow_up_is_stalled(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        past = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        self._set(svc, 1, status="messaged", follow_up_date=past)
        assert [c["id"] for c in svc.stalled_contacts()] == [1]

    def test_future_follow_up_is_not_stalled(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        future = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        self._set(svc, 1, status="messaged", follow_up_date=future)
        assert svc.stalled_contacts() == []

    def test_terminal_contacts_are_never_stalled(self, json_repos):
        svc = self._svc(json_repos)
        svc.add_contact(name="Alice", title="Engineer", company="Acme", linkedin="")
        svc.update_contact(1, status="rejected")
        self._set(svc, 1, follow_up_date=None)
        assert svc.stalled_contacts() == []

    def test_the_real_five_month_stall_is_detected(self, json_repos):
        """All 11 real contacts were active with follow_up_date=None."""
        contact_repo, _company_repo, *_ = json_repos
        for i in range(1, 12):
            contact_repo.add(sample_contact(id=i, status="messaged", follow_up_date=None))
        assert len(self._svc(json_repos).stalled_contacts()) == 11


class TestRepairPartialRecords:
    """Contacts written without required keys crashed the renderers.

    `contacts due` raised KeyError('company') on real data the moment follow-up
    dates started populating — the records had been invisible until then.
    """

    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def test_repair_backfills_missing_string_fields(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add({"id": 1, "status": "connected"})
        svc = self._svc(json_repos)

        result = svc.repair_contacts()
        assert result["total"] == 1
        contact = svc.get_contact(1)
        for field in ("name", "company", "title", "linkedin_url", "notes", "email"):
            assert contact[field] == ""

    def test_repair_supplies_a_missing_status(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add({"id": 1, "name": "Alice"})
        svc = self._svc(json_repos)

        svc.repair_contacts()
        assert svc.get_contact(1)["status"] == "not_contacted"

    def test_repair_does_not_blank_existing_values(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add({"id": 1, "name": "Alice", "company": "Acme", "status": "messaged"})
        svc = self._svc(json_repos)

        svc.repair_contacts()
        contact = svc.get_contact(1)
        assert contact["name"] == "Alice" and contact["company"] == "Acme"

    def test_filters_survive_partial_records(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add({"id": 1})
        contact_repo.add(sample_contact(id=2, status="messaged", company="Acme"))
        svc = self._svc(json_repos)

        assert [c["id"] for c in svc.list_contacts(status="messaged")] == [2]
        assert [c["id"] for c in svc.list_contacts(company="acme")] == [2]
        assert svc.get_stats()["total"] == 2

    def test_due_contacts_survive_partial_records(self, json_repos):
        contact_repo, _company_repo, *_ = json_repos
        contact_repo.add({"id": 1, "follow_up_date": "2020-01-01"})
        assert len(self._svc(json_repos).get_due_contacts()["overdue"]) == 1


class TestDashboardMatchesThePlanner:
    """The dashboard used to keep its own copy of "overdue" and its own `>= 14`."""

    def _svc(self, json_repos):
        from linkedin.services.dashboard_service import DashboardService

        contacts, companies, profiles, drafts = json_repos[:4]
        return DashboardService(profiles, contacts, companies, drafts)

    def test_a_contact_with_no_status_does_not_crash(self, json_repos):
        json_repos[0].add({"id": 1, "name": "Alice"})
        data = self._svc(json_repos).get_dashboard_data()
        assert data["overdue"] == []

    def test_stale_threshold_tracks_the_status_rule(self, json_repos):
        from linkedin.services.contact_service import STATUS_RULES

        stale_after = STATUS_RULES["connection_sent"]["after_days"]
        json_repos[0].add({
            "id": 1,
            "name": "Alice",
            "status": "connection_sent",
            "last_contact": (datetime.now() - timedelta(days=stale_after)).isoformat(),
        })
        data = self._svc(json_repos).get_dashboard_data()
        assert [c["id"] for c, _ in data["stale_connections"]] == [1]


class TestDraftDeletion:
    """Drafts could be created but never removed.

    A draft is a message about to go out under the user's real name; a bad one
    (an offline template passed off as a draft, say) had no way off the list.
    """

    def _svc(self, json_repos):
        from linkedin.services.draft_service import DraftService

        contact_repo, _, profile_repo, draft_repo, *_ = json_repos
        return DraftService(draft_repo, contact_repo, profile_repo)

    def test_delete_removes_the_draft(self, json_repos):
        svc = self._svc(json_repos)
        _, _, _, draft_repo, *_ = json_repos
        draft_repo.add({"id": 1, "contact_id": 1, "type": "message", "content": "hi"})

        assert svc.delete_draft(1) is True
        assert svc.drafts.get(1) is None

    def test_delete_missing_draft_reports_false(self, json_repos):
        assert self._svc(json_repos).delete_draft(999) is False

    def test_delete_leaves_other_drafts_alone(self, json_repos):
        svc = self._svc(json_repos)
        _, _, _, draft_repo, *_ = json_repos
        draft_repo.add({"id": 1, "contact_id": 1, "type": "message", "content": "one"})
        draft_repo.add({"id": 2, "contact_id": 1, "type": "message", "content": "two"})

        svc.delete_draft(1)
        assert [d["id"] for d in svc.drafts.list_all()] == [2]


class TestContactDeletion:
    """Contacts could be added and merged but never deleted.

    A junk record was the daily plan's top priority for days — it could not be
    removed, only merged into something real, which would have corrupted that
    record instead.
    """

    def _svc(self, json_repos):
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, *_ = json_repos
        return ContactService(contact_repo, company_repo)

    def test_delete_removes_the_contact(self, json_repos):
        svc = self._svc(json_repos)
        contact = svc.add_contact("Junk", "", "", "")

        assert svc.delete_contact(contact["id"]) is True
        assert svc.contacts.get(contact["id"]) is None

    def test_delete_missing_contact_reports_false(self, json_repos):
        assert self._svc(json_repos).delete_contact(999) is False

    def test_deleted_contact_leaves_the_planner(self, json_repos):
        """The point of deleting: it stops generating actions."""
        svc = self._svc(json_repos)
        junk = svc.add_contact("Junk", "", "", "")
        svc.add_contact("Real Person", "", "", "")

        svc.delete_contact(junk["id"])
        assert all(a["contact_id"] != junk["id"] for a in svc.get_next_actions())
