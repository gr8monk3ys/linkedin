# CONTEXT.md — domain vocabulary

Terms as this codebase uses them. Use these words in code, tests, and docs.

- **Contact**: a person in the CRM with a pipeline status
  (`not_contacted → connection_sent → connected → messaged → responded → call_scheduled → hired/rejected`).
- **Application**: a job application with its own status lifecycle, planned separately from contacts.
- **Action**: what the planner says to do next for one contact or application. At most one per contact.
  Defined by a **status rule** row: cadence, action name, label, command, draft strategy.
- **Draft**: text the model produced for a specific contact, from the profile and the contact.
  Has a **source**: `ai` or `template`. A row with no source is `unknown`.
- **Template**: the offline fallback text used when the model is unavailable. Not a draft.
  Never published unattended; never passed off as a draft.
- **AI result**: the value every model call returns: `text`, `error`, `was_fallback`.
  There is one error protocol; services do not raise `AIClientError` to the CLI.
- **Proposal**: a *proposed* pipeline transition derived from inbound signals (messages, invitations).
  Applied one at a time by a human; a hand edit since the sync wins.
- **Run**: one execution of `run-daily`. Has a status: `success`, `no_actions`, `failed`.
  A run that generates only templates is `failed`.
- **Planner**: the module holding `ACTIONS` (one row per action name: label, command, draft spec),
  both status-rule tables, and the coverage checks. Every action a rule or a date branch can emit
  has a row; a half-added action fails at import or in the date-branch test.
- **Session**: one open browser logged into LinkedIn. Exposes named verbs (`connect`, `message`,
  `post`, `react`, `comment`, `inbox`, `jobs`, `scrape`, `search`, `sync_profile`, `easy_apply`),
  owns budget, pacing, dry run, and the selector-health report on close. The test double is a
  fake session, not a fake page.
- **Action result**: what every session verb returns: `status` in `ok | skipped | refused | failed`,
  `reason`, `data`. `refused` is a rule saying no (budget, template draft); `skipped` is a normal
  absence; `failed` is a raise or a selector miss.
- **Dry run**: the session navigates and reads, never writes, never spends budget.
- **Budget**: daily caps per action kind, in `limits.json` under the data dir. `spend(kind, n)`
  and `remaining(kind)`. There is no "no budget".
- **Data dir**: the one root every file lives under (`LINKEDIN_DATA_DIR`, default `~/.linkedin-cli`).
  Repos take their file at construction. Backups enumerate the directory.
- **Write result**: what a page-object write returns: `outcome` in `ok | not_applicable |
  selector_missing | degraded`, plus `detail` (the post URN for `create_post`). A write into an
  editor we do not recognise is `selector_missing`, never a quiet success.
- **Post**: a published LinkedIn post: URN, text, posted-at, source draft, source calendar entry.
  The join key for per-post metrics. A calendar entry is a schedule row that points at a post.
- **Thread index**: the per-sync record of message threads: sender, thread URL, last-message time,
  whether the last message is ours, first seen. No bodies. Source of "inbound from strangers".
- **Daily run**: `DailyRun(app, config).execute(trigger) -> RunResult`. Owns lock, idempotency,
  retry, streak, recovery, and status classification. `run_state` is its private implementation.
- **Daily plan**: an ordered list of sections rendered by two renderers (terminal, Markdown recap).
- **Diagnostics**: one check list, one naming, one `doctor` command.
- **Rank**: a contact's 0–100 score for the target role, with reasons. Decides who gets the day's
  invitations. **Pinned** contacts are exempt: always first, never in the bottom list, always followed.
- **Metric row**: one day's account numbers (followers, connections, profile views, post impressions,
  search appearances, SSI). A number that could not be read is None, never 0.
- **Fleet facts**: a week of public GitHub activity (merged PRs, pushed repos), the only thing the
  post drafter may see. **Candidate**: an AI draft of type `post_fleet` awaiting review.
  **Skip rule**: publishing stops by default when the last three measured posts all underperform
  the earlier median.
