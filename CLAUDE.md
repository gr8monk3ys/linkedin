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
- `src/linkedin/services/daily_run.py` — the daily run: `DailyRun(app, RunConfig).execute(trigger, run_at)` owns idempotency, retry/backoff, the failure-streak escalation and recovery, the run log, and the `success | no_actions | failed` classification. `build_plan(data)` shapes the plan into ordered `Section`s that the terminal (Rich) and the recap (`DailyPlan.to_markdown`) both iterate — a new section is one entry, not three functions.
- `src/linkedin/services/diagnostics.py` — the one check list behind `automation doctor` and `automation status`. It reads the macOS LaunchAgent too (`launchd_job`): the daily run on this machine is a launchd job, and the doctor once reported "no schedule" for one that fired every morning. `health` was a second copy under different names and is gone; CI's smoke step calls `automation doctor --json --time 09:00`.
- `src/linkedin/services/run_state.py` — run log, lock file, idempotency keys, webhook notifications: the storage `daily_run` sits on.
- `src/linkedin/constants.py` — Enums (`ContactStatus`, `CompanyPriority`, etc.), emoji mappings.
- `src/linkedin/types.py` — TypedDicts for all domain objects: `ContactDict`, `CompanyDict`, `ProfileDict`, `DraftDict`, `ResearchDict`, `ApplicationDict`, `ApplicationEventDict`, `InterviewPrepDict`, `ConversationDict`, `MessageDict`, `ContentPostDict`.
- `src/linkedin/ai/client.py` — the AI seam. `ai_call(prompt, *, max_tokens, fallback=None) -> AIResult(text, error, was_fallback)` is what services call; it never raises. `generate_with_ai(...)` underneath is the raw call that raises `AIClientError` (auth errors are not retried) and is what tests patch. Model from `LINKEDIN_AI_MODEL`; retry/backoff via `LINKEDIN_AI_*` env vars.

**Data layer:**
- `src/linkedin/data/paths.py` — `DataDir`: the one root every file lives under (`LINKEDIN_DATA_DIR`, default `~/.linkedin-cli`), one property per file. Nothing reads a module-level path constant at call time; there are none.
- `src/linkedin/data/json_store.py` — JSON file stores. Each `Json*Repo(path)` takes its file at construction. `load_json` / `save_json` are the only module functions.
- `src/linkedin/data/factory.py` — `create_repos(data_dir) -> Repos`. The abstract repository classes were deleted with the SQLModel/Postgres backend (removed 2026-08-29; four of its nine repos silently fell back to JSON, splitting the dataset): a seam with one adapter is hypothetical.
- `src/linkedin/app.py` — `App(data_dir)`: every repo and service for one directory. `cli.py` holds a lazy `_app` handle built from the environment on first use, so importing the CLI never touches disk. Commands reach `_app.contact_svc`, `_app.data_dir.recaps`, and so on.

**Services** (`src/linkedin/services/`) — All business logic. Accept/return plain dicts:
- `planner.py` — every table the planner reads: `STATUS_RULES`, `APPLICATION_STATUS_RULES`, and `ACTIONS` (one row per action name: `label`, `command`, `draft` spec or None). Three coverage checks run at import; `contact_service` and `application_service` re-export the rule tables from here.
- `ranking_service.py` — ranks contacts 0–100 by career priority (hiring-side title, tracked-company priority, industry overlap, relationship) with named reasons. `pinned` contacts are exempt: always 100, first in `contacts rank`, never in `--bottom`, and the target set for `automate engage --pinned`. `get_next_actions(scores=)` adds `connection_bonus(score)` (0–25) to every `send_connection` priority, so the day's scarce invitations go to the top of the ranking; `DailyRun` passes the scores.
- `contact_service.py` — CRUD, pipeline advancement, next-actions, outreach campaign management, duplicate detection + merge, pin/unpin
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

**Automation** (`src/linkedin/automation/`) — Playwright-based browser automation behind one module, `session.py`. `LinkedInSession.open(data_dir, headless=, dry_run=, on_login_needed=)` starts the browser, establishes the login (saved session first, keyring second, then a person at the window), and always closes. Its named verbs (`connect`, `message`, `post`, `react`, `like_post`, `comment`, `sync_profile`, `easy_apply`, `search`, `jobs`, `scrape`, `inbox`) each do the same six things — budget, pace, navigate, page verb, record on success — and return one `ActionResult(status, reason, data)` with status `ok | skipped | refused | failed`, truthy only on `ok`. A dry run navigates and reads, never writes, never spends. `budget.py` is the daily budget: `Budget.spend(kind, n)` / `remaining(kind)` over one caps table read from `limits.json` (seeded with the ramp caps: 0 connections, 1 post, 5 reactions, 2 comments per day) and today's usage in `automation_usage.json`; `automate limits set <kind> <n>` steps a cap up. There is no "no budget". The CLI opens sessions through `_open_session()`; tests use the `fake_session` fixture, which makes `LinkedInSession.open` yield `tests/fake_session.FakeSession` — the second adapter at the session port, with scripted results and recorded calls.

- **Every module in this package must import without Playwright or keyring** — CI installs only `--extra dev`, and a module-scope `import playwright` drops that module *and everything importing it* to 0% coverage. That is how `linkedin_page.py` (the layer that actually talks to LinkedIn) went untested. Import Playwright types under `TYPE_CHECKING`, and `sync_playwright`/`keyring` inside the function that uses them. `tests/test_automation_import_safety.py` walks the package and fails if this regresses.
- **`automation/selectors.py` holds every LinkedIn selector.** Never inline one at a call site. Role/label locators are preferred over CSS — accessible names survive class-name churn. `FRAGILE_SELECTORS` catalogues the CSS ones that break on a markup change.
- **A markup change must not look like a quiet page.** Reads that cannot tell a breakage from an empty page call `self._record_miss(name)`. Writes return `WriteResult(outcome, detail)` with outcome `ok | not_applicable | selector_missing | degraded`: a normal absence (already connected, not connected, already liked, no About section) is `not_applicable`; an affordance the page should have had is `selector_missing` and is recorded; `degraded` is a write that happened but whose follow-up could not be read (a post with no URN). The session maps these to `skipped` / `failed` / `ok`. `create_post` refuses the legacy Quill editor rather than typing into it. `LinkedInPage.selector_health()` reports every miss and `cli._open_session` prints them on close — the catalogue covers the write path too, so a renamed Connect button is no longer a bare False.
- **The home feed and profile pages were rebuilt with obfuscated markup (verified 2026-09-03).** No `feed-shared-update-v2`, no `data-urn`, no `h1` name. `get_feed_posts` reads cards by shape through `FEED_POSTS_SCRIPT` (the smallest ancestor of a "Reaction button state" button that also holds a Comment button) and tags each with `FEED_CARD_TAG` so `like_post`/`comment_on_post` can address them by index; `scrape_profile` falls back to `_profile_from_text` (name, optional pronouns or degree line, headline, location, About block). Recent-activity pages still carry the old markup, which is why `react(profile_url)` never needed this. The like control's label is now `Reaction button state: <state>`; anything but `no reaction` means we already reacted, and `LIKE_ALREADY_REACTED` must keep matching it or `engage` will un-like posts.
- **Messaging selectors are the most fragile in the file.** The pane is virtualized and lazy-loaded, so `THREAD_*` is the first place to look when `inbox sync` reports a quiet inbox.
- `tests/fake_page.py` is a Page/Locator double — register what the page contains, and anything unregistered resolves empty (exactly what a renamed class looks like).

**Key patterns:**
- Services are instantiated with their repos at module level in `cli.py` and reused across commands.
- All AI calls go through `ai_call` and read the `AIResult`. No service catches `AIClientError` or lets it reach the CLI; the tuple-returning services hand back `(result.error, result.text)`.
- Mock patches target the one seam: `linkedin.ai.client.generate_with_ai` (return a string, or `side_effect=AIClientError`).
- Contact pipeline: `not_contacted → connection_sent → connected → messaged → responded → call_scheduled → hired/rejected`.
- **Every active contact always carries a `follow_up_date`.** `contact_service.FOLLOW_UP_CADENCE_DAYS` seeds it on add and on every status change; `hired`/`rejected` (`TERMINAL_STATUSES`) clear it and generate no actions. An explicit `follow_up=` argument still wins. Adding a pipeline status means adding its row in `planner.STATUS_RULES`; adding an action means adding its row in `planner.ACTIONS` with a label, a command, and a draft spec (or None). Import fails otherwise. A status with no rule was invisible to the planner forever (that was `messaged`); an action with no row rendered as a bare slug and drafted nothing in `run-daily` (that was `send_connection` and `follow_up_messaged`). The three date-driven actions have no rule, so a test walks those branches instead.
- **`run-daily` drafts through `DraftService.generate_for_action(action)`**, which reads the planner row. Never add an `if action == ...` branch in the CLI.
- **`get_next_actions` returns at most one action per contact**, highest priority first. A contact with no `created_at`/`last_contact` yields a `repair_contact` action rather than being skipped; `contacts repair` backfills it.
- **`run-daily` exits nonzero and reports `no_actions`** when the planner produces nothing while a contact is due or stranded, and nonzero on `failed`. It previously returned exit 0 and status `success` in both cases, which is how it logged 136 consecutive green runs over five months while generating zero drafts. Never widen `DailyRun.classify` back to unconditional success. Tests reach the lifecycle through `DailyRun` (`tests/test_daily_run.py`), not by patching CLI privates.
- **`json_store.save_json` is atomic** (temp file + fsync + `os.replace`). Every mutation rewrites the whole file, so a plain write loses the entire store if interrupted. `automation/budget.py` persists today's usage through it for the same reason — a truncated usage file reads back as "no usage today".
- **Backups enumerate the data directory** (`DataDir.backup_members`), not a list. A list is how job postings, templates, the usage counters, and the inbox proposals were left out of every backup. Excluded on purpose: the browser session (cookies), the lock, temp files.
- **Nothing inbound auto-advances a contact.** `inbox sync` reads LinkedIn messaging and the sent-invitation manager and writes *proposals* to `inbox_proposals.json`; `inbox review` applies them one at a time. Both halves of that invariant live in `inbox_service.py`, pure and tested without a CLI runner: `propose_transitions` decides what to propose, `review_proposals(proposals, contacts, confirm=, yes=)` decides what may be applied — a contact whose status changed since the sync drops its proposal (the hand edit wins), a missing contact drops it, `--yes` covers high-confidence proposals only, and a proposal matched on display name alone is `low` confidence and is always put to `confirm`. The CLI keeps only the prompt and the write.
- **`inbox sync` keeps a thread index** (`thread_index.json`): sender name and URL, when they last wrote, whether the last word is theirs, first/last seen, whether they are a contact. No message bodies. `inbound_from_strangers(index, since)` is the growth goal's metric (someone who is not a contact wrote unprompted); `inbox strangers --days N` lists them. The matcher discards strangers, which is why the index exists.
- **`get_pending_sent_invitations` returns `None`, not `[]`, when it cannot read the list.** Every other page-object method fails soft to an empty result; this one must not. Acceptance is inferred from an invitation's *absence*, so a selector that stopped matching would otherwise read as "every outstanding invitation was accepted" and advance the whole pipeline at once. `[]` is returned only when LinkedIn's own empty state is on the page.
- **The reply signal rests entirely on `THREAD_OWN_MESSAGE_PREFIX`.** LinkedIn prefixes a thread snippet with `You:` when the last message is the user's own; that prefix is the only thing separating a real reply from an echo of the message we sent. Lose it and every outbound message becomes a fake response.
- **Applications have their own planner rules and their own plan section.** `APPLICATION_STATUS_RULES` mirrors `contact_service.STATUS_RULES`, with the same coverage check against `APPLICATION_STATUSES`. Kept out of `get_next_actions`: `DailyRun.classify` classifies a run by whether the *contact* planner produced anything, and merging application rows in would let a due application mask a broken contact planner — the exact failure that guard exists to catch.
- **AI can be off by choice.** `settings.json` (`settings ai off`) sets `ai_enabled: false`: `ai_call` returns `AI_DISABLED` at once (no retries, no network, no template), `run-daily` skips drafting and stays green, and the doctor reports the key as "disabled by choice" instead of nagging. The user runs this way: drafts and post candidates are written by hand (Claude through the browser) and enter the same pipeline through `drafts add CONTACT --file/--text` and `posts add-candidate --file/--text`, saved with `source: ai` and `generated_from: hand-written`. The Sunday batch is then: `posts facts` → write candidates → `posts add-candidate` each → `posts review` → `posts publish-due`.
- **Every message and post prompt ends with `ai/style.STYLE_RULES`** (no em dashes, emojis, exclamation marks, lists of three, or the AI vocabulary; plain words, one concrete detail, a specific ask). A generated-sounding message to a real person costs the reply. Drafts written by hand follow the same rules.
- **An offline template is never passed off as a draft.** Fallback-ness is a property of the value: `AIResult.was_fallback`, stamped onto the saved row as `source: "ai" | "template"`. A row with no `source` (saved before provenance was recorded) is unknown, and `automate post` / `automate message --draft-id` refuse both unknown and template rows. `run-daily` counts a template as a failed draft, saves nothing, and exits nonzero with status `failed` — that is how an invalid key in `cron.env` becomes visible instead of logging 150 green runs. The templates ignore `context` entirely (it is prompt input, not body text). Note the API key commonly lives in `~/.linkedin-cli/cron.env`, which only cron sources, so scheduled runs and interactive ones can disagree about whether AI works at all.
- **Account metrics are read from page text by label, never by class**, and a label that is not on the page reads as `None`, never `0` — a zero in the series is a data point, a missing one is a gap (`metrics collect`, `metrics show`, `MetricsService`, `metrics.json`, one row per day). Verified live 2026-09-02: followers and the rest come from `/dashboard/` (number on the line *before* its label), connections from `/mynetwork/` (the profile caps it at "500+"), and this account has no SSI access (LinkedIn discontinued it), which is recorded as None without a selector miss. `run-daily --collect-metrics` (on by default in `automation schedule` and `doctor --fix`) collects before the plan and never fails the run; the plan's optional Metrics section shows the latest row with 7-day deltas.
- **The headline and About come from the resume repo**, `docs/linkedin-copy.md`, through `resume_service.linkedin_copy`; `ProfileService.get_profile` overlays them and marks `copy_source`. The local profile file's copy is a fallback for machines without the checkout (`LINKEDIN_RESUME_REPO`, defaulting to `~/code/resume`). The two had drifted for five months and `sync-profile` would have pushed the stale one.
- **`automation doctor --probe-ai` proves the key**, one tiny `models.list` call per source (cron.env and shell). Presence is not validity: the cron.env key was present and returned 401 for five months while every check said ok.
- **Posts come from public fleet facts, and only those.** `fleet_facts.collect_fleet_facts` reads merged PRs and pushed repos through `gh` with `--visibility public` and drops any PR whose repo is not in the public list; `content_service.build_prompt` fences the digest as data. `posts draft-week` saves candidates as `post_fleet` drafts with `source: ai` and **no fallback** — AI down means no candidates and exit 1. `posts review` approves (schedules the next Tuesday) or rejects. `posts publish-due` publishes the next due entry unless the skip rule fires: when the last three measured posts all drew fewer impressions than the median of the earlier ones it exits 2 and leaves the entry scheduled (`--force` overrides). A non-AI draft on the calendar is never published.
- **A published post is recorded with its URN** in `posts.json` (`PostService.record_published`; `posts list`). The URN is the only join key to per-post metrics; a post whose success link could not be read back is recorded with an empty URN and flagged as unmeasurable, and the CLI says so instead of "published".
- **AI feed comments are reviewed before they are published.** `automation_service.engage_feed` takes an `approve_comment` callback and the CLI passes `_review_feed_comment` unless `--yes`; `sanitize_comment` drops empty, overlong, and refusal-shaped model output. The post body is untrusted third-party text fenced inside the prompt — it reaches the model as data, and its output goes out publicly under the user's real name.

## Testing

**Fixtures** (`tests/conftest.py`):
- `isolated_data_dir` (autouse) — sets `LINKEDIN_DATA_DIR` to a per-test directory and resets `cli._app`. Every test, in every file, runs against its own directory; never monkeypatch a path.
- `json_repos` — `create_repos(DataDir(tmp_path)).as_tuple()` in factory order; use for service tests. Stateful services take their file explicitly: `TemplateService(..., templates_file)`, `MarketService(..., postings_file)`, `DataService(data_dir)`.
- `sample_contact`, `sample_company`, `sample_profile` — factory functions (accept `**overrides`). `sample_profile` includes `resume_text` by default.

**Test files:**
- `test_cli.py` — CLI integration tests via Click's `CliRunner`.
- `test_daily_run.py` — `DailyRun`: sections and Markdown, classification, drafts, retries and streaks, without a CLI runner.
- `test_cli_applications.py` — CLI integration tests for `applications`, `interview`, `conversations`, `calendar` command groups.
- `test_ai_client.py` — The AI seam: `ai_call` result contract, fallback on/off, model from env.
- `test_services.py` — Service unit tests for original services.
- `test_application_service.py`, `test_interview_service.py`, `test_conversation_service.py`, `test_calendar_service.py` — Service tests for new features including `AIClientError` paths.
- `test_data_service.py` — Import/export/backup over a `DataDir(tmp_path)`.
- `test_json_store.py`, `test_factory.py`, `test_paths.py` — Storage layer tests: `save_json` atomicity, repos per directory, `DataDir` resolution and backup enumeration, and that importing the CLI creates nothing on disk.
- `test_analytics.py`, `test_market.py`, `test_optimizer.py`, `test_templates.py` — Feature-specific tests.
- `test_automation.py` — Browser config (only fields something reads) and pacing.
- `test_budget.py` — The budget: caps table, per-day persistence, legacy counter names, `limits.json` seeding.
- `test_session.py` — Every verb's preamble over a MagicMock page: budget before navigation, skipped vs failed, dry run, `open()` lifecycle (login handoff, browser closed on raise, Playwright missing).
- `test_contact_import.py`, `test_job_import.py` — Search rows and scraped profiles into contacts; job rows into scored postings.
- `test_post_service.py` — The published-post record and the unmeasurable (URN-less) flag.
- `test_metrics.py` — Metric reads by label (None never 0, SSI discontinued), the session verb, the daily store and deltas.
- `test_growth_prereqs.py` — The resume-repo copy bridge, the profile overlay, and the key probe.
- `test_settings.py` — AI disabled by choice: short-circuit, green run-daily, doctor, hand-written entry points.
- `test_content_engine.py` — Fleet facts (public only, bots split), the fenced prompt, candidates without fallback, review, the skip rule, and the three `posts` commands.
- `test_ranking_service.py` — Scores, reasons, the pin exemption, and the bottom list.
- `test_linkedin_page.py` — Page object against `tests/fake_page.py`; covers selector misses.
- `test_automation_import_safety.py` — Walks `linkedin.automation` asserting no module needs Playwright/keyring to import.
- `test_scheduling.py` — Schedule math and managed-crontab handling.
- `test_resume_service.py` — Resume repo bridge (builds a fake checkout + autoapply SQLite db in tmp_path).
- `test_cli_automate.py` — CLI tests for the `automate` group through `fake_session`, and resume-repo application commands.
- `test_inbox_service.py` — The proposal matcher (URL vs name matching, the low-confidence path, the unreadable-invitation-list case), the review rules, and the thread index. No browser.
- `test_cli_inbox.py` — CLI tests for `inbox sync/list/review/strangers` and `automate jobs`.

**Notes:**
- When adding records via `repo.add()` directly, include an `id` field. When using service methods (e.g. `add_contact()`), id is auto-generated.
- CLI tests that need a profile: invoke `profile setup` with input string `"Name\nHeadline\nRole\nSkills\nExp\nUnique\nIndustry\nLoc\nn\n"`. To include resume text, use `"y\n<resume text>\n\n\n"` for the last 4 tokens (confirm + content + two blank lines to terminate).

## Code Style

- Ruff rules `E`, `F`, `I`, `W`; `E501` ignored (long lines permitted for Rich table formatting).
- Line length: 120. Target: Python 3.10+.
- `src/linkedin/automation/` and `src/linkedin/migrations/versions/` excluded from lint.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push and PR: ruff check → pytest → CLI smoke test across Python 3.10, 3.11, 3.12.
