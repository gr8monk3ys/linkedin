# LinkedIn Job Hunt Assistant

A local command-line CRM for a LinkedIn job search, with a daily plan, a
review-gated content pipeline, an inbox reader that proposes pipeline moves
instead of making them, and a browser layer that does the sending.

Storage is JSON files under `~/.linkedin-cli`. Nothing leaves the machine
except what you tell the browser to post or send.

> The `automate` commands drive a real browser against your own LinkedIn
> account, which LinkedIn's User Agreement forbids and can get an account
> restricted. Every write is budgeted (`automate limits`), paced, and
> confirmed. A dry run navigates and reads, never writes.

## What it does

- **Contacts and companies.** Who you are trying to reach, what stage they
  are at, and when they are due. Every active contact always carries a
  follow-up date; the planner turns those into the day's actions.
- **Ranking.** Contacts are scored 0–100 against your target role so the
  day's scarce invitations go to the people who matter. Pinned contacts are
  always first.
- **Drafts.** Connection requests, messages, follow-ups and thank-yous,
  written by the model or by hand (`drafts add`). A template is never passed
  off as a draft.
- **Applications.** Lifecycle tracking with its own planner rules, linked to
  resume variants in the resume repo and to autoapply's submission log.
- **Posts.** Candidates come from what your public repos actually shipped
  this week (`posts facts`), are reviewed before they are scheduled, and are
  published on a cadence with a skip rule when the last three flopped.
- **Inbox.** `inbox sync` reads replies and accepted invitations and writes
  *proposals*; `inbox review` applies them one at a time. Nothing inbound
  advances a contact on its own.
- **Metrics.** Followers, connections, profile views, impressions and search
  appearances, one row per day, read from LinkedIn by label. A missing value
  is `None`, never `0`.
- **The daily run.** `run-daily` builds the plan, drafts for it, records the
  run, and exits nonzero when a contact was due and nothing happened.

## Install

```bash
uv sync                      # the CLI
uv sync --extra automation   # plus Playwright and keyring for the browser layer
uv sync --extra dev          # pytest, ruff, coverage
uv run playwright install chromium
```

Both `linkedin` and `linkedin-cli` run the same entry point.

## First day

```bash
uv run linkedin profile setup
uv run linkedin companies add
uv run linkedin contacts add --company-id 1
uv run linkedin contacts rank
uv run linkedin daily-plan
```

Optional: `settings ai off` if you write drafts yourself. `run-daily` stays
green, drafting is skipped, and hand-written text enters the same pipeline
through `drafts add` and `posts add-candidate`.

## Every morning

```bash
uv run linkedin run-daily --save-recap --collect-metrics
uv run linkedin contacts due
uv run linkedin automate connect <id>        # one budgeted invitation
uv run linkedin automate message <id> --draft-id <n>
uv run linkedin inbox sync && uv run linkedin inbox review
```

`automation schedule --time 09:00` installs the daily run under cron (or a
LaunchAgent on macOS); `automation doctor` tells you why a run did not fire.

## Every Sunday

```bash
uv run linkedin posts facts            # what the public fleet did this week
uv run linkedin posts draft-week       # model writes candidates (or posts add-candidate by hand)
uv run linkedin posts review           # approve schedules the next Tuesday
uv run linkedin posts publish-due      # or let run-daily do it
```

## Commands

| Group | What it holds |
|---|---|
| `contacts` | add, list, view, update, due, next-actions, rank, pin, dedupe, merge, repair |
| `companies` | add, list, view, update, contacts |
| `drafts` | connection, message, follow-up, intro-request, thank-you, batch-connections, add, list, view |
| `applications` | add, advance, list, view, stats, suggest-resume, attach-resume, import-autoapply, tailor-resume, cover-letter, skills-gap |
| `postings` | add, import, list — scored against your profile; `automate jobs` fills this |
| `posts` | facts, draft-week, add-candidate, review, publish-due, list |
| `inbox` | sync, list, review, strangers |
| `metrics` | collect, show |
| `automate` | login, setup, limits, search, import-search, profile, connect, message, post, engage, jobs, easy-apply, sync-profile |
| `automation` | status, doctor, schedule, unschedule, env |
| `data` | export, import, backup, backups, restore, verify-backup |
| `analytics` | summary, conversion, velocity |
| `settings` | show, ai |
| top level | `dashboard`, `daily-plan`, `run-daily`, `run-history` |

`--help` on any group lists its commands with their options.

## Configuration

| Variable | Purpose |
|---|---|
| `LINKEDIN_DATA_DIR` | Data directory (default `~/.linkedin-cli`) |
| `ANTHROPIC_API_KEY` | Model access; scheduled runs read it from `~/.linkedin-cli/cron.env` |
| `LINKEDIN_AI_MODEL` | Model id for drafts and posts |
| `LINKEDIN_AI_FALLBACK_ENABLED` | Offline templates when the model is unreachable (`drafts` only, never `run-daily`) |
| `LINKEDIN_RESUME_REPO` | Path to the resume repo checkout (default `~/code/resume`) |

Daily browser caps live in `limits.json` and are stepped up with
`automate limits set <kind> <n>`.

## Development

```bash
uv run pytest
uv run pytest --cov=linkedin --cov-report=term-missing
uv run ruff check src/ tests/ && uv run ruff format src/ tests/
```

`CLAUDE.md` documents the architecture and the invariants that have bitten
before. `CONTEXT.md` is the glossary.
