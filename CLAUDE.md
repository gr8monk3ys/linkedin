# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinkedIn Job Hunt Assistant (v3.0.0) is a Python CLI plus Reflex web dashboard for running a LinkedIn-heavy job search. It combines a local CRM, AI-powered draft generation, company/contact discovery, analytics, market intelligence, profile optimization, smart templates, job application tracking, interview prep, content planning, and optional Playwright automation.

Supported storage backends:
- `json` (default)
- `db` via SQLModel / SQLAlchemy
- `twenty` for contacts, companies, and drafts, with local JSON fallbacks for profile/research and newer feature stores

## Commands

```bash
# Install dependencies
uv sync
uv sync --extra dev
uv sync --extra web
uv sync --extra automation

# CLI
uv run linkedin <command>
uv run linkedin-cli <command>

# Web UI
uv run linkedin-web

# Tests
uv run pytest
uv run pytest tests/test_application_service.py::test_add_and_list

# Lint
uv run ruff check src tests
uv run ruff check src tests --fix

# Database migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
```

## Architecture

Thin command/state layers call services, which depend on repositories, which depend on the selected storage backend.

Key modules:
- `src/linkedin/cli/__init__.py` wires shared services for the package-based CLI entrypoint.
- `src/linkedin/cli/*.py` defines Click command groups with Rich output.
- `src/linkedin/web/states/*.py` defines Reflex state classes for the web UI.
- `src/linkedin/services/*.py` contains business logic and returns plain dicts or `Result`.
- `src/linkedin/data/repository.py` defines abstract repo interfaces.
- `src/linkedin/data/json_store.py` implements JSON-backed repos.
- `src/linkedin/data/db_store.py` implements SQLModel-backed repos.
- `src/linkedin/data/twenty_store.py` implements Twenty-backed repos for the supported entities.
- `src/linkedin/data/factory.py` selects repos from `LINKEDIN_BACKEND` and exposes `create_template_repo()`.
- `src/linkedin/models/base.py` contains SQLModel models and engine/session helpers.
- `src/linkedin/types.py` defines the TypedDict shapes for domain data.
- `src/linkedin/ai/client.py` wraps Anthropic and raises `AIClientError` on failures.

Core services:
- `contact_service.py` handles CRM operations, reminders, next actions, dedupe, and outreach campaigns.
- `draft_service.py` generates connection/message/follow-up drafts and supports deterministic fallback text.
- `template_service.py` persists reusable templates, tracks usage, and computes A/B results.
- `data_service.py` handles import/export plus JSON-only backup, verify, and restore flows.
- `application_service.py`, `interview_service.py`, `conversation_service.py`, `calendar_service.py` support newer job-search workflows.
- `discover_service.py`, `research_service.py`, `market_service.py`, `optimizer_service.py` handle AI suggestions and analysis.

## Backend Notes

- `LINKEDIN_BACKEND` selects `json`, `db`, or `twenty`.
- `DATABASE_URL` configures the DB backend; default SQLite path is `~/.linkedin-cli/linkedin.db`.
- `create_repos()` returns nine repos in a fixed order:
  `contact, company, profile, draft, research, application, conversation, calendar, interview_prep`
- Templates are created separately through `create_template_repo()`.
- `linkedin data export` works against the active backend.
- `linkedin data backup`, `restore`, and `backups` are intentionally limited to `LINKEDIN_BACKEND=json`.

## AI Patterns

- `generate_with_ai()` raises `AIClientError` on real failures.
- Service layers should normalize AI output into `Result` or `(error, data)` contracts.
- Some tests still patch inline error strings like `[AI generation failed: ...]`, so helpers normalize both raised and inline error shapes.
- Patch the usage site in tests, for example `linkedin.services.draft_service.generate_with_ai` or `linkedin.services.research_service.generate_ai_text`.

## Testing

Important fixtures in `tests/conftest.py`:
- `json_repos` monkeypatches `json_store` paths to a temp directory.
- `db_engine` and `db_repos` provide in-memory SQLite coverage.
- `json_template_repo` and `db_template_repo` cover template persistence paths.
- `sample_contact`, `sample_company`, `sample_profile`, and `sample_application` are helper factories.

Notable test files:
- `tests/test_cli.py` covers the CLI with `CliRunner`.
- `tests/test_services.py` covers the core service layer.
- `tests/test_application_service.py`, `tests/test_interview_service.py`, `tests/test_conversation_service.py`, and `tests/test_calendar_service.py` cover newer features.
- `tests/test_data_service.py`, `tests/test_db_store.py`, `tests/test_json_store.py`, and `tests/test_factory.py` cover storage/backends.
- `tests/test_web_states.py` smoke-tests Reflex state wiring.

## Code Style

- Python 3.10+.
- Ruff rules: `E`, `F`, `I`, `W`; `E501` ignored.
- Line length: 120.
- `src/linkedin/automation/` and Alembic version files are excluded from Ruff.

## CI

GitHub Actions runs Ruff, pytest, CLI smoke checks, and a Reflex web smoke flow.
