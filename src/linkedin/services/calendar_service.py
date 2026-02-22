"""Content calendar service -- schedule and track LinkedIn posts."""

from datetime import datetime, timedelta

from linkedin.data.repository import CalendarRepo
from linkedin.types import ContentPostDict


class ContentCalendarService:
    def __init__(self, calendar_repo: CalendarRepo):
        self.calendar = calendar_repo

    def add(
        self,
        title: str,
        scheduled_date: str,
        draft_id: int | None = None,
        platform: str = "linkedin",
    ) -> ContentPostDict:
        post: ContentPostDict = {
            "id": self.calendar.next_id(),
            "title": title,
            "scheduled_date": scheduled_date,
            "status": "scheduled",
            "platform": platform,
            "draft_id": draft_id,
            "actual_posted_date": None,
            "created_at": datetime.now().isoformat(),
        }
        return self.calendar.add(post)

    def get(self, post_id: int) -> ContentPostDict | None:
        return self.calendar.get(post_id)

    def list_all(self) -> list[ContentPostDict]:
        return sorted(self.calendar.list_all(), key=lambda p: p.get("scheduled_date", ""))

    def list_upcoming(self, days: int = 14) -> list[ContentPostDict]:
        cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        return [
            p for p in self.list_all()
            if p.get("status") == "scheduled"
            and today <= p.get("scheduled_date", "") <= cutoff
        ]

    def mark_posted(self, post_id: int, posted_date: str = "") -> ContentPostDict | None:
        post = self.calendar.get(post_id)
        if not post:
            return None
        post["status"] = "posted"
        post["actual_posted_date"] = posted_date or datetime.now().strftime("%Y-%m-%d")
        self.calendar.update(post)
        return post

    def delete(self, post_id: int) -> bool:
        return self.calendar.delete(post_id)

    def get_stats(self) -> dict:
        posts = self.calendar.list_all()
        by_status: dict[str, int] = {}
        for p in posts:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(posts),
            "scheduled": by_status.get("scheduled", 0),
            "posted": by_status.get("posted", 0),
            "skipped": by_status.get("skipped", 0),
        }
