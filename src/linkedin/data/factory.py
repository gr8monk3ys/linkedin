"""The repository set for one data directory.

Storage is JSON files under a `DataDir`. A SQLModel/Postgres backend existed
behind LINKEDIN_BACKEND=db until 2026-08-29 and was removed: it was last used
in February, and four of its nine repositories silently fell back to JSON, so
enabling it split the dataset across two stores. The abstract repository
classes went with it — a seam with one adapter is a hypothetical seam.
"""

from dataclasses import dataclass

from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonCalendarRepo,
    JsonCompanyRepo,
    JsonContactRepo,
    JsonConversationRepo,
    JsonDraftRepo,
    JsonInterviewPrepRepo,
    JsonPostRepo,
    JsonProfileRepo,
    JsonResearchRepo,
)
from linkedin.data.paths import DataDir


@dataclass(frozen=True)
class Repos:
    contacts: JsonContactRepo
    companies: JsonCompanyRepo
    profile: JsonProfileRepo
    drafts: JsonDraftRepo
    research: JsonResearchRepo
    applications: JsonApplicationRepo
    conversations: JsonConversationRepo
    calendar: JsonCalendarRepo
    interview_prep: JsonInterviewPrepRepo
    posts: JsonPostRepo

    def as_tuple(self) -> tuple:
        return (
            self.contacts,
            self.companies,
            self.profile,
            self.drafts,
            self.research,
            self.applications,
            self.conversations,
            self.calendar,
            self.interview_prep,
        )


def create_repos(data_dir: DataDir) -> Repos:
    return Repos(
        contacts=JsonContactRepo(data_dir.contacts),
        companies=JsonCompanyRepo(data_dir.companies),
        profile=JsonProfileRepo(data_dir.profile),
        drafts=JsonDraftRepo(data_dir.drafts),
        research=JsonResearchRepo(data_dir.research),
        applications=JsonApplicationRepo(data_dir.applications),
        conversations=JsonConversationRepo(data_dir.conversations),
        calendar=JsonCalendarRepo(data_dir.calendar),
        interview_prep=JsonInterviewPrepRepo(data_dir.interview_prep),
        posts=JsonPostRepo(data_dir.posts),
    )
