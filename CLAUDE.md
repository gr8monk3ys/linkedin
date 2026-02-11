# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinkedIn Job Hunt Assistant (v2.0.0) — a Python CLI + web dashboard combining a local CRM, AI-powered draft generation (via Claude API), analytics, market intelligence, profile optimization, smart templates, and content research for LinkedIn job searching. Supports JSON file storage (default) or SQLModel/PostgreSQL database backend. Includes Playwright-based browser automation.

## Commands

```bash
# Install dependencies
uv sync

# Install optional deps
uv sync --extra web          # Reflex web UI
uv sync --extra automation   # Playwright + keyring

# Run the CLI
uv run linkedin <command>

# Run the web dashboard
uv run linkedin-web

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_services.py::TestContactService::test_add_and_list

# Run with coverage
uv run pytest --cov=linkedin --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Format
uv run ruff format src/ tests/

# Run Alembic migrations
uv run alembic upgrade head

# Generate new migration after model changes
uv run alembic revision --autogenerate -m "description"

# Migrate JSON data to database
uv run python -m linkedin.scripts.migrate_json_to_db
```

## Architecture

**Modular structure** — decomposed from a monolith into clean layers:

- `src/linkedin/cli.py` — Thin CLI layer: Click groups + Rich formatting. Calls services, no business logic.
- `src/linkedin/constants.py` — Enums (`ContactStatus`, `CompanyPriority`, etc.), emoji mappings, display tuples.
- `src/linkedin/types.py` — TypedDicts: `ContactDict`, `CompanyDict`, `ProfileDict`, `DraftDict`, `ResearchDict`.
- `src/linkedin/ai/client.py` — `generate_with_ai(prompt, max_tokens)` wrapping Anthropic API.

**Data layer:**
- `src/linkedin/data/repository.py` — Abstract base classes: `ContactRepo`, `CompanyRepo`, `ProfileRepo`, `DraftRepo`, `ResearchRepo`.
- `src/linkedin/data/json_store.py` — JSON file implementations. Default backend.
- `src/linkedin/data/db_store.py` — SQLModel/SQLAlchemy implementations.
- `src/linkedin/data/factory.py` — `create_repos()` selects backend via `LINKEDIN_BACKEND` env var (`json` or `db`).
- `src/linkedin/models/base.py` — SQLModel table classes (`Profile`, `Company`, `Contact`, `Activity`, `Draft`, `Research`, `OutreachEvent`, `JobPosting`, `MarketInsight`, `ProfileSuggestion`, `Template`, `TemplateUsage`).
- `src/linkedin/migrations/` — Alembic migration scripts.

**Services** (`src/linkedin/services/`) — Business logic, accept/return plain data:
- `contact_service.py`, `company_service.py`, `profile_service.py` — CRUD + pipeline management
- `draft_service.py` — AI draft generation (connection, message, intro, thank you, follow-up, batch)
- `discover_service.py` — AI-powered contact/company discovery
- `research_service.py` — Content research, post ideas, hashtags
- `data_service.py` — Import/export (CSV/JSON), backup/restore
- `dashboard_service.py` — Overview aggregation
- `analytics_service.py` — Pipeline conversion, response rates, outreach velocity, source effectiveness
- `market_service.py` — AI salary estimates, hiring trends, job posting tracker
- `optimizer_service.py` — AI headline/about/skills/full profile optimization
- `template_service.py` — Reusable templates with `{{placeholders}}`, A/B testing, response tracking

**Web UI** (`src/linkedin/web/`) — Reflex SaaS dashboard:
- `app.py` — App definition, page registration
- `layout.py` — Sidebar + topbar navigation
- `pages/` — dashboard, contacts, companies, drafts, discover, research, settings
- `states/` — Reflex State subclasses per page

**Automation** (`src/linkedin/automation/`) — Playwright-based browser automation:
- `browser.py` — BrowserManager with session persistence
- `credentials.py` — Keyring-based secure credential storage
- `rate_limiter.py` — Configurable delays with random jitter
- `safety.py` — Conservative daily limits (20 connections, 25 messages)
- `linkedin_page.py` — Page object model using accessible locators
- `actions/` — login, connect, message, search modules

**Key patterns:**
- Repository pattern with abstract base classes for data access.
- Services injected with repos at module level in `cli.py`.
- `DATABASE_URL` env var configures DB (default: `sqlite:///~/.linkedin-cli/linkedin.db`).
- `LINKEDIN_BACKEND` env var selects `json` (default) or `db` backend.
- Mock patches target usage sites: `linkedin.services.<module>.generate_with_ai`.

**Contact pipeline:** `not_contacted → connection_sent → connected → messaged → responded → call_scheduled → hired/rejected`.

## Testing

- `tests/conftest.py` — Shared fixtures: `db_engine`, `db_repos`, `json_repos`, factory functions (`sample_contact`, `sample_company`, `sample_profile`). The `json_repos` fixture monkeypatches all file path constants to temp dirs.
- `tests/test_cli.py` — CLI integration tests using Click's `CliRunner`.
- `tests/test_services.py` — Service unit tests for all original services.
- `tests/test_analytics.py`, `test_market.py`, `test_optimizer.py`, `test_templates.py` — Phase 4 feature tests.
- `tests/test_data_service.py` — Data import/export/backup tests (needs separate monkeypatching of `data_service` module constants).
- `tests/test_db_store.py` — DB repository tests using in-memory SQLite.
- `tests/test_factory.py` — Backend factory selection tests.
- `tests/test_automation.py` — Config, rate limiter, safety limits tests.

When adding contacts via `repo.add()` directly in tests, include an `id` field. When using `ContactService.add_contact()`, the id is auto-generated.

## Code Style

- Ruff with rules `E`, `F`, `I`, `W` enabled; `E501` ignored (long lines allowed for Rich formatting)
- Line length: 120
- Target: Python 3.10+
- `src/linkedin/automation/` and `src/linkedin/migrations/versions/` excluded from lint
