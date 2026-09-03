"""Published posts: the record and the URN that joins each to its metrics."""

from linkedin.data.json_store import JsonPostRepo
from linkedin.services.post_service import PostService


def _svc(tmp_path):
    return PostService(JsonPostRepo(tmp_path / "posts.json"))


def test_record_published_keeps_urn_and_provenance(tmp_path):
    svc = _svc(tmp_path)
    post = svc.record_published("Shipped a thing", "urn:li:activity:1", draft_id=3, calendar_id=7)
    assert post["id"] == 1 and post["urn"] == "urn:li:activity:1"
    assert post["draft_id"] == 3 and post["calendar_id"] == 7
    assert post["posted_at"]
    assert svc.list_posts() == [post]


def test_posts_without_a_urn_are_recorded_and_flagged(tmp_path):
    svc = _svc(tmp_path)
    svc.record_published("Live but unmeasurable", "")
    svc.record_published("Measured", "urn:li:activity:2")
    assert [p["text"] for p in svc.unmeasurable()] == ["Live but unmeasurable"]


def test_list_is_newest_first(tmp_path):
    svc = _svc(tmp_path)
    a = svc.record_published("a", "urn:li:activity:1")
    b = svc.record_published("b", "urn:li:activity:2")
    b["posted_at"] = "2099-01-01T00:00:00"
    svc.posts.update(b)
    assert [p["id"] for p in svc.list_posts()] == [b["id"], a["id"]]
