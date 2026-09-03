# LinkedIn growth: design decisions (2026-09-02)

Outcome of a grilling session. Every line below is a decision, not a plan.
Nothing here has been built. Do not treat this file as scope approval.

## Goal

**3 inbound messages per month from strangers** (not replies to our outreach)
by **2026-12-01**. Followers are the leading indicator only.

Why this number: it is the one metric the tool cannot inflate itself. Reach
can be bought with hashtags, followers with connection blasts. A recruiter
writing unprompted cannot be faked.

## Audience

- **Profile** speaks to hiring managers for full-time solutions / ML
  engineering roles. Upwork is the bridge, not the target.
- **Posts** are written for peer engineers, because peers are who reshare and
  comment, and that engagement is what surfaces a post to the hiring manager.

## Content

**Building in public from fleet data.** Source material is the orchestrator's
run logs, PR counts, merge-gate decisions, CI watchdog output.

- **Public repos only.** Private repo names and client-adjacent work never
  reach a model prompt whose output is published under the user's name.
  Every claim in a post must be verifiable by a reader who clicks through.
- AI "thought leadership" on trending topics was considered and rejected: it
  is the commodity option, and the fleet already measured it on Letterboxd
  (34 AI reviews, zero engagement).

## Loop

- **Draft-and-approve.** Fully autonomous publishing was rejected.
- **Weekly batch approval, Sunday.** One post a week means one approval a
  week. The daily launchd run has nobody at the terminal, so a draft that
  waits for a keypress waits forever.
- **A skipped approval means no post.** Never a fallback post.
- The approval view shows the draft **plus** follower delta, impressions on
  the last three posts, and inbound count. Without numbers approval is
  rubber-stamping.
- **Skip-by-default** when the last three posts underperform the baseline.
  This is the rule that stops the tool posting into silence indefinitely.

## Ramp (account protection)

The account is the user's real professional identity. A restriction is
unacceptable. LinkedIn detects *change* in behaviour, not absolute volume,
and this account has zero automated history.

First 30 days: **one post a week, five reactions a day, zero automated
connections.** Step up only if metrics are clean. The current safety caps
(20 connections / 25 messages / 3 posts / 30 reactions per day) are the
ceiling, not the starting point.

Reactions go to a **hand-curated list of ~25 accounts** (people at target
companies, peers in the stack), stored as a plain list in the CLI data dir,
reviewed monthly. Keyword-driven feed picking was rejected.

## Metrics (must ship first)

Nothing account-level is measured today. No followers, profile views,
impressions, or received engagement are scraped or stored. Post publishing
captures no post ID, so a published post cannot be matched to its stats.

Version one, daily, read-only, via the existing Playwright session:
followers, connections, profile views, search appearances, per-post
impressions and reactions on own recent posts, Social Selling Index, and
inbound-message count (free, from `inbox sync`).

**Run the scraper alone for 14 days before the first post** so the first
post has a baseline. Without it the skip-by-default rule never fires.

## Prerequisites before the first post

1. **Fix the AI key** in `~/.linkedin-cli/cron.env`. It is invalid; 150 runs
   produced two drafts, both offline templates.
2. **The post action refuses to publish** anything `DraftService` flags as a
   fallback. Hard condition, not a warning.
3. **Headline single source.** `~/.linkedin-cli/my_profile.json` holds a
   stale March headline ("ML and Backend Engineer"); the curated one lives in
   `~/code/resume/docs/linkedin-copy.md`. Profile sync would overwrite the
   curated one with the stale one. The CLI reads headline/about through the
   existing resume bridge; the headline field is removed from the CLI file.
4. **One-time manual profile pass** (user, ~1 hour): add the 7 catalog
   projects not on LinkedIn, rebuild Featured. The tool produces the
   paste-ready copy. Posting into a half-finished profile wastes every
   impression the posts earn.

## Status 2026-09-02 (end of day)

- API key: **both dead** (cron.env returns 401, shell unset). `automation doctor --probe-ai` now proves it. The user must set one: `linkedin-cli automation env set-anthropic-key`.
- Headline single source: done (resume repo doc overlays the profile).
- Metrics scraper: done and verified live — 2,498 followers, 2,506 connections, 46 profile views, 70 search appearances, 0 post impressions. **SSI is discontinued for this account**; the plan's SSI metric is dropped.
- Baseline: `automation schedule` now installs `run-daily --collect-metrics`; reinstall the schedule to start the 14 days.

## Kill criteria

If by **2026-12-01** inbound is under 3/month **and** follower growth is
under 20%, **freeze the posting engine** and keep only metrics and inbox
sync, the way the media fleet froze its review engines. Decided now, before
sunk cost can argue against it.

## Build order (implied, not yet approved)

1. AI key + fallback refusal in post action
2. Headline single-source via resume bridge
3. Metrics scraper + time series + dashboard section
4. 14-day baseline (nothing else runs)
5. Reaction target list + daily reactions at 5/day
6. Fleet-data drafter (public repos only) + Sunday batch approval
7. First post
