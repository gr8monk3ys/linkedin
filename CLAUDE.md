# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinkedIn Job Hunt Assistant — a Python CLI combining a local CRM, AI-powered draft generation (Claude API), job application lifecycle tracking, interview prep, analytics, market intelligence, profile optimization, smart templates, content calendar, and conversation history. Storage is JSON files under `~/.linkedin-cli`. Includes Playwright-based browser automation.

## Commands

```bash
# Install dependencies
uv sync
uv sync --extra dev          # pytest, ruff, coverage
uv sync --extra automation   # Playwright + keyring

# CLI (both entry points are equivalent)
uv run linkedin <command>
uv run linkedin-cli <command>

# Run tests
uv run pytest
uv run pytest tests/test_application_service.py::test_add_and_list   # single test
uv run pytest --cov=linkedin --cov-report=term-missing

# Lint / format
uv run ruff check src/ tests/
uv run ruff check src/ tests/ --fix
uv run ruff format src/ tests/

```

## Architecture

**Modular structure** — thin CLI → services → repositories → storage:

- `src/linkedin/cli.py` — Click groups + Rich formatting. No business logic; all calls go to services.
- `src/linkedin/scheduling/schedule.py` — schedule-time math and the argv for a scheduled `run-daily`. Pure functions.
- `src/linkedin/scheduling/crontab.py` — the one delimited crontab block the CLI owns, plus the cron env file. Never rewrites unmanaged lines.
- `src/linkedin/services/run_state.py` — run log, lock file, idempotency keys, failure streaks, webhook notifications.
- `src/linkedin/constants.py` — Enums (`ContactStatus`, `CompanyPriority`, etc.), emoji mappings.
- `src/linkedin/types.py` — TypedDicts for all domain objects: `ContactDict`, `CompanyDict`, `ProfileDict`, `DraftDict`, `ResearchDict`, `ApplicationDict`, `ApplicationEventDict`, `InterviewPrepDict`, `ConversationDict`, `MessageDict`, `ContentPostDict`.
- `src/linkedin/ai/client.py` — `generate_with_ai(prompt, max_tokens, timeout_seconds, retries, backoff_seconds)` wrapping Anthropic API. Raises `AIClientError(RuntimeError)` on failure (auth errors are not retried). Retry/backoff configurable via `LINKEDIN_AI_*` env vars.

**Data layer:**
- `src/linkedin/data/repository.py` — Abstract base classes for all repos, including `ApplicationRepo`, `InterviewPrepRepo`, `ConversationRepo`, `CalendarRepo`.
- `src/linkedin/data/json_store.py` — JSON file implementations (default). All file path constants (`CONTACTS_FILE`, `APPLICATIONS_FILE`, etc.) are module-level and monkeypatched in tests.
- `src/linkedin/data/factory.py` — `create_repos()` builds the JSON repo set. A SQLModel/Postgres backend behind `LINKEDIN_BACKEND=db` was removed 2026-08-29 (unused since February; four of its nine repos silently fell back to JSON, splitting the dataset).

**Services** (`src/linkedin/services/`) — All business logic. Accept/return plain dicts:
- `contact_service.py` — CRUD, pipeline advancement, next-actions, outreach campaign management, duplicate detection + merge
- `company_service.py`, `profile_service.py` — CRUD
- `draft_service.py` — AI draft generation with offline fallback templates (connection, message, intro, thank you, follow-up, batch). Fallback controlled by `LINKEDIN_AI_FALLBACK_ENABLED` env var.
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
- `resume_service.py` — Bridge to the resume repo checkout (`LINKEDIN_RESUME_REPO` env var): variant discovery, `skills.tex` parsing, JD→variant matching, built-PDF resolution, autoapply `state.db` import. Stdlib only — never imports resume repo code.
- `inbox_service.py` — The inbound edge. Turns message threads and pending invitations into *proposed* pipeline transitions. Pure (dicts in, proposals out, no browser, no repo) because the matching logic is what can corrupt the CRM.
- `dashboard_service.py`, `analytics_service.py` — Overview aggregation, pipeline conversion, response rates

**Automation** (`src/linkedin/automation/`) — Playwright-based browser automation with session persistence, keyring credentials, rate limiting, and per-day safety limits persisted to `~/.linkedin-cli/automation_usage.json` (20 connections, 25 messages, 3 posts, 30 reactions, 15 Easy Applies). Actions live in `actions/` (connect, message, scrape, search, post, engage, profile_sync, easy_apply). The CLI `automate` group lazy-imports the stack via `_require_automation()`; CLI tests patch `_require_automation`/`_open_linkedin_session` in `linkedin.cli`.

- **Every module in this package must import without Playwright or keyring** — CI installs only `--extra dev`, and a module-scope `import playwright` drops that module *and everything importing it* to 0% coverage. That is how `linkedin_page.py` (the layer that actually talks to LinkedIn) went untested. Import Playwright types under `TYPE_CHECKING`, and `sync_playwright`/`keyring` inside the function that uses them. `tests/test_automation_import_safety.py` walks the package and fails if this regresses.
- **`automation/selectors.py` holds every LinkedIn selector.** Never inline one at a call site. Role/label locators are preferred over CSS — accessible names survive class-name churn. `FRAGILE_SELECTORS` catalogues the CSS ones that break on a markup change.
- **A markup change must not look like a quiet page.** These methods fail soft by design (a missing Connect button is normal), so the ones that cannot tell a breakage from an empty page call `self._record_miss(name)`. `LinkedInPage.selector_health()` reports them and `cli._close_linkedin_session` prints them at the end of every `automate` run. Close browsers through that helper, not `browser.close()`.
- **Messaging selectors are the most fragile in the file.** The pane is virtualized and lazy-loaded, so `THREAD_*` is the first place to look when `inbox sync` reports a quiet inbox.
- `tests/fake_page.py` is a Page/Locator double — register what the page contains, and anything unregistered resolves empty (exactly what a renamed class looks like).

**Key patterns:**
- Services are instantiated with their repos at module level in `cli.py` and reused across commands.
- All AI calls use `generate_with_ai`; wrap in `try/except AIClientError` and return `(error_str, "")`.
- Mock patches target the usage site: `linkedin.services.<module>.generate_with_ai`.
- Contact pipeline: `not_contacted → connection_sent → connected → messaged → responded → call_scheduled → hired/rejected`.
- **Every active contact always carries a `follow_up_date`.** `contact_service.FOLLOW_UP_CADENCE_DAYS` seeds it on add and on every status change; `hired`/`rejected` (`TERMINAL_STATUSES`) clear it and generate no actions. An explicit `follow_up=` argument still wins. Adding a pipeline status means adding its cadence entry *and* its rule in `get_next_actions` — a status with neither is invisible to the planner forever, which is what `messaged` was.
- **`get_next_actions` returns at most one action per contact**, highest priority first. A contact with no `created_at`/`last_contact` yields a `repair_contact` action rather than being skipped; `contacts repair` backfills it.
- **`run-daily` exits nonzero and reports `no_actions`** when the planner produces nothing while `active_pipeline_count() > 0`, and nonzero on `failed`. It previously returned exit 0 and status `success` in both cases, which is how it logged 136 consecutive green runs over five months while generating zero drafts. Never widen `_daily_run_status` back to unconditional success.
- **`json_store.save_json` is atomic** (temp file + fsync + `os.replace`). Every mutation rewrites the whole file, so a plain write loses the entire store if interrupted. `automation/safety.py` persists its daily budgets through it for the same reason — a truncated usage file reads back as "no usage today".
- **Nothing inbound auto-advances a contact.** `inbox sync` reads LinkedIn messaging and the sent-invitation manager and writes *proposals* to `inbox_proposals.json`; `inbox review` applies them one at a time. A contact whose status changed since the sync drops its proposal — the hand edit wins. `--yes` covers high-confidence proposals only: a proposal matched on display name alone is `low` confidence and is always asked about, and a name matching two contacts is no evidence about either.
- **`get_pending_sent_invitations` returns `None`, not `[]`, when it cannot read the list.** Every other page-object method fails soft to an empty result; this one must not. Acceptance is inferred from an invitation's *absence*, so a selector that stopped matching would otherwise read as "every outstanding invitation was accepted" and advance the whole pipeline at once. `[]` is returned only when LinkedIn's own empty state is on the page.
- **The reply signal rests entirely on `THREAD_OWN_MESSAGE_PREFIX`.** LinkedIn prefixes a thread snippet with `You:` when the last message is the user's own; that prefix is the only thing separating a real reply from an echo of the message we sent. Lose it and every outbound message becomes a fake response.
- **Applications have their own planner rules and their own plan section.** `APPLICATION_STATUS_RULES` mirrors `contact_service.STATUS_RULES`, with the same coverage check against `APPLICATION_STATUSES`. Kept out of `get_next_actions`: `_daily_run_status` classifies a run by whether the *contact* planner produced anything, and merging application rows in would let a due application mask a broken contact planner — the exact failure that guard exists to catch.
- **An offline template is never passed off as a draft.** `generate_with_ai` failing falls back to a template, and that fallback used to return `(None, text)` — indistinguishable from a real draft. The templates now ignore `context` entirely (it is prompt input, not body text; splicing it in verbatim turned a `--context` of instructions into the message itself), and `DraftService.last_draft_was_fallback` makes the CLI say so. Note the API key commonly lives in `~/.linkedin-cli/cron.env`, which only cron sources, so scheduled runs and interactive ones can disagree about whether AI works at all.
- **AI feed comments are reviewed before they are published.** `automation_service.engage_feed` takes an `approve_comment` callback and the CLI passes `_review_feed_comment` unless `--yes`; `sanitize_comment` drops empty, overlong, and refusal-shaped model output. The post body is untrusted third-party text fenced inside the prompt — it reaches the model as data, and its output goes out publicly under the user's real name.

## Testing

**Fixtures** (`tests/conftest.py`):
- `json_repos` — monkeypatches all `json_store` file path constants to a `tmp_path`; use for service tests.
- `sample_contact`, `sample_company`, `sample_profile` — factory functions (accept `**overrides`). `sample_profile` includes `resume_text` by default.

**Test files:**
- `test_cli.py` — CLI integration tests via Click's `CliRunner` (88 tests, covers original commands).
- `test_cli_applications.py` — CLI integration tests for `applications`, `interview`, `conversations`, `calendar` command groups. Has `patch_json_paths` autouse fixture patching all file constants.
- `test_services.py` — Service unit tests for original services.
- `test_application_service.py`, `test_interview_service.py`, `test_conversation_service.py`, `test_calendar_service.py` — Service tests for new features including `AIClientError` paths.
- `test_data_service.py` — Needs its own monkeypatching of the `data_service` module's constants (separate from `json_store`).
- `test_json_store.py`, `test_factory.py` — Storage layer tests, including `save_json` atomicity.
- `test_analytics.py`, `test_market.py`, `test_optimizer.py`, `test_templates.py` — Feature-specific tests.
- `test_automation.py`, `test_automation_scrape.py` — Automation config and action tests.
- `test_linkedin_page.py` — Page object against `tests/fake_page.py`; covers selector misses.
- `test_automation_import_safety.py` — Walks `linkedin.automation` asserting no module needs Playwright/keyring to import.
- `test_automation_connect_message_search.py` — Connect/message/search actions and their safety-budget accounting.
- `test_scheduling.py` — Schedule math and managed-crontab handling.
- `test_automation_actions.py` — Post/engage/profile-sync/easy-apply actions + persistent safety limits (MagicMock page objects, no Playwright).
- `test_resume_service.py` — Resume repo bridge (builds a fake checkout + autoapply SQLite db in tmp_path).
- `test_cli_automate.py` — CLI tests for the `automate` group and resume-repo application commands.
- `test_inbox_service.py` — The proposal matcher: URL vs name matching, the low-confidence path, and the unreadable-invitation-list case. No browser.
- `test_automation_inbox_jobs.py` — The read-only `inbox` and `jobs` actions.
- `test_cli_inbox.py` — CLI tests for `inbox sync/list/review` and `automate jobs`.

**Notes:**
- When adding records via `repo.add()` directly, include an `id` field. When using service methods (e.g. `add_contact()`), id is auto-generated.
- CLI tests that need a profile: invoke `profile setup` with input string `"Name\nHeadline\nRole\nSkills\nExp\nUnique\nIndustry\nLoc\nn\n"`. To include resume text, use `"y\n<resume text>\n\n\n"` for the last 4 tokens (confirm + content + two blank lines to terminate).

## Code Style

- Ruff rules `E`, `F`, `I`, `W`; `E501` ignored (long lines permitted for Rich table formatting).
- Line length: 120. Target: Python 3.10+.
- `src/linkedin/automation/` and `src/linkedin/migrations/versions/` excluded from lint.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and PR: ruff check → pytest → CLI smoke test across Python 3.10, 3.11, 3.12.
