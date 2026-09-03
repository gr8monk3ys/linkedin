"""Analytics service — pipeline conversion, response rates, outreach velocity."""

from collections import Counter
from datetime import datetime, timedelta

from linkedin.data.json_store import JsonContactRepo, JsonDraftRepo


def _parse_created_at(value: str) -> datetime | None:
    """Parse a created_at timestamp defensively (imported data may carry 'Z' or offsets)."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    # Normalize to naive local-style timestamps so comparisons with now() work
    return parsed.replace(tzinfo=None)


class AnalyticsService:
    def __init__(self, contact_repo: JsonContactRepo, draft_repo: JsonDraftRepo):
        self.contacts = contact_repo
        self.drafts = draft_repo

    def get_summary(self) -> dict:
        """Get analytics summary with key metrics."""
        contacts = self.contacts.list_all()
        drafts = self.drafts.list_all()

        total = len(contacts)
        if total == 0:
            return {
                "total_contacts": 0,
                "response_rate": "0%",
                "conversion_rate": "0%",
                "outreach_velocity": "0/week",
                "avg_time_per_stage": "N/A",
                "pipeline": {},
                "source_effectiveness": {},
                "draft_type_counts": {},
            }

        pipeline = Counter(c.get("status", "not_contacted") for c in contacts)
        responded = sum(pipeline.get(s, 0) for s in ["responded", "call_scheduled", "hired"])
        contacted = total - pipeline.get("not_contacted", 0)
        response_rate = f"{(responded / contacted * 100):.0f}%" if contacted > 0 else "0%"

        hired = pipeline.get("hired", 0)
        conversion_rate = f"{(hired / total * 100):.1f}%" if total > 0 else "0%"

        # Outreach velocity — contacts added per week
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        recent = 0
        for c in contacts:
            created = _parse_created_at(c.get("created_at") or "")
            if created and created > week_ago:
                recent += 1
        velocity = f"{recent}/week"

        # Source effectiveness
        source_counts = Counter(c.get("source", "unknown") for c in contacts)
        source_responses = Counter()
        for c in contacts:
            if c.get("status") in ("responded", "call_scheduled", "hired"):
                source_responses[c.get("source", "unknown")] += 1

        source_effectiveness = {}
        for source, count in source_counts.items():
            resp = source_responses.get(source, 0)
            rate = f"{(resp / count * 100):.0f}%" if count > 0 else "0%"
            source_effectiveness[source] = {"total": count, "responded": resp, "rate": rate}

        # Draft type counts
        draft_type_counts = Counter(d.get("type", "unknown") for d in drafts)

        return {
            "total_contacts": total,
            "response_rate": response_rate,
            "conversion_rate": conversion_rate,
            "outreach_velocity": velocity,
            "avg_time_per_stage": "N/A",
            "pipeline": dict(pipeline),
            "source_effectiveness": source_effectiveness,
            "draft_type_counts": dict(draft_type_counts),
        }

    def get_conversion_funnel(self) -> list[dict]:
        """Get pipeline as a conversion funnel."""
        contacts = self.contacts.list_all()
        total = len(contacts)
        if total == 0:
            return []

        stages = [
            "not_contacted",
            "connection_sent",
            "connected",
            "messaged",
            "responded",
            "call_scheduled",
            "hired",
        ]
        pipeline = Counter(c.get("status", "not_contacted") for c in contacts)

        funnel = []
        cumulative = total
        for stage in stages:
            count = pipeline.get(stage, 0)
            pct = f"{(cumulative / total * 100):.0f}%"
            funnel.append({"stage": stage.replace("_", " ").title(), "count": count, "remaining": cumulative, "pct": pct})
            cumulative -= count

        return funnel

    def get_velocity(self, weeks: int = 8) -> list[dict]:
        """Get weekly outreach velocity for the last N weeks."""
        contacts = self.contacts.list_all()
        now = datetime.now()
        velocity = []

        for i in range(weeks - 1, -1, -1):
            week_start = now - timedelta(weeks=i + 1)
            week_end = now - timedelta(weeks=i)
            count = 0
            for c in contacts:
                created = _parse_created_at(c.get("created_at") or "")
                if created and week_start < created <= week_end:
                    count += 1
            label = week_end.strftime("%b %d")
            velocity.append({"week": label, "contacts": count})

        return velocity
