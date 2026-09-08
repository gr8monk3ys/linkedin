# 0001. A feature needs a user who runs it

Date: 2026-09-03
Status: accepted

## Context

A February 2026 review of this repo found "gaps" and filled them: interview
prep, profile optimizer, content research, contact discovery, market
intelligence, A/B templates, a content calendar, outreach campaigns and
per-contact conversation logs. Seven new JSON stores, nine command groups,
about sixty commands, some 2,500 lines of source and 1,800 of tests.

Seven months later the tool had been run daily and none of it had been used:
two template rows, two calendar rows, nothing else. All nine groups depended
on model calls that are now off by choice (`settings ai off`; drafts are
written by hand). The CLI was a 4,144-line file and 72% of its uncovered
lines sat in those groups. Meanwhile the thing the tool exists for, inbound
interest and interviews, had not moved.

## Decision

The nine groups and their services, repos, types and tests are deleted.
Job postings survive as `postings` because `automate jobs` and the daily
plan feed on them. The calendar repo survives because approved posts are
scheduled in it; the calendar *service* does not.

A feature is added to this repo only when the user has a concrete routine
that runs it, and it is removed when a month of run logs shows it unused.
"It would be nice to have" is not a routine.

## Consequences

- The command surface is the CRM, drafts, applications, postings, posts,
  inbox, metrics, the daily run, the browser layer and its scheduling.
- The README lists commands by the routine they belong to (first day, every
  morning, every Sunday), not by feature.
- Any future review that finds "gaps" must name the routine that would fill
  them before adding code.
