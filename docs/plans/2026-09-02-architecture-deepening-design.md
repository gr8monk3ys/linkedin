# Architecture deepening: decisions (2026-09-02)

Nine candidates from the architecture review, grilled and settled. Vocabulary in
`CONTEXT.md`. Nothing here is built yet. Build order at the end.

## 1. AI call returns a result
- `generate_with_ai` stays as the raw raising function (tests keep patching it).
- New wrapper `ai_call(prompt, *, max_tokens, fallback=None) -> AIResult(text, error, was_fallback)`.
  Owns `LINKEDIN_AI_FALLBACK_ENABLED`. Model from `LINKEDIN_AI_MODEL` (check the
  current model reference before choosing the default).
- All 21 call sites migrate; `research_service` stops raising to the CLI;
  feed-comment checks `result.error` and skips.
- `DraftDict.source: "ai" | "template"`; a row with no source reads as unknown.
  Unknown and template are both refused by the post action.
- `run-daily` does not save template drafts; counts them as failed; run status nonzero.
- Delete `last_draft_was_fallback` / `last_draft_error` and `_warn_if_fallback`;
  the CLI warns from the value at all eight sites.

## 2. Planner rows
- New `planner` module: `ACTIONS` keyed by action name (label, command, draft spec
  or None), both status-rule tables, both coverage checks.
- Draft spec is data (type, generator, context). `DraftService.generate_for_action(action)`.
  The branch in `_generate_action_drafts` is deleted.
- Mapping: `send_connection` -> connection; `follow_up_messaged` -> follow-up attempt 1;
  `call_follow_up`, `repair_contact` -> None; others as today.
- Applications get the same row shape with `draft=None`.
- Date-driven action names become constants; a test walks every date branch and
  asserts each emitted action is in `ACTIONS`.

## 5. Data dir
- `DataDir(root)` value object: one property per file; from `LINKEDIN_DATA_DIR`.
- Repos take their file at construction. Delete the nine ABCs.
- All orphans under it: job postings, templates, run state/lock/log, inbox proposals,
  automation usage, `li_session.json`, recaps, cron logs, `limits.json`, posts, thread index.
  Backup enumerates the directory.
- `App(data_dir)` holds every repo and service; module-level `_app` bound by the group
  callback, rebound by one test fixture. Click log-path defaults computed at invocation.

## 3 + 8. Session and budget
- `LinkedInSession.open(app, headless, dry_run)` context manager with named verbs:
  connect, message, post, react, comment, inbox, jobs, scrape, search, sync_profile, easy_apply.
  Each: budget -> pace -> navigate -> page verb -> record on success.
- One `ActionResult(status, reason, data)`, status `ok | skipped | refused | failed`.
- Dry run: navigates and reads, never writes, never spends.
- `Budget(caps, usage_file)` with `spend(kind, n)` / `remaining(kind)`; caps in
  `limits.json` seeded with the ramp defaults (1 post/week, 5 reactions/day, 0 connections
  for the first 30 days); `automate limits set <kind> <n>`. No "no budget".
- Delete: the 11 action files (login ordering and the usable-page rule move into the
  session; scrape import -> contact module; job import -> market module), the three
  legacy `automation search/import-search/profile` commands, `_require_automation`,
  dead `AutomationConfig` fields; delays declared once.
- Test seam: patch `LinkedInSession.open` to return a fake session with scripted results.

## 6 + 7. Write results and the second adapter
- Page writes return `WriteResult(outcome, detail)`; `create_post` refuses the fallback
  editor (`selector_missing`), returns the URN in `detail`, `degraded` if the URN
  cannot be read; all write selectors join `FRAGILE_SELECTORS`; login records misses.
- New `posts` store (URN, text, posted_at, draft id, calendar id).
- The second adapter is the fake session (above); `FakePage` stays for page-object tests.

## 9. Inbox
- `InboxService.apply_proposals(proposals, contacts, *, confirm) -> Applied` with the
  stale-drop, missing-drop, and confidence gate inside; CLI keeps the prompt.
- Thread index persisted on every sync (no bodies); pure
  `inbound_from_strangers(threads, contacts, since)`.

## 4. Daily run
- `DailyRun(app, RunConfig).execute(trigger) -> RunResult`; `run_state` private.
- One `diagnostics()`; one `doctor` command; `health` deleted. CI's smoke step
  (`ci.yml:130`, `linkedin-cli health --json --time 09:00`) is updated to `doctor` in the
  same change.
- `DailyPlan` = ordered sections; Rich and Markdown renderers iterate it.

## Build order
1 -> 2 -> 5 -> 3+8 -> 6+7 -> 9 -> 4. Each step is its own PR, verified by running
the command it changes, never by tests alone.
