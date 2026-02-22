"""Factory for selecting data backend (JSON or Database)."""

import os

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


def get_backend() -> str:
    return os.environ.get("LINKEDIN_BACKEND", "json").lower()


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
    backend = get_backend()

    if backend == "db":
        from linkedin.data.db_store import (
            DbCompanyRepo,
            DbContactRepo,
            DbDraftRepo,
            DbProfileRepo,
            DbResearchRepo,
        )
        from linkedin.models.base import create_tables

        create_tables()
        # DB store stubs for new repos — fall back to JSON for now
        from linkedin.data.json_store import (
            JsonApplicationRepo,
            JsonCalendarRepo,
            JsonConversationRepo,
            JsonInterviewPrepRepo,
        )
        return (
            DbContactRepo(),
            DbCompanyRepo(),
            DbProfileRepo(),
            DbDraftRepo(),
            DbResearchRepo(),
            JsonApplicationRepo(),
            JsonConversationRepo(),
            JsonCalendarRepo(),
            JsonInterviewPrepRepo(),
        )

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
