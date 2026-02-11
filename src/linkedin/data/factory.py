"""Factory for selecting data backend (JSON or Database)."""

import os

from linkedin.data.repository import CompanyRepo, ContactRepo, DraftRepo, ProfileRepo, ResearchRepo


def get_backend() -> str:
    """Return the configured backend: 'db' or 'json'."""
    return os.environ.get("LINKEDIN_BACKEND", "json").lower()


def create_repos() -> tuple[ContactRepo, CompanyRepo, ProfileRepo, DraftRepo, ResearchRepo]:
    """Create repository instances based on the configured backend."""
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
        return (
            DbContactRepo(),
            DbCompanyRepo(),
            DbProfileRepo(),
            DbDraftRepo(),
            DbResearchRepo(),
        )

    from linkedin.data.json_store import (
        JsonCompanyRepo,
        JsonContactRepo,
        JsonDraftRepo,
        JsonProfileRepo,
        JsonResearchRepo,
    )

    return (
        JsonContactRepo(),
        JsonCompanyRepo(),
        JsonProfileRepo(),
        JsonDraftRepo(),
        JsonResearchRepo(),
    )
