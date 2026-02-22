"""Tests for ContentCalendarService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import JsonCalendarRepo
from linkedin.services.calendar_service import ContentCalendarService


@pytest.fixture
def cal_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")
    return JsonCalendarRepo()


@pytest.fixture
def svc(cal_repo):
    return ContentCalendarService(cal_repo)


def test_add_and_list(svc):
    svc.add(title="Why Python rocks", scheduled_date="2026-03-01")
    posts = svc.list_all()
    assert len(posts) == 1
    assert posts[0]["title"] == "Why Python rocks"
    assert posts[0]["status"] == "scheduled"


def test_mark_posted(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id)
    post = svc.get(post_id)
    assert post["status"] == "posted"
    assert post["actual_posted_date"] is not None


def test_mark_posted_with_date(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id, posted_date="2026-03-02")
    assert svc.get(post_id)["actual_posted_date"] == "2026-03-02"


def test_delete(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.delete(post_id)
    assert svc.get(post_id) is None


def test_list_upcoming(svc):
    svc.add(title="Future", scheduled_date="2030-01-01")
    svc.add(title="Past", scheduled_date="2020-01-01")
    upcoming = svc.list_upcoming(days=3650)
    assert any(p["title"] == "Future" for p in upcoming)


def test_stats_empty(svc):
    stats = svc.get_stats()
    assert stats["total"] == 0
    assert stats["scheduled"] == 0
    assert stats["posted"] == 0


def test_stats_counts(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    svc.add(title="Post 2", scheduled_date="2026-03-08")
    svc.mark_posted(svc.list_all()[0]["id"])
    stats = svc.get_stats()
    assert stats["total"] == 2
    assert stats["posted"] == 1
    assert stats["scheduled"] == 1


def test_list_upcoming_excludes_posted(svc):
    """Posted posts should not appear in list_upcoming."""
    svc.add(title="Post", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id)
    upcoming = svc.list_upcoming(days=3650)
    assert len(upcoming) == 0


def test_delete_nonexistent(svc):
    """Deleting a post that doesn't exist should return False."""
    assert svc.delete(999) is False


def test_stats_all_states(svc):
    """Stats should correctly count both scheduled and posted states."""
    svc.add(title="Scheduled post", scheduled_date="2026-03-01")
    svc.add(title="Also scheduled", scheduled_date="2026-03-02")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id)
    stats = svc.get_stats()
    assert stats["scheduled"] == 1
    assert stats["posted"] == 1
    assert stats["total"] == 2
