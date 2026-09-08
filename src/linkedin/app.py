"""The object graph for one data directory.

`App.from_env()` is what the CLI builds; `App(DataDir(tmp_path))` is what a
test builds. Every repo and service hangs off it, so the CLI reaches
`_app.contact_svc` and nothing at module scope touches disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkedin.data.factory import Repos, create_repos
from linkedin.data.paths import DataDir
from linkedin.services.analytics_service import AnalyticsService
from linkedin.services.application_service import ApplicationService
from linkedin.services.automation_service import AutomationService
from linkedin.services.company_service import CompanyService
from linkedin.services.contact_service import ContactService
from linkedin.services.content_service import ContentService
from linkedin.services.dashboard_service import DashboardService
from linkedin.services.data_service import DataService
from linkedin.services.draft_service import DraftService
from linkedin.services.inbox_service import InboxService
from linkedin.services.metrics_service import MetricsService
from linkedin.services.post_service import PostService
from linkedin.services.postings_service import PostingService
from linkedin.services.profile_service import ProfileService
from linkedin.services.ranking_service import RankingService
from linkedin.services.resume_service import linkedin_copy


@dataclass
class App:
    data_dir: DataDir
    repos: Repos = field(init=False)

    def __post_init__(self) -> None:
        r = self.repos = create_repos(self.data_dir)
        d = self.data_dir
        self.profile_svc = ProfileService(r.profile, copy_loader=linkedin_copy)
        self.contact_svc = ContactService(r.contacts, r.companies)
        self.ranking_svc = RankingService(r.contacts, r.companies, r.profile)
        self.company_svc = CompanyService(r.companies, r.contacts)
        self.draft_svc = DraftService(r.drafts, r.contacts, r.profile)
        self.data_svc = DataService(d)
        self.dashboard_svc = DashboardService(r.profile, r.contacts, r.companies, r.drafts)
        self.analytics_svc = AnalyticsService(r.contacts, r.drafts)
        self.posting_svc = PostingService(r.profile, d.job_postings)
        self.application_svc = ApplicationService(r.applications, r.profile, r.contacts)
        self.post_svc = PostService(r.posts)
        self.metrics_svc = MetricsService(d.metrics, r.posts)
        self.content_svc = ContentService(r.profile, r.drafts, r.calendar, r.posts)
        self.automation_svc = AutomationService(r.profile)
        self.inbox_svc = InboxService()

    @classmethod
    def from_env(cls) -> App:
        return cls(DataDir.from_env())

    @property
    def contact_repo(self):
        return self.repos.contacts

    @property
    def company_repo(self):
        return self.repos.companies

    @property
    def profile_repo(self):
        return self.repos.profile

    @property
    def draft_repo(self):
        return self.repos.drafts

    @property
    def application_repo(self):
        return self.repos.applications

    @property
    def calendar_repo(self):
        return self.repos.calendar

    @property
    def post_repo(self):
        return self.repos.posts
