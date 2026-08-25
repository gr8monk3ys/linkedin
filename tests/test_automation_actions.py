"""Tests for post/engage/profile-sync/easy-apply actions and persistent safety limits."""

import json
from unittest.mock import MagicMock

from linkedin.automation.actions.easy_apply import apply_to_job
from linkedin.automation.actions.engage import like_contact_posts, like_feed_posts
from linkedin.automation.actions.post import publish_post
from linkedin.automation.actions.profile_sync import sync_profile
from linkedin.automation.safety import (
    MAX_EASY_APPLIES_PER_DAY,
    MAX_POSTS_PER_DAY,
    MAX_REACTIONS_PER_DAY,
    PersistentSafetyLimits,
    SafetyLimits,
)


class TestPublishPost:
    def test_publishes_and_records(self):
        page = MagicMock()
        page.create_post.return_value = True
        safety = SafetyLimits()
        success, reason = publish_post(page, "Hello LinkedIn", safety=safety)
        assert success and reason == "posted"
        assert safety.posts_created == 1

    def test_empty_post_rejected(self):
        page = MagicMock()
        success, reason = publish_post(page, "   ")
        assert not success and reason == "empty_post"
        page.create_post.assert_not_called()

    def test_daily_limit_blocks(self):
        page = MagicMock()
        safety = SafetyLimits(posts_created=MAX_POSTS_PER_DAY)
        success, reason = publish_post(page, "text", safety=safety)
        assert not success and reason == "daily_post_limit_reached"
        page.create_post.assert_not_called()

    def test_dry_run_skips_browser(self):
        page = MagicMock()
        success, reason = publish_post(page, "text", dry_run=True)
        assert success and reason == "dry_run"
        page.create_post.assert_not_called()


class TestEngage:
    def test_like_contact_posts(self):
        page = MagicMock()
        page.like_visible_posts.return_value = 2
        safety = SafetyLimits()
        liked = like_contact_posts(page, "https://linkedin.com/in/x", count=2, safety=safety)
        assert liked == 2
        assert safety.reactions == 2
        page.goto_recent_activity.assert_called_once()

    def test_no_url_returns_zero(self):
        page = MagicMock()
        assert like_contact_posts(page, "", count=2) == 0

    def test_clamps_to_remaining_budget(self):
        page = MagicMock()
        page.like_visible_posts.return_value = 1
        safety = SafetyLimits(reactions=MAX_REACTIONS_PER_DAY - 1)
        like_contact_posts(page, "https://linkedin.com/in/x", count=5, safety=safety)
        page.like_visible_posts.assert_called_once_with(1)

    def test_limit_reached_blocks(self):
        page = MagicMock()
        safety = SafetyLimits(reactions=MAX_REACTIONS_PER_DAY)
        assert like_feed_posts(page, count=3, safety=safety) == 0
        page.goto_feed.assert_not_called()

    def test_feed_likes(self):
        page = MagicMock()
        page.like_visible_posts.return_value = 3
        assert like_feed_posts(page, count=3) == 3
        page.goto_feed.assert_called_once()


class TestSyncProfile:
    def test_updates_both_fields(self):
        page = MagicMock()
        page.update_headline.return_value = True
        page.update_about.return_value = False
        results = sync_profile(page, headline="New headline", about="New about")
        assert results == {"headline": "updated", "about": "failed"}

    def test_nothing_requested(self):
        page = MagicMock()
        assert sync_profile(page) == {}
        page.update_headline.assert_not_called()

    def test_dry_run(self):
        page = MagicMock()
        results = sync_profile(page, headline="X", dry_run=True)
        assert results["headline"] == "dry_run"
        page.update_headline.assert_not_called()


class TestEasyApply:
    def test_submitted_records_usage(self):
        page = MagicMock()
        page.easy_apply.return_value = {"status": "submitted", "detail": "ok"}
        safety = SafetyLimits()
        result = apply_to_job(
            page, "https://linkedin.com/jobs/view/1", resume_path="/r.pdf", submit=True, safety=safety
        )
        assert result["status"] == "submitted"
        assert safety.easy_applies == 1

    def test_ready_to_submit_does_not_record(self):
        page = MagicMock()
        page.easy_apply.return_value = {"status": "ready_to_submit", "detail": ""}
        safety = SafetyLimits()
        apply_to_job(page, "https://linkedin.com/jobs/view/1", safety=safety)
        assert safety.easy_applies == 0

    def test_no_url(self):
        assert apply_to_job(MagicMock(), "")["status"] == "error"

    def test_daily_limit_blocks_submit(self):
        page = MagicMock()
        safety = SafetyLimits(easy_applies=MAX_EASY_APPLIES_PER_DAY)
        result = apply_to_job(page, "https://x", submit=True, safety=safety)
        assert result["status"] == "error"
        page.easy_apply.assert_not_called()

    def test_dry_run(self):
        page = MagicMock()
        result = apply_to_job(page, "https://x", dry_run=True)
        assert result["status"] == "dry_run"
        page.easy_apply.assert_not_called()


class TestPersistentSafetyLimits:
    def test_counters_survive_reload(self, tmp_path):
        usage_file = tmp_path / "usage.json"
        limits = PersistentSafetyLimits(usage_file=usage_file)
        limits.record_connection()
        limits.record_post()
        limits.record_post()

        reloaded = PersistentSafetyLimits(usage_file=usage_file)
        assert reloaded.connections_sent == 1
        assert reloaded.posts_created == 2

    def test_other_days_ignored(self, tmp_path):
        usage_file = tmp_path / "usage.json"
        usage_file.write_text(json.dumps({"2000-01-01": {"connections_sent": 19}}))
        limits = PersistentSafetyLimits(usage_file=usage_file)
        assert limits.connections_sent == 0

    def test_corrupt_file_ignored(self, tmp_path):
        usage_file = tmp_path / "usage.json"
        usage_file.write_text("{not json")
        limits = PersistentSafetyLimits(usage_file=usage_file)
        assert limits.connections_sent == 0
        limits.record_connection()  # must not raise
        assert PersistentSafetyLimits(usage_file=usage_file).connections_sent == 1

    def test_in_memory_limits_do_not_write(self, tmp_path, monkeypatch):
        import linkedin.automation.safety as safety_mod

        usage_file = tmp_path / "usage.json"
        monkeypatch.setattr(safety_mod, "USAGE_FILE", usage_file)
        SafetyLimits().record_connection()
        assert not usage_file.exists()

    def test_summary_includes_new_actions(self):
        summary = SafetyLimits().summary()
        for key in ("posts_remaining", "reactions_remaining", "easy_applies_remaining"):
            assert key in summary
