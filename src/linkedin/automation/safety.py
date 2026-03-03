"""Safety limits for LinkedIn automation."""

from dataclasses import dataclass

# Conservative daily limits to avoid account restrictions
MAX_CONNECTIONS_PER_DAY = 20
MAX_MESSAGES_PER_DAY = 25
MAX_PROFILE_VIEWS_PER_DAY = 50
MAX_SEARCHES_PER_DAY = 30
MAX_LIKES_PER_DAY = 50
MAX_COMMENTS_PER_DAY = 15
MAX_SESSION_MINUTES = 30
MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 8.0


@dataclass
class SafetyLimits:
    """Track and enforce safety limits."""

    connections_sent: int = 0
    messages_sent: int = 0
    profile_views: int = 0
    searches: int = 0
    likes_given: int = 0
    comments_posted: int = 0

    def can_send_connection(self) -> bool:
        return self.connections_sent < MAX_CONNECTIONS_PER_DAY

    def can_send_message(self) -> bool:
        return self.messages_sent < MAX_MESSAGES_PER_DAY

    def can_view_profile(self) -> bool:
        return self.profile_views < MAX_PROFILE_VIEWS_PER_DAY

    def can_search(self) -> bool:
        return self.searches < MAX_SEARCHES_PER_DAY

    def can_like(self) -> bool:
        return self.likes_given < MAX_LIKES_PER_DAY

    def can_comment(self) -> bool:
        return self.comments_posted < MAX_COMMENTS_PER_DAY

    def record_connection(self) -> None:
        self.connections_sent += 1

    def record_message(self) -> None:
        self.messages_sent += 1

    def record_profile_view(self) -> None:
        self.profile_views += 1

    def record_search(self) -> None:
        self.searches += 1

    def record_like(self) -> None:
        self.likes_given += 1

    def record_comment(self) -> None:
        self.comments_posted += 1

    def remaining_connections(self) -> int:
        return max(0, MAX_CONNECTIONS_PER_DAY - self.connections_sent)

    def remaining_messages(self) -> int:
        return max(0, MAX_MESSAGES_PER_DAY - self.messages_sent)

    def remaining_likes(self) -> int:
        return max(0, MAX_LIKES_PER_DAY - self.likes_given)

    def remaining_comments(self) -> int:
        return max(0, MAX_COMMENTS_PER_DAY - self.comments_posted)

    def summary(self) -> dict[str, int]:
        return {
            "connections_sent": self.connections_sent,
            "connections_remaining": self.remaining_connections(),
            "messages_sent": self.messages_sent,
            "messages_remaining": self.remaining_messages(),
            "profile_views": self.profile_views,
            "searches": self.searches,
            "likes_given": self.likes_given,
            "likes_remaining": self.remaining_likes(),
            "comments_posted": self.comments_posted,
            "comments_remaining": self.remaining_comments(),
        }
