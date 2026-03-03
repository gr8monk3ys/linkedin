"""Tests for feed engagement automation."""

import sys
from unittest.mock import MagicMock, patch

# Mock optional dependencies before importing automation modules
_pw_mock = MagicMock()
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", _pw_mock)
sys.modules.setdefault("keyring", MagicMock())

from linkedin.automation.safety import (  # noqa: E402
    MAX_COMMENTS_PER_DAY,
    MAX_LIKES_PER_DAY,
    SafetyLimits,
)
from tests.conftest import sample_profile  # noqa: E402


class TestSafetyLimitsEngage:
    """Tests for like/comment safety limits."""

    def test_can_like_initially(self):
        safety = SafetyLimits()
        assert safety.can_like() is True

    def test_can_comment_initially(self):
        safety = SafetyLimits()
        assert safety.can_comment() is True

    def test_like_limit_enforced(self):
        safety = SafetyLimits(likes_given=MAX_LIKES_PER_DAY)
        assert safety.can_like() is False

    def test_comment_limit_enforced(self):
        safety = SafetyLimits(comments_posted=MAX_COMMENTS_PER_DAY)
        assert safety.can_comment() is False

    def test_record_like_increments(self):
        safety = SafetyLimits()
        safety.record_like()
        assert safety.likes_given == 1

    def test_record_comment_increments(self):
        safety = SafetyLimits()
        safety.record_comment()
        assert safety.comments_posted == 1

    def test_remaining_likes(self):
        safety = SafetyLimits(likes_given=10)
        assert safety.remaining_likes() == MAX_LIKES_PER_DAY - 10

    def test_remaining_comments(self):
        safety = SafetyLimits(comments_posted=5)
        assert safety.remaining_comments() == MAX_COMMENTS_PER_DAY - 5

    def test_remaining_never_negative(self):
        safety = SafetyLimits(likes_given=999, comments_posted=999)
        assert safety.remaining_likes() == 0
        assert safety.remaining_comments() == 0

    def test_summary_includes_engagement_fields(self):
        safety = SafetyLimits(likes_given=3, comments_posted=2)
        summary = safety.summary()
        assert summary["likes_given"] == 3
        assert summary["likes_remaining"] == MAX_LIKES_PER_DAY - 3
        assert summary["comments_posted"] == 2
        assert summary["comments_remaining"] == MAX_COMMENTS_PER_DAY - 2


class TestFeedCommentGeneration:
    """Tests for _generate_feed_comment()."""

    def _svc(self, json_repos):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo)

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Great insight on AI trends!")
    def test_generates_comment_with_profile_and_post(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        profile = sample_profile()
        post = {
            "author": "Jane Smith",
            "headline": "VP of Engineering at Google",
            "content": "AI is transforming how we build software...",
        }

        comment = svc._generate_feed_comment(profile, post)

        assert comment == "Great insight on AI trends!"
        mock_ai.assert_called_once()

        # Verify prompt includes profile and post data
        prompt = mock_ai.call_args[0][0]
        assert "Senior Software Engineer" in prompt  # target_role
        assert "Jane Smith" in prompt
        assert "VP of Engineering at Google" in prompt
        assert "AI is transforming" in prompt

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Interesting take!")
    def test_works_without_profile(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        post = {
            "author": "Bob",
            "headline": "Engineer",
            "content": "Some post content",
        }

        comment = svc._generate_feed_comment(None, post)

        assert comment == "Interesting take!"
        mock_ai.assert_called_once()
        # Prompt should not contain MY PROFILE section
        prompt = mock_ai.call_args[0][0]
        assert "MY PROFILE" not in prompt

    @patch("linkedin.services.automation_service.generate_with_ai", side_effect=Exception("API error"))
    def test_returns_empty_on_ai_failure(self, mock_ai, json_repos):
        svc = self._svc(json_repos)
        comment = svc._generate_feed_comment(sample_profile(), {"author": "X", "content": "Y"})
        assert comment == ""


class TestRunEngage:
    """Tests for the full run_engage() pipeline."""

    def _svc(self, json_repos, config=None):
        from linkedin.services.automation_service import AutomationService
        from linkedin.services.contact_service import ContactService

        contact_repo, company_repo, profile_repo, *_ = json_repos
        contact_svc = ContactService(contact_repo, company_repo)
        return AutomationService(contact_svc, company_repo, profile_repo, config)

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Nice post!")
    @patch("linkedin.automation.actions.engage.comment_on_post")
    @patch("linkedin.automation.actions.engage.like_post")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_full_pipeline(self, mock_bm, mock_login, mock_like, mock_comment, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        mock_like.return_value = True
        mock_comment.return_value = True

        feed_posts = [
            {"author": "Alice", "headline": "Engineer", "content": "Great article on Python", "element_index": 0},
            {"author": "Bob", "headline": "Designer", "content": "UI trends for 2026", "element_index": 1},
        ]

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_feed_posts.return_value = feed_posts

            svc = self._svc(json_repos)
            results = svc.run_engage(limit=10, comment_count=5)

        assert len(results) == 2
        assert results[0]["author"] == "Alice"
        assert results[0]["liked"] is True
        assert results[0]["commented"] is True
        assert results[0]["comment_text"] == "Nice post!"
        assert results[1]["liked"] is True
        assert mock_like.call_count == 2
        assert mock_comment.call_count == 2

    @patch("linkedin.automation.actions.login.login_action", return_value=False)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_login_failure(self, mock_bm, mock_login, json_repos):
        mock_browser = MagicMock()
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        svc = self._svc(json_repos)
        results = svc.run_engage()

        assert len(results) == 1
        assert results[0]["liked"] is False
        assert results[0]["reason"] == "Login failed"

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Comment!")
    @patch("linkedin.automation.actions.engage.comment_on_post")
    @patch("linkedin.automation.actions.engage.like_post")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_respects_comment_count(self, mock_bm, mock_login, mock_like, mock_comment, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        mock_like.return_value = True
        mock_comment.return_value = True

        feed_posts = [
            {"author": f"Person{i}", "headline": "Dev", "content": f"Post content {i}", "element_index": i}
            for i in range(5)
        ]

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_feed_posts.return_value = feed_posts

            svc = self._svc(json_repos)
            results = svc.run_engage(limit=10, comment_count=2)

        # All 5 posts should be liked
        assert all(r["liked"] for r in results)
        # Only 2 should have comments
        commented = [r for r in results if r["commented"]]
        assert len(commented) == 2

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Nice!")
    @patch("linkedin.automation.actions.engage.comment_on_post")
    @patch("linkedin.automation.actions.engage.like_post")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_dry_run_passes_through(self, mock_bm, mock_login, mock_like, mock_comment, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        mock_like.return_value = True
        mock_comment.return_value = True

        feed_posts = [
            {"author": "Alice", "headline": "Dev", "content": "Test post", "element_index": 0},
        ]

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_feed_posts.return_value = feed_posts

            svc = self._svc(json_repos)
            svc.run_engage(limit=10, dry_run=True)

        # Verify dry_run was passed to action functions
        _, like_kwargs = mock_like.call_args
        assert like_kwargs["dry_run"] is True
        _, comment_kwargs = mock_comment.call_args
        assert comment_kwargs["dry_run"] is True

    @patch("linkedin.automation.actions.engage.like_post")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_empty_feed_returns_empty(self, mock_bm, mock_login, mock_like, json_repos):
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_feed_posts.return_value = []

            svc = self._svc(json_repos)
            results = svc.run_engage()

        assert results == []
        mock_like.assert_not_called()

    @patch("linkedin.services.automation_service.generate_with_ai", return_value="Comment!")
    @patch("linkedin.automation.actions.engage.comment_on_post")
    @patch("linkedin.automation.actions.engage.like_post")
    @patch("linkedin.automation.actions.login.login_action", return_value=True)
    @patch("linkedin.automation.browser.BrowserManager")
    def test_skips_comment_when_no_content(self, mock_bm, mock_login, mock_like, mock_comment, mock_ai, json_repos):
        _, _, profile_repo, *_ = json_repos
        profile_repo.save(sample_profile())

        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser.page = mock_page
        mock_bm.return_value.__enter__ = MagicMock(return_value=mock_browser)
        mock_bm.return_value.__exit__ = MagicMock(return_value=False)

        mock_like.return_value = True
        mock_comment.return_value = True

        # Post with no content — should be liked but not commented
        feed_posts = [
            {"author": "Alice", "headline": "Dev", "content": "", "element_index": 0},
        ]

        with patch("linkedin.automation.linkedin_page.LinkedInPage") as mock_lp:
            mock_linkedin = MagicMock()
            mock_lp.return_value = mock_linkedin
            mock_linkedin.get_feed_posts.return_value = feed_posts

            svc = self._svc(json_repos)
            results = svc.run_engage(limit=10, comment_count=5)

        assert len(results) == 1
        assert results[0]["liked"] is True
        assert results[0]["commented"] is False
        mock_comment.assert_not_called()
