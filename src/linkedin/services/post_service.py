"""Published posts: the record that a post went out, and the URN that joins it to its metrics."""

from datetime import datetime

from linkedin.data.json_store import JsonPostRepo
from linkedin.types import PostDict


class PostService:
    def __init__(self, post_repo: JsonPostRepo):
        self.posts = post_repo

    def record_published(
        self, text: str, urn: str = "", *, draft_id: int | None = None, calendar_id: int | None = None
    ) -> PostDict:
        """Record a post that LinkedIn accepted. An empty `urn` is a post whose
        success link could not be read; it exists but cannot be measured."""
        post: PostDict = {
            "id": self.posts.next_id(),
            "urn": urn,
            "text": text,
            "posted_at": datetime.now().isoformat(timespec="seconds"),
            "draft_id": draft_id,
            "calendar_id": calendar_id,
        }
        return self.posts.add(post)

    def list_posts(self) -> list[PostDict]:
        return sorted(self.posts.list_all(), key=lambda p: p.get("posted_at", ""), reverse=True)

    def unmeasurable(self) -> list[PostDict]:
        """Posts with no URN: published, but nothing can ever be joined to them."""
        return [p for p in self.posts.list_all() if not p.get("urn")]
