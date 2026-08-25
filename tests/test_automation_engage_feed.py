"""Tests for feed engagement: index-based actions and the AutomationService."""

from unittest.mock import MagicMock, patch

import pytest

from linkedin.ai.client import AIClientError
from linkedin.automation.actions.engage import comment_on_post, like_post_by_index
from linkedin.automation.safety import (
    MAX_COMMENTS_PER_DAY,
    MAX_REACTIONS_PER_DAY,
    SafetyLimits,
)
from linkedin.services.automation_service import AutomationService


class TestLikePostByIndex:
    def test_likes_and_records(self):
        page = MagicMock()
        page.like_post.return_value = True
        safety = SafetyLimits()
        assert like_post_by_index(page, 0, safety=safety)
        assert safety.reactions == 1
        page.like_post.assert_called_once_with(0)

    def test_reaction_budget_blocks(self):
        page = MagicMock()
        safety = SafetyLimits(reactions=MAX_REACTIONS_PER_DAY)
        assert not like_post_by_index(page, 0, safety=safety)
        page.like_post.assert_not_called()

    def test_dry_run(self):
        page = MagicMock()
        safety = SafetyLimits()
        assert like_post_by_index(page, 0, safety=safety, dry_run=True)
        assert safety.reactions == 1
        page.like_post.assert_not_called()


class TestCommentOnPost:
    def test_comments_and_records(self):
        page = MagicMock()
        page.comment_on_post.return_value = True
        safety = SafetyLimits()
        assert comment_on_post(page, 1, "Great insight!", safety=safety)
        assert safety.comments_posted == 1
        page.comment_on_post.assert_called_once_with(1, "Great insight!")

    def test_empty_comment_rejected(self):
        page = MagicMock()
        assert not comment_on_post(page, 1, "   ")
        page.comment_on_post.assert_not_called()

    def test_comment_budget_blocks(self):
        page = MagicMock()
        safety = SafetyLimits(comments_posted=MAX_COMMENTS_PER_DAY)
        assert not comment_on_post(page, 1, "text", safety=safety)
        page.comment_on_post.assert_not_called()

    def test_dry_run(self):
        page = MagicMock()
        safety = SafetyLimits()
        assert comment_on_post(page, 1, "text", safety=safety, dry_run=True)
        assert safety.comments_posted == 1
        page.comment_on_post.assert_not_called()


@pytest.fixture
def profile_repo():
    repo = MagicMock()
    repo.get.return_value = {
        "name": "Test User",
        "headline": "ML Engineer",
        "target_role": "ML Engineer",
        "skills": "Python, ML",
    }
    return repo


def _post(i, author="Alice", content="A long post about machine learning and its many applications."):
    return {"element_index": i, "author": author, "headline": "Engineer", "content": content}


class TestEngageFeed:
    def test_likes_and_comments_with_budgets(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        page.get_feed_posts.return_value = [_post(0), _post(1, author="Bob"), _post(2, author="Cara")]
        page.like_post.return_value = True
        page.comment_on_post.return_value = True
        safety = SafetyLimits()

        with patch("linkedin.services.automation_service.generate_with_ai", return_value="Nice point!") as gen:
            results = svc.engage_feed(page, limit=3, comment_count=2, safety=safety)

        assert len(results) == 3
        assert all(r["liked"] for r in results)
        assert sum(1 for r in results if r["commented"]) == 2
        assert safety.reactions == 3
        assert safety.comments_posted == 2
        assert gen.call_count == 2  # stops generating once comment budget for the run is spent

    def test_empty_feed(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        page.get_feed_posts.return_value = []
        assert svc.engage_feed(page, limit=5) == []

    def test_no_comment_on_contentless_post(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        page.get_feed_posts.return_value = [_post(0, content="")]
        page.like_post.return_value = True
        with patch("linkedin.services.automation_service.generate_with_ai") as gen:
            results = svc.engage_feed(page, limit=1, comment_count=1)
        gen.assert_not_called()
        assert not results[0]["commented"]

    def test_ai_failure_skips_comment_but_still_likes(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        page.get_feed_posts.return_value = [_post(0)]
        page.like_post.return_value = True
        with patch("linkedin.services.automation_service.generate_with_ai", side_effect=AIClientError("down")):
            results = svc.engage_feed(page, limit=1, comment_count=1)
        assert results[0]["liked"]
        assert not results[0]["commented"]
        assert results[0]["comment_text"] == ""
        page.comment_on_post.assert_not_called()

    def test_reaction_budget_stops_run(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        page.get_feed_posts.return_value = [_post(0), _post(1)]
        safety = SafetyLimits(reactions=MAX_REACTIONS_PER_DAY)
        results = svc.engage_feed(page, limit=2, comment_count=0, safety=safety)
        assert results == []
        page.like_post.assert_not_called()

    def test_content_preview_truncated(self, profile_repo):
        svc = AutomationService(profile_repo)
        page = MagicMock()
        long_content = "x" * 120
        page.get_feed_posts.return_value = [_post(0, content=long_content)]
        page.like_post.return_value = True
        results = svc.engage_feed(page, limit=1)
        assert results[0]["content_preview"] == "x" * 47 + "..."

    def test_generate_feed_comment_without_profile(self):
        svc = AutomationService(MagicMock())
        with patch("linkedin.services.automation_service.generate_with_ai", return_value="  Thoughtful!  "):
            comment = svc.generate_feed_comment(None, _post(0))
        assert comment == "Thoughtful!"


class TestEngageCliCommentsFlag:
    @pytest.fixture(autouse=True)
    def patch_paths(self, tmp_path, monkeypatch):
        import linkedin.data.json_store as js

        monkeypatch.setattr(js, "DATA_DIR", tmp_path)
        monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
        monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")

    def test_comments_requires_feed(self):
        from click.testing import CliRunner

        from linkedin.cli import cli

        result = CliRunner().invoke(cli, ["automate", "engage", "--contact-id", "1", "--comments", "2"])
        assert result.exit_code == 1
        assert "--comments requires --feed" in result.output

    def test_feed_comments_pipeline(self, monkeypatch):
        from click.testing import CliRunner

        import linkedin.cli as cli_mod
        from linkedin.automation.rate_limiter import RateLimiter
        from linkedin.cli import cli

        fake_browser, fake_page = MagicMock(), MagicMock()
        namespace = {
            "RateLimiter": RateLimiter,
            "SafetyLimits": SafetyLimits,
            "PersistentSafetyLimits": SafetyLimits,
            "engage": MagicMock(),
        }
        monkeypatch.setattr(cli_mod, "_require_automation", lambda: namespace)
        monkeypatch.setattr(cli_mod, "_open_linkedin_session", lambda auto, headless: (fake_browser, fake_page))
        monkeypatch.setattr(
            cli_mod._automation_svc,
            "engage_feed",
            MagicMock(
                return_value=[
                    {
                        "author": "Alice",
                        "content_preview": "post",
                        "liked": True,
                        "commented": True,
                        "comment_text": "Nice!",
                    }
                ]
            ),
        )

        result = CliRunner().invoke(cli, ["automate", "engage", "--feed", "--likes", "1", "--comments", "1"])
        assert result.exit_code == 0, result.output
        assert "commented 1" in result.output
        fake_browser.close.assert_called_once()
