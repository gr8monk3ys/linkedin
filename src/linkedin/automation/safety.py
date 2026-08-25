"""Safety limits for LinkedIn automation.

`SafetyLimits` tracks in-memory counters for one session. `PersistentSafetyLimits`
additionally loads/saves counters per calendar day, so daily caps hold across
separate CLI invocations rather than resetting with each new process.
"""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Conservative daily limits to avoid account restrictions
MAX_CONNECTIONS_PER_DAY = 20
MAX_MESSAGES_PER_DAY = 25
MAX_PROFILE_VIEWS_PER_DAY = 50
MAX_SEARCHES_PER_DAY = 30
MAX_POSTS_PER_DAY = 3
MAX_REACTIONS_PER_DAY = 30
MAX_EASY_APPLIES_PER_DAY = 15
MAX_SESSION_MINUTES = 30
MIN_DELAY_SECONDS = 3.0
MAX_DELAY_SECONDS = 8.0

# Persisted usage counters, keyed by ISO date (monkeypatched in tests)
USAGE_FILE = Path.home() / ".linkedin-cli" / "automation_usage.json"


@dataclass
class SafetyLimits:
    """Track and enforce safety limits."""

    connections_sent: int = 0
    messages_sent: int = 0
    profile_views: int = 0
    searches: int = 0
    posts_created: int = 0
    reactions: int = 0
    easy_applies: int = 0

    def can_send_connection(self) -> bool:
        return self.connections_sent < MAX_CONNECTIONS_PER_DAY

    def can_send_message(self) -> bool:
        return self.messages_sent < MAX_MESSAGES_PER_DAY

    def can_view_profile(self) -> bool:
        return self.profile_views < MAX_PROFILE_VIEWS_PER_DAY

    def can_search(self) -> bool:
        return self.searches < MAX_SEARCHES_PER_DAY

    def can_post(self) -> bool:
        return self.posts_created < MAX_POSTS_PER_DAY

    def can_react(self) -> bool:
        return self.reactions < MAX_REACTIONS_PER_DAY

    def can_easy_apply(self) -> bool:
        return self.easy_applies < MAX_EASY_APPLIES_PER_DAY

    def record_connection(self) -> None:
        self.connections_sent += 1
        self._persist()

    def record_message(self) -> None:
        self.messages_sent += 1
        self._persist()

    def record_profile_view(self) -> None:
        self.profile_views += 1
        self._persist()

    def record_search(self) -> None:
        self.searches += 1
        self._persist()

    def record_post(self) -> None:
        self.posts_created += 1
        self._persist()

    def record_reaction(self) -> None:
        self.reactions += 1
        self._persist()

    def record_easy_apply(self) -> None:
        self.easy_applies += 1
        self._persist()

    def _persist(self) -> None:
        """No-op for in-memory limits; PersistentSafetyLimits overrides."""

    def remaining_connections(self) -> int:
        return max(0, MAX_CONNECTIONS_PER_DAY - self.connections_sent)

    def remaining_messages(self) -> int:
        return max(0, MAX_MESSAGES_PER_DAY - self.messages_sent)

    def remaining_posts(self) -> int:
        return max(0, MAX_POSTS_PER_DAY - self.posts_created)

    def remaining_reactions(self) -> int:
        return max(0, MAX_REACTIONS_PER_DAY - self.reactions)

    def remaining_easy_applies(self) -> int:
        return max(0, MAX_EASY_APPLIES_PER_DAY - self.easy_applies)

    def summary(self) -> dict[str, int]:
        return {
            "connections_sent": self.connections_sent,
            "connections_remaining": self.remaining_connections(),
            "messages_sent": self.messages_sent,
            "messages_remaining": self.remaining_messages(),
            "profile_views": self.profile_views,
            "searches": self.searches,
            "posts_created": self.posts_created,
            "posts_remaining": self.remaining_posts(),
            "reactions": self.reactions,
            "reactions_remaining": self.remaining_reactions(),
            "easy_applies": self.easy_applies,
            "easy_applies_remaining": self.remaining_easy_applies(),
        }


_COUNTER_FIELDS = (
    "connections_sent",
    "messages_sent",
    "profile_views",
    "searches",
    "posts_created",
    "reactions",
    "easy_applies",
)


class PersistentSafetyLimits(SafetyLimits):
    """SafetyLimits backed by a per-day JSON file.

    Counters accumulate across CLI runs within the same calendar day and
    reset automatically when the date changes.
    """

    def __init__(self, usage_file: Path | None = None):
        super().__init__()
        self.usage_file = usage_file or USAGE_FILE
        self._today = date.today().isoformat()
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.usage_file.read_text())
        except (OSError, ValueError):
            return
        day_counts = data.get(self._today, {})
        for field_name in _COUNTER_FIELDS:
            value = day_counts.get(field_name, 0)
            if isinstance(value, int) and value >= 0:
                setattr(self, field_name, value)

    def _persist(self) -> None:
        counts = {name: getattr(self, name) for name in _COUNTER_FIELDS}
        # Keep only today's entry — history lives in run logs, not here.
        payload = {self._today: counts}
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file.write_text(json.dumps(payload, indent=2))
        except OSError:
            pass
