# Inbound signals, job posting feed, and application planning

Date: 2026-08-30
Status: approved

## The problem

The repo has nineteen services and ten automation actions. Five data files have
ever been written; `automation_usage.json` does not exist, which means the
Playwright stack has never run against LinkedIn once.

Measured on 2026-08-30:

| Store | Rows |
|---|---|
| contacts | 11 (9 real, 1 junk, 1 test) |
| applications | 20, all `applied` |
| drafts | 2 |
| templates | 2 |
| conversations / calendar / interview prep / research / postings | never created |

The daily plan for 2026-08-30 contained one action, for contact id 2 — a record
named `New` with no company — and the lines `No postings above threshold` and
`No template performance data yet`.

Three distinct causes, none of them "a missing feature":

1. **No inbound edge.** Every automation action is outbound: connect, message,
   post, engage, easy-apply. Nothing reads replies, accepted invitations, or
   notifications. A contact is frozen at whatever status it was given on the day
   it was created; `connection_sent` can only become `connected` if a human
   types it.
2. **No posting source.** `market_service` has import and skill-match scoring
   and no way to get a posting in, so the opportunities section is empty by
   construction.
3. **Applications are unplanned.** `contact_service.get_next_actions` walks
   contacts only. All twenty applications are invisible to the planner however
   long they sit.

### Two claims from the initial analysis that did not survive checking

- Applications were *not* malformed. `title`, `url` and `history` are all
  populated on all twenty; the first pass queried a `role` key that does not
  exist. The applications problem is planning, not data.
- The nine real contacts are *not* overdue. `STATUS_RULES["connection_sent"]`
  has `after_days: 14` and they were three days old. The planner was correct to
  stay quiet about them.

## Design

### 1. Inbound signals

The load-bearing decision: **browser reading and proposal logic are separate
units.** The action module navigates and returns raw dicts. A pure service turns
dicts into proposals. The logic that can corrupt the CRM is therefore testable
with no browser.

Nothing auto-advances. Reading a page wrong must not be able to silently
rewrite nine real contacts, and the repo already has this shape: AI feed
comments go through an `approve_comment` callback before publication.

**`linkedin_page.py`** gains navigation to `/messaging/` and
`/mynetwork/invitation-manager/sent/`, plus two readers:

- `get_message_threads(limit)` → `{name, url, snippet, timestamp, unread, last_from_them}`
- `get_pending_sent_invitations()` → `{name, url}`

Both record a selector miss when they match nothing, so a markup change reports
itself instead of looking like an empty inbox.

**`automation/actions/inbox.py`** — rate-limit, navigate, return. No repo writes.

**`services/inbox_service.py`** — pure, dict in, dict out:

- Latest message in a thread is from them and newer than the contact's
  `last_contact` → propose `→ responded`.
- Contact in `connection_sent` no longer present in the pending-sent set →
  propose `→ connected`.

Contacts are matched on `linkedin_url` first, compared with the query string
stripped. A name-only match is recorded `low_confidence` and is never applied
without confirmation, in this or any later change.

Proposals persist to `~/.linkedin-cli/inbox_proposals.json`
(`json_store.INBOX_PROPOSALS_FILE`).

**CLI:** `inbox sync` writes proposals, `inbox list` shows them, `inbox review`
applies or skips them one at a time.

### 2. Job posting feed

`get_job_results()` → `{title, company, location, url, posted, easy_apply}`,
imported through the existing `market_service.add_posting`, which already scores
a posting against the profile. Exposed as
`automate jobs --query ... --location ... --limit N`.

### 3. Applications in the planner

`APPLICATION_STATUS_RULES` in `application_service.py`, built the way
`STATUS_RULES` is: one row per status carrying `after_days`, `priority`,
`action` and `reason`, with a coverage check against `APPLICATION_STATUSES` so a
status with no rule cannot ship. `applied` becomes due after ten days.

Application actions occupy their own key in the daily plan data, not the
existing `actions` list. `_daily_run_status` classifies a run by whether
`actions` is empty while contacts are stalled — that guard exists because the
job once logged 136 consecutive green runs while generating zero drafts.
Merging application rows into `actions` would let them mask the very failure the
guard was added to catch.

### 4. Supervised live run

Run `inbox sync` and `automate jobs` against the real account, then report
`selector_health()`.

Both new features are read-only: no connection request, no message, no post. The
first real execution of this automation stack cannot write anything to LinkedIn.

## Risk

LinkedIn's messaging pane is virtualized and lazy-loaded, and is the selector
most likely to need a second pass after the live run. The `_record_miss`
plumbing means it will say so rather than reporting a quiet inbox. Expect step 4
to send step 1 back for revision at least once.

## Testing

- `fake_page.py` registrations for every new selector, including the
  unregistered-empty case, which is what a markup change looks like.
- Pure-function tests for the proposal matcher, covering the URL match, the
  name-only `low_confidence` path, and a thread whose last message is the user's
  own.
- Application rules table tests, including the coverage check.
- CLI tests patching `_require_automation`.

## Files

New: `automation/actions/inbox.py`, `automation/actions/jobs.py`,
`services/inbox_service.py`, `tests/test_inbox_service.py`,
`tests/test_automation_inbox_jobs.py`.

Edited: `automation/selectors.py`, `automation/linkedin_page.py`,
`services/application_service.py`, `data/json_store.py`, `cli.py`,
`tests/test_linkedin_page.py`, `tests/test_application_service.py`, `CLAUDE.md`.

## Order

1 → 3 → 2 → 4. Inbox first because it is the substance; applications next
because it is pure logic needing no browser; jobs; then the live run, when there
is something worth watching.
