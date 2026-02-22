# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinkedIn Job Hunt Assistant — a Python CLI combining a local CRM, AI-powered draft generation (Claude API), job application lifecycle tracking, interview prep, analytics, market intelligence, profile optimization, smart templates, content calendar, and conversation history. Supports JSON file storage (default) or SQLModel/PostgreSQL. Includes Playwright-based browser automation.

## Commands

```bash
# Install dependencies
uv sync
uv sync --extra dev          # pytest, ruff, coverage
uv sync --extra web          # Reflex web UI
uv sync --extra automation   # Playwright + keyring

# CLI (both entry points are equivalent)
uv run linkedin <command>
uv run linkedin-cli <command>

# Run the web dashboard
uv run linkedin-web

# Run tests
uv run pytest
uv run pytest tests/test_application_service.py::test_add_and_list   # single test
uv run pytest --cov=linkedin --cov-report=term-missing

# Lint / format
uv run ruff check src/ tests/
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/

# Database (only needed when using LINKEDIN_BACKEND=db)
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
uv run python -m linkedin.scripts.migrate_json_to_db
```

## Architecture

**Modular structure** — thin CLI → services → repositories → storage:

- `src/linkedin/cli.py` — Click groups + Rich formatting. No business logic; all calls go to services.
- `src/linkedin/constants.py` — Enums (`ContactStatus`, `CompanyPriority`, etc.), emoji mappings.
- `src/linkedin/types.py` — TypedDicts for all domain objects: `ContactDict`, `CompanyDict`, `ProfileDict`, `DraftDict`, `ResearchDict`, `ApplicationDict`, `ApplicationEventDict`, `InterviewPrepDict`, `ConversationDict`, `MessageDict`, `ContentPostDict`.
- `src/linkedin/ai/client.py` — `generate_with_ai(prompt, max_tokens, timeout_seconds, retries, backoff_seconds)` wrapping Anthropic API. Raises `AIClientError(RuntimeError)` on failure (auth errors are not retried). Retry/backoff configurable via `LINKEDIN_AI_*` env vars.

**Data layer:**
- `src/linkedin/data/repository.py` — Abstract base classes for all repos, including `ApplicationRepo`, `InterviewPrepRepo`, `ConversationRepo`, `CalendarRepo`.
- `src/linkedin/data/json_store.py` — JSON file implementations (default). All file path constants (`CONTACTS_FILE`, `APPLICATIONS_FILE`, etc.) are module-level and monkeypatched in tests.
- `src/linkedin/data/db_store.py` — SQLModel/SQLAlchemy implementations.
- `src/linkedin/data/factory.py` — `create_repos()` selects backend via `LINKEDIN_BACKEND` env var (`json` or `db`).

**Services** (`src/linkedin/services/`) — All business logic. Accept/return plain dicts:
- `contact_service.py` — CRUD, pipeline advancement, next-actions, outreach campaign management, duplicate detection + merge
- `company_service.py`, `profile_service.py` — CRUD
- `draft_service.py` — AI draft generation with offline fallback templates (connection, message, intro, thank you, follow-up, batch). Fallback controlled by `LINKEDIN_DRAFT_FALLBACK` env var.
- `application_service.py` — Job application lifecycle, AI tailor-resume / cover-letter / skills-gap
- `interview_service.py` — AI prep (questions+STAR), company research briefing, STAR scaffolds, questions-to-ask
- `conversation_service.py` — Per-contact message thread logging + plain-text export
- `calendar_service.py` — Content calendar (schedule, mark-posted, stats)
- `discover_service.py` — AI contact/company discovery suggestions
- `research_service.py` — Content research, post ideas, hashtags
- `market_service.py` — AI salary estimates, hiring trends, job posting import + skill-match scoring
- `optimizer_service.py` — AI headline/about/skills/full profile optimization
- `template_service.py` — `{{placeholder}}` templates, A/B testing, response tracking, auto-outcome recording
- `data_service.py` — CSV/JSON import/export, backup create/verify/restore (with path-traversal protection)
- `dashboard_service.py`, `analytics_service.py` — Overview aggregation, pipeline conversion, response rates

**Web UI** (`src/linkedin/web/`) — Reflex SaaS dashboard. Pages under `pages/`, Reflex State subclasses under `states/`.

**Automation** (`src/linkedin/automation/`) — Playwright-based browser automation with session persistence, keyring credentials, rate limiting, and daily safety limits (20 connections, 25 messages).

**Key patterns:**
- Services are instantiated with their repos at module level in `cli.py` and reused across commands.
- `LINKEDIN_BACKEND` env var selects `json` (default) or `db`. `DATABASE_URL` configures the DB.
- All AI calls use `generate_with_ai`; wrap in `try/except AIClientError` and return `(error_str, "")`.
- Mock patches target the usage site: `linkedin.services.<module>.generate_with_ai`.
- Contact pipeline: `not_contacted → connection_sent → connected → messaged → responded → call_scheduled → hired/rejected`.

## Testing

**Fixtures** (`tests/conftest.py`):
- `json_repos` — monkeypatches all `json_store` file path constants to a `tmp_path`; use for service tests.
- `db_engine` / `db_repos` — in-memory SQLite for DB store tests.
- `sample_contact`, `sample_company`, `sample_profile` — factory functions (accept `**overrides`). `sample_profile` includes `resume_text` by default.

**Test files:**
- `test_cli.py` — CLI integration tests via Click's `CliRunner` (88 tests, covers original commands).
- `test_cli_applications.py` — CLI integration tests for `applications`, `interview`, `conversations`, `calendar` command groups. Has `patch_json_paths` autouse fixture patching all file constants.
- `test_services.py` — Service unit tests for original services.
- `test_application_service.py`, `test_interview_service.py`, `test_conversation_service.py`, `test_calendar_service.py` — Service tests for new features including `AIClientError` paths.
- `test_data_service.py` — Needs its own monkeypatching of the `data_service` module's constants (separate from `json_store`).
- `test_db_store.py`, `test_json_store.py`, `test_factory.py` — Storage layer tests.
- `test_analytics.py`, `test_market.py`, `test_optimizer.py`, `test_templates.py` — Feature-specific tests.
- `test_automation.py`, `test_automation_scrape.py` — Automation config and action tests.

**Notes:**
- When adding records via `repo.add()` directly, include an `id` field. When using service methods (e.g. `add_contact()`), id is auto-generated.
- CLI tests that need a profile: invoke `profile setup` with input string `"Name\nHeadline\nRole\nSkills\nExp\nUnique\nIndustry\nLoc\nn\n"`. To include resume text, use `"y\n<resume text>\n\n\n"` for the last 4 tokens (confirm + content + two blank lines to terminate).

## Code Style

- Ruff rules `E`, `F`, `I`, `W`; `E501` ignored (long lines permitted for Rich table formatting).
- Line length: 120. Target: Python 3.10+.
- `src/linkedin/automation/` and `src/linkedin/migrations/versions/` excluded from lint.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and PR: ruff check → pytest → CLI smoke test across Python 3.10, 3.11, 3.12.
