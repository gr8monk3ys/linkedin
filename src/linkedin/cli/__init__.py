#!/usr/bin/env python3
"""LinkedIn Job Hunt Assistant CLI."""

import click
from rich.console import Console

from linkedin.data.factory import create_repos, create_template_repo
from linkedin.data.json_store import ensure_dirs
from linkedin.services.analytics_service import AnalyticsService
from linkedin.services.company_service import CompanyService
from linkedin.services.contact_service import ContactService
from linkedin.services.dashboard_service import DashboardService
from linkedin.services.data_service import DataService
from linkedin.services.discover_service import DiscoverService
from linkedin.services.draft_service import DraftService
from linkedin.services.market_service import MarketService
from linkedin.services.optimizer_service import OptimizerService
from linkedin.services.profile_service import ProfileService
from linkedin.services.research_service import ResearchService
from linkedin.services.template_service import TemplateService

console = Console()

# Repositories (backend selected by LINKEDIN_BACKEND env var)
ensure_dirs()
_contact_repo, _company_repo, _profile_repo, _draft_repo, _research_repo = create_repos()

# Services
_profile_svc = ProfileService(_profile_repo)
_contact_svc = ContactService(_contact_repo, _company_repo)
_company_svc = CompanyService(_company_repo, _contact_repo)
_draft_svc = DraftService(_draft_repo, _contact_repo, _profile_repo)
_discover_svc = DiscoverService(_profile_repo, _company_repo, _contact_repo)
_research_svc = ResearchService(_profile_repo, _research_repo, _draft_repo)
_data_svc = DataService(_contact_repo, _company_repo)
_dashboard_svc = DashboardService(_profile_repo, _contact_repo, _company_repo, _draft_repo)
_analytics_svc = AnalyticsService(_contact_repo, _draft_repo)
_market_svc = MarketService(_profile_repo)
_optimizer_svc = OptimizerService(_profile_repo)
_template_svc = TemplateService(_contact_repo, create_template_repo())


@click.group()
@click.version_option(version="3.0.0", prog_name="linkedin")
def cli():
    """
    LinkedIn Job Hunt Assistant

    \b
    A local CRM + AI-powered tool to accelerate your job search:
    - Track contacts and outreach status
    - Generate personalized drafts with AI
    - Research high-engagement content
    - Plan your LinkedIn strategy

    \b
    Quick Start:
      1. linkedin profile setup         # Add your info
      2. linkedin contacts add          # Add target contacts
      3. linkedin drafts connection 1   # AI writes your outreach
    """
    ensure_dirs()


# Register subgroups - must be after cli and services are defined
from linkedin.cli import analytics, automation, companies, contacts, data, drafts, outreach, profile  # noqa: E402, F401
