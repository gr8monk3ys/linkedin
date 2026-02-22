# Feature Additions Design

**Date:** 2026-02-22
**Approach:** CLI-only (Approach A), parallel agent execution
**Scope:** All identified gaps from brutally-honest codebase review

---

## 1. Data Model

Seven new JSON-backed data entities added to `~/.linkedin-cli/`.

### New TypedDicts (`src/linkedin/types.py`)

```python
ApplicationDict       # Job application lifecycle tracking
ApplicationEventDict  # Embedded status-change history log
ConversationDict      # Contact message thread
MessageDict           # Individual message within a conversation
ContentPostDict       # Scheduled/published content calendar entry
InterviewPrepDict     # Interview prep package per application
```

### New JSON store files
| File | Entity |
|------|--------|
| `applications.json` | `ApplicationDict` + embedded `ApplicationEventDict[]` |
| `conversations.json` | `ConversationDict` |
| `content_calendar.json` | `ContentPostDict` |
| `interview_prep.json` | `InterviewPrepDict` |

### Profile extension
`ProfileDict` gains `resume_text: str` field (loaded from `--resume-file` flag or set directly in `profile setup`).

### Application pipeline
```
saved → applied → phone_screen → technical → onsite → offer_received → accepted / rejected / ghosted
```

---

## 2. New Services

### `ApplicationService` (`src/linkedin/services/application_service.py`)
- CRUD for applications
- `advance(id, new_status, notes)` — append event to history, update status
- `tailor_resume(id)` → AI: rewrite resume bullets for this JD
- `cover_letter(id)` → AI: full cover letter
- `skills_gap(id)` → AI: structured "you have X/Y required skills, missing: ..."
- `get_stats()` → funnel metrics (applied→offer rate, avg days per stage)

### `InterviewService` (`src/linkedin/services/interview_service.py`)
- `prep(application_id)` → AI: role-specific questions + model STAR answers
- `research(application_id)` → AI: company briefing (funding, news, tech stack, culture)
- `star(application_id)` → AI: STAR method scaffolds for top behavioral questions
- `questions_to_ask(application_id)` → AI: "what to ask them" list
- `get_prep(application_id)` → retrieve stored prep

### `ConversationService` (`src/linkedin/services/conversation_service.py`)
- `log(contact_id, sender, text, timestamp?)` → append message to thread
- `get_thread(contact_id)` → ordered message list
- `export(contact_id)` → plain text dump

### `ContentCalendarService` (`src/linkedin/services/calendar_service.py`)
- CRUD for content calendar entries
- `add(title, scheduled_date, draft_id?, platform?)`
- `list_upcoming(days)` / `list_all()`
- `mark_posted(id, posted_date?)`
- `get_stats()` → cadence, gap since last post, scheduled count

### Playwright automation extensions (`src/linkedin/automation/actions/scrape.py`)
- `search_people(query, limit)` → list of raw profile dicts from LinkedIn search
- `import_search(query, limit)` → call search, map to `ContactDict`, add to repo
- `scrape_profile(url)` → single profile → `ContactDict`

---

## 3. CLI Command Groups

### `linkedin-cli applications`
```
applications add --title STR --company STR [--url] [--jd FILE|STR] [--notes]
applications list [--status STATUS] [--company STR]
applications view ID
applications advance ID --status STATUS [--notes STR]
applications tailor-resume ID [--resume-file PATH]
applications cover-letter ID
applications skills-gap ID
applications stats
```

### `linkedin-cli interview`
```
interview prep ID           # Generate questions + model answers, save to interview_prep.json
interview research ID       # Company briefing
interview star ID           # STAR method scaffolds
interview questions ID      # What to ask them
interview view ID           # Show all saved prep for application ID
```

### `linkedin-cli conversations`
```
conversations log CONTACT_ID --from [me|them] --text STR [--at TIMESTAMP]
conversations view CONTACT_ID
conversations export CONTACT_ID
```

### `linkedin-cli calendar`
```
calendar add --title STR --date DATE [--draft-id INT] [--platform linkedin]
calendar list [--week] [--month]
calendar mark-posted ID [--date DATE]
calendar stats
```

### `linkedin-cli automate` (new sub-commands, extend existing group)
```
automate search --query STR --limit INT          # Print results table
automate import-search --query STR --limit INT   # Import to CRM
automate profile URL                             # Scrape single profile → CRM
```

### `linkedin-cli profile` extension
```
profile setup  # Gains --resume-file PATH flag and resume_text prompt field
```

---

## 4. Repository Layer

New abstract repos in `repository.py`:
- `ApplicationRepo` — `add/get/list_all/update/delete`
- `ConversationRepo` — `get_by_contact/upsert`
- `CalendarRepo` — `add/get/list_all/update/delete`
- `InterviewPrepRepo` — `get_by_application/upsert`

New JSON implementations in `json_store.py`.

`create_repos()` in `factory.py` returns extended tuple.

---

## 5. Testing

| Test file | Covers |
|-----------|--------|
| `tests/test_applications.py` | ApplicationService CRUD, pipeline, stats |
| `tests/test_interview.py` | InterviewService with mocked `generate_with_ai` |
| `tests/test_conversations.py` | ConversationService CRUD, thread ordering |
| `tests/test_calendar.py` | ContentCalendarService CRUD, stats |
| `tests/test_cli_applications.py` | Click integration via CliRunner |
| `tests/test_cli_interview.py` | Click integration for interview group |
| `tests/test_automation_scrape.py` | Scraping logic with mocked BrowserManager |

AI calls mocked via `monkeypatch` on `linkedin.services.<module>.generate_with_ai`.
Playwright tests mock `BrowserManager` — no real browser required.

---

## 6. Parallel Agent Breakdown

Seven independent work streams, safe to execute in parallel:

| Agent | Responsibility |
|-------|---------------|
| Agent 1 | Types + repos + JSON store + factory wiring |
| Agent 2 | ApplicationService + tests/test_applications.py |
| Agent 3 | InterviewService + tests/test_interview.py |
| Agent 4 | ConversationService + CalendarService + their tests |
| Agent 5 | CLI command groups (applications, interview, conversations, calendar) + CLI tests |
| Agent 6 | Playwright scraping (scrape.py) + automation tests |
| Agent 7 | Profile resume_text extension + profile CLI + README update |

Agent 1 must complete before Agents 2-7 begin (shared foundation).
