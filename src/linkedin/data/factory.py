"""Factory for constructing the repository set.

Storage is JSON files under ~/.linkedin-cli. A SQLModel/Postgres backend existed
behind LINKEDIN_BACKEND=db until 2026-08-29 and was removed: it was last used in
February, and four of its nine repositories silently fell back to JSON, so
enabling it split the dataset across two stores.
"""

from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonCalendarRepo,
    JsonCompanyRepo,
    JsonContactRepo,
    JsonConversationRepo,
    JsonDraftRepo,
    JsonInterviewPrepRepo,
    JsonProfileRepo,
    JsonResearchRepo,
)
from linkedin.data.repository import (
    ApplicationRepo,
    CalendarRepo,
    CompanyRepo,
    ContactRepo,
    ConversationRepo,
    DraftRepo,
    InterviewPrepRepo,
    ProfileRepo,
    ResearchRepo,
)


def create_repos() -> tuple[
    ContactRepo,
    CompanyRepo,
    ProfileRepo,
    DraftRepo,
    ResearchRepo,
    ApplicationRepo,
    ConversationRepo,
    CalendarRepo,
    InterviewPrepRepo,
]:
    return (
        JsonContactRepo(),
        JsonCompanyRepo(),
        JsonProfileRepo(),
        JsonDraftRepo(),
        JsonResearchRepo(),
        JsonApplicationRepo(),
        JsonConversationRepo(),
        JsonCalendarRepo(),
        JsonInterviewPrepRepo(),
    )
