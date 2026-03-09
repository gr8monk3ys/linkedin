"""Factory for selecting data backend (JSON, Database, or Twenty CRM)."""

import os
from pathlib import Path

from linkedin.data.repository import (
    CompanyRepo,
    ContactRepo,
    DraftRepo,
    ProfileRepo,
    ResearchRepo,
    TemplateRepo,
)

DATA_DIR = Path.home() / ".linkedin-cli"


def get_backend() -> str:
    """Return the configured backend: 'db', 'json', or 'twenty'."""
    return os.environ.get("LINKEDIN_BACKEND", "json").lower()


def create_repos() -> tuple[ContactRepo, CompanyRepo, ProfileRepo, DraftRepo, ResearchRepo]:
    """Create repository instances based on the configured backend."""
    backend = get_backend()

    if backend == "twenty":
        from linkedin.data.json_store import JsonProfileRepo, JsonResearchRepo
        from linkedin.data.twenty_client import TwentyClient
        from linkedin.data.twenty_setup import ensure_custom_fields
        from linkedin.data.twenty_store import TwentyCompanyRepo, TwentyContactRepo, TwentyDraftRepo, _IdMapper

        client = TwentyClient()
        url = client.base_url
        if not client.health_check():
            raise SystemExit(f"Cannot reach Twenty CRM at {url}. Is the Pi running?")

        ensure_custom_fields(client)
        id_mapper = _IdMapper(DATA_DIR / "twenty_id_map.json")

        return (
            TwentyContactRepo(client, id_mapper),
            TwentyCompanyRepo(client, id_mapper),
            JsonProfileRepo(),
            TwentyDraftRepo(client, id_mapper),
            JsonResearchRepo(),
        )

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


def create_template_repo() -> TemplateRepo:
    """Create a template repository based on the configured backend."""
    backend = get_backend()

    if backend == "db":
        from linkedin.data.db_store import DbTemplateRepo
        from linkedin.models.base import create_tables

        create_tables()
        return DbTemplateRepo()

    from linkedin.data.json_store import JsonTemplateRepo

    return JsonTemplateRepo()
