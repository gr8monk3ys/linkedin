# LinkedIn Job Hunt Assistant

A local CRM + AI-powered tool to accelerate your job search on LinkedIn.

## What It Does

A personal productivity tool with an optional browser-automation layer:

1. **Companies** - Track target companies for networking
2. **CRM** - Track people you want to connect with, their status, follow-ups
3. **AI Drafts** - Generate personalized connection requests, messages, intro requests, and more
4. **Discovery** - AI-powered suggestions for who to connect with
5. **Content Research** - Get post ideas, engagement strategies, and draft posts
6. **Applications** - Track job applications, linked to resume variants from your resume repo
7. **Browser Automation** (optional) - Drive your own LinkedIn session: search, connect, message, post, like, sync your profile, Easy Apply
8. **Data Management** - Import, export, and backup your data

> ⚠️ The `automate` commands drive a real browser against your own LinkedIn
> account. Browser automation violates LinkedIn's User Agreement and can get
> an account restricted. Conservative daily limits, human-like delays, and
> confirmation prompts are built in, but use it deliberately and at your own
> risk. Everything else in this tool is plain local CRM + AI drafting.

## Quick Start

```bash
cd linkedin
uv sync

# 1. Set up your profile (used for personalization)
uv run linkedin-cli profile setup

# 2. Add target companies
uv run linkedin-cli companies add

# 3. Add contacts to track
uv run linkedin-cli contacts add --company-id 1

# 4. Generate personalized outreach
uv run linkedin-cli drafts connection 1

# 5. Get AI suggestions for more contacts
uv run linkedin-cli discover contacts --company "LangChain"

# 6. View your dashboard
uv run linkedin-cli dashboard
```

## Commands

### Profile (Your Info)
```bash
linkedin-cli profile setup                              # Set up your info for AI personalization
linkedin-cli profile setup --resume-file resume.txt    # Load resume from file (for AI tailoring)
linkedin-cli profile show                              # View your saved profile
```

### Companies (Track Target Companies)
```bash
linkedin-cli companies add                      # Add a new target company
linkedin-cli companies list                     # List all companies
linkedin-cli companies list --priority high     # Filter by priority
linkedin-cli companies view 1                   # View company details
linkedin-cli companies update 1 --priority high # Update company
linkedin-cli companies update 1 --add-role "Engineering Manager"  # Add role to find
linkedin-cli companies contacts 1               # List contacts at a company
linkedin-cli companies delete 1                 # Delete a company
```

### Contacts CRM
```bash
linkedin-cli contacts add                       # Add a new contact
linkedin-cli contacts add --company-id 1        # Add contact linked to company
linkedin-cli contacts list                      # List all contacts
linkedin-cli contacts list --status connected   # Filter by status
linkedin-cli contacts list --company-id 1       # Filter by company
linkedin-cli contacts view 1                    # View contact details
linkedin-cli contacts update 1 --status connected  # Update status
linkedin-cli contacts update 1 --status responded  # Auto-credits latest relevant template outcome
linkedin-cli contacts update 1 --email "x@y.com"   # Add email
linkedin-cli contacts link-company 1 2          # Link contact to company
linkedin-cli contacts activity 1                # View activity log
linkedin-cli contacts due                       # Show overdue follow-ups
linkedin-cli contacts due --days 7              # Show follow-ups due within 7 days
linkedin-cli contacts next-actions              # Prioritized outreach to-dos
linkedin-cli contacts next-actions --generate-drafts --save-drafts  # Auto-generate actionable drafts
linkedin-cli contacts remind 1 --days 7         # Set follow-up reminder
linkedin-cli contacts dedupe                    # Find likely duplicates with confidence scores
linkedin-cli contacts merge 1 2                 # Merge duplicate contact #2 into #1
linkedin-cli contacts stats                     # View pipeline stats
```

### Campaign Sequences
```bash
linkedin-cli campaigns enroll 1 --name networking_21d   # Start a 21-day outreach sequence
linkedin-cli campaigns status 1                          # Show one contact's campaign progress
linkedin-cli campaigns status --active-only              # List all active campaign enrollments
linkedin-cli campaigns due                               # Show due campaign steps + suggested commands
linkedin-cli campaigns advance 1                         # Mark current campaign step complete
linkedin-cli campaigns advance 1 --complete              # Mark sequence complete now
```

### AI Drafts
```bash
linkedin-cli drafts connection 1    # Generate connection request
linkedin-cli drafts message 1       # Generate follow-up message
linkedin-cli drafts intro-request 1 --to 2  # Ask contact 1 to intro you to contact 2
linkedin-cli drafts thank-you 1     # Generate thank you note after call
linkedin-cli drafts follow-up 1     # Generate follow-up after no response
linkedin-cli drafts follow-up 1 --attempt 2  # Second follow-up attempt
linkedin-cli drafts batch-connections --limit 5  # Generate drafts for all not_contacted
linkedin-cli drafts list            # List saved drafts
linkedin-cli drafts view 1          # View a draft
```

### Templates & Experiments
```bash
linkedin-cli templates save --name "Conn A" --type connection --content "Hi {{name}}" --variant A
linkedin-cli templates use 1 1                  # Render template 1 for contact 1 (tracks usage)
linkedin-cli templates record-response 1         # Record a response for template 1
linkedin-cli templates suggest-best --type connection  # Best-performing template by type
linkedin-cli templates ab-results                # A/B comparison for variants
linkedin-cli templates dashboard                 # Experiment summary by template type
# Positive contact status updates auto-credit matching templates:
# connected -> connection templates, responded/call_scheduled/hired -> message/follow_up
```

### Discovery (AI-Powered Suggestions)
```bash
linkedin-cli discover contacts --company "LangChain"  # Who to find at a company
linkedin-cli discover contacts --role "Engineering Manager"  # Who to find by role
linkedin-cli discover companies     # Suggest companies based on your profile
```

### Content Research
```bash
linkedin-cli research engagement    # Show engagement strategies
linkedin-cli research ideas         # Generate post ideas
linkedin-cli research draft-post "topic" --style story  # Write a post
linkedin-cli research hashtags "AI" # Get hashtag suggestions
```

### Market Intelligence
```bash
linkedin-cli market analyze --role "ML Engineer" --industry "SaaS"
linkedin-cli market salary --role "ML Engineer" --location "San Francisco, CA"
linkedin-cli market trends --industry "AI"
linkedin-cli market add-posting --title "Senior ML Engineer" --company "Acme" --skills "Python, ML"
linkedin-cli market import-postings jobs.csv --merge
linkedin-cli market postings --min-score 40
```

### Job Applications
```bash
linkedin-cli applications add --company "Acme" --title "ML Engineer" --url "https://..." --jd "Job description"
linkedin-cli applications list [--status phone_screen] [--company "Acme"]
linkedin-cli applications view 1
linkedin-cli applications advance 1 --status applied --notes "Submitted via website"
linkedin-cli applications tailor-resume 1 [--resume-file resume.txt]
linkedin-cli applications cover-letter 1
linkedin-cli applications skills-gap 1
linkedin-cli applications stats
```

### Interview Prep
```bash
linkedin-cli interview prep 1          # Generate questions + STAR answers (saved for later)
linkedin-cli interview research 1      # Company briefing: funding, culture, tech stack
linkedin-cli interview star 1          # STAR method answer scaffolds
linkedin-cli interview questions 1     # Smart questions to ask the interviewer
linkedin-cli interview view 1          # Show all saved prep for an application
```

### Conversation History
```bash
linkedin-cli conversations log 1 --from me --text "Hi there, wanted to connect..."
linkedin-cli conversations log 1 --from them --text "Sure, happy to chat!"
linkedin-cli conversations view 1
linkedin-cli conversations export 1
```

### Content Calendar
```bash
linkedin-cli calendar add --title "AI post" --date 2026-03-01 [--draft-id 3]
linkedin-cli calendar list [--week] [--month]
linkedin-cli calendar mark-posted 1 [--date 2026-03-02]
linkedin-cli calendar stats
```

### Browser Automation (requires `uv sync --extra automation` + `uv run playwright install chromium`)
```bash
# One-time setup
linkedin-cli automate setup                 # Store credentials in the system keyring
linkedin-cli automate login                 # Log in (headful; handles 2FA) and save the session
linkedin-cli automate limits                # Today's usage vs daily safety caps

# Import people into the CRM
linkedin-cli automate search --query "ML Engineer at Stripe" --limit 20         # Preview results
linkedin-cli automate import-search --query "ML Engineer at Stripe" --limit 20  # Import to CRM
linkedin-cli automate profile https://linkedin.com/in/username                  # Import single profile

# Outreach (uses the contact's linkedin_url; updates pipeline status on success)
linkedin-cli automate connect 1 --draft-id 3          # Send connection request w/ AI draft as note
linkedin-cli automate connect 1 --note "Hi!" --dry-run
linkedin-cli automate message 1 --draft-id 4          # Message a connected contact

# Content + engagement
linkedin-cli automate post --calendar-id 1            # Publish a scheduled post, mark it posted
linkedin-cli automate post --text "Shipped a thing"   # Ad-hoc post (asks for confirmation)
linkedin-cli automate engage --contact-id 1 --contact-id 2 --likes 2  # Warm up targets
linkedin-cli automate engage --feed --likes 5         # Like posts on your feed

# Profile appearance
linkedin-cli automate sync-profile --headline-from-profile          # Push local profile headline
linkedin-cli automate sync-profile --about-file about.txt --dry-run # Push a new About section

# Applying (see Resume Repo Integration below)
linkedin-cli automate easy-apply 1              # Walk Easy Apply, stop at review step
linkedin-cli automate easy-apply 1 --submit     # Actually submit, with the attached resume PDF
```

Daily safety caps (persisted across runs in `~/.linkedin-cli/automation_usage.json`):
20 connections, 25 messages, 3 posts, 30 reactions, 15 Easy Applies.

### Resume Repo Integration

Job applications link to resume variants built by your resume repository
(the repo with `variants/<slug>/`, `output/<slug>-resume.pdf`, and the
`autoapply` pipeline). Point the CLI at your local checkout:

```bash
export LINKEDIN_RESUME_REPO=~/resume    # or pass --resume-repo per command

linkedin-cli applications suggest-resume 1     # Rank variants against the JD (skills.tex vs jd_text)
linkedin-cli applications attach-resume 1      # Attach best-matching variant + built PDFs
linkedin-cli applications attach-resume 1 --variant ai-engineer
linkedin-cli applications import-autoapply     # Pull submitted/interview/offer apps from autoapply's state.db
linkedin-cli applications import-autoapply --include-queued
```

The division of labor: the resume repo owns resume artifacts and broad ATS
auto-apply (Greenhouse/Lever/Ashby); this repo owns networking, LinkedIn-side
automation (including Easy Apply with the right variant PDF), and unified
application tracking.

### Data Management
```bash
linkedin-cli data export contacts   # Export contacts to CSV
linkedin-cli data export companies  # Export companies to CSV
linkedin-cli data export all        # Export everything
linkedin-cli data export contacts --format json  # Export as JSON
linkedin-cli data import contacts contacts.csv   # Import contacts
linkedin-cli data import contacts contacts.csv --merge  # Merge with existing
linkedin-cli data backup            # Create backup of all data
linkedin-cli data backup --verify   # Backup + integrity verification
linkedin-cli data backups           # List available backups
linkedin-cli data verify-backup backup.zip  # Verify an existing backup archive
linkedin-cli data restore backup.zip  # Restore from backup
linkedin-cli data restore backup.zip --dry-run  # Validate restore without writing files
```

### Analytics & Profile Optimization
```bash
linkedin-cli analytics summary       # Response rates, velocity, source effectiveness
linkedin-cli analytics conversion    # Pipeline conversion funnel
linkedin-cli analytics velocity      # Weekly outreach velocity
linkedin-cli optimize headline       # AI headline suggestions
linkedin-cli optimize about          # AI About-section rewrite
linkedin-cli optimize skills         # AI skills-list suggestions
linkedin-cli optimize full           # Full profile optimization report
# Then push the result live: linkedin-cli automate sync-profile --headline "..." --about-file about.txt
```

### Dashboard
```bash
linkedin-cli dashboard    # Overview of your job hunt
linkedin-cli daily-plan   # Unified daily execution plan (actions + opportunities + templates)
linkedin-cli daily-plan --save-recap  # Save the plan as markdown under ~/.linkedin-cli/recaps/
linkedin-cli daily-plan --json  # Machine-readable plan payload for automation
linkedin-cli run-daily --save-recap --generate-drafts --save-drafts
linkedin-cli run-daily --watch --time 09:00 --run-now  # Hands-off daily runner
linkedin-cli run-daily --idempotency-key monday-run  # Prevent duplicate one-shot executions
linkedin-cli run-daily --notify-webhook "https://hooks.slack.com/services/..."  # Failure alerts
linkedin-cli run-daily --retry-attempts 2 --retry-backoff-seconds 10
linkedin-cli run-daily --failure-streak-threshold 3  # Escalate when failures are consecutive
linkedin-cli automation status --json  # Check managed scheduler + latest run health
linkedin-cli automation schedule --time 09:00  # Install/update managed daily cron schedule
linkedin-cli automation schedule --time 09:00 --adopt-existing  # Migrate legacy unmanaged cron lines
linkedin-cli automation env sync  # Sync shell secrets to cron env file (~/.linkedin-cli/cron.env)
linkedin-cli automation env status  # Verify cron env file + key presence
linkedin-cli automation doctor --fix --run-smoke  # Diagnose, repair, and smoke-test automation
linkedin-cli automation unschedule  # Remove managed schedule
linkedin-cli health --json  # Preflight checks (API key, lock, schedule, history, webhook)
linkedin-cli run-history --status failed --limit 50 --json  # Inspect recent failed runs
```

Run reliability notes:
- `run-daily` acquires a lock file to prevent overlapping runs.
- Scheduled watch runs are idempotent by day (`schedule:<time>:<YYYY-MM-DD>`).
- Watch mode can catch up missed same-day runs (`--catch-up-missed`, enabled by default).
- Failed runs can auto-retry with exponential backoff.
- Failure-streak alerting avoids silent degradation (`--failure-streak-threshold`).
- `automation schedule` manages a dedicated cron block so setup is idempotent and reversible.
- `automation schedule` can adopt existing unmanaged `run-daily` cron entries to avoid duplicates.
- Managed schedules source an env file (`~/.linkedin-cli/cron.env`) for cron-safe secrets.
- Draft generation has a deterministic fallback mode when AI is unavailable (`LINKEDIN_AI_FALLBACK_ENABLED`).
- Every run appends a structured log entry at `~/.linkedin-cli/run_daily.log.jsonl`.
- Optional webhook notifications can also be set via `LINKEDIN_RUN_NOTIFY_WEBHOOK`.

## Pipeline Stages

Track each contact through your outreach pipeline:

```
⚪ not_contacted  →  📤 connection_sent  →  🤝 connected
                                              ↓
                                         💬 messaged
                                              ↓
                                         ✉️ responded
                                              ↓
                                         📅 call_scheduled
                                              ↓
                                         🎉 hired!
```

## How AI Works

The CLI uses Claude AI (via the Anthropic API) to generate personalized drafts. It uses:

- **Your profile** (skills, experience, target role)
- **Contact's info** (title, company, why you want to connect)
- **Company context** (if linked to a target company)
- **Context** (notes you've added)

To generate drafts that sound natural and personalized, not templated.

## Example Workflow

```bash
# Morning: Research target companies
linkedin-cli companies add -n "LangChain" -i "AI/ML" --priority high
linkedin-cli discover contacts --company "LangChain"

# Add contacts you found
linkedin-cli contacts add -n "Harrison Chase" -t "CEO" --company-id 1 \
  --notes "Founder, building RAG tools"

# Generate outreach
linkedin-cli drafts connection 1
# → AI generates personalized connection request

# Track progress
linkedin-cli contacts update 1 --status connection_sent
linkedin-cli contacts remind 1 --days 7

# When they accept
linkedin-cli contacts update 1 --status connected
linkedin-cli drafts message 1 -c "Ask about AI engineering roles"

# After a call
linkedin-cli drafts thank-you 1 --context "Great call about RAG tools"

# If no response
linkedin-cli contacts due
linkedin-cli drafts follow-up 1 --attempt 1

# View your progress
linkedin-cli dashboard

# Create thought leadership content
linkedin-cli research draft-post "lessons from my job search" --style story

# Backup your data
linkedin-cli data backup
```

## Data Storage

Everything is stored locally in `~/.linkedin-cli/`:

```
~/.linkedin-cli/
├── my_profile.json   # Your info
├── contacts.json     # Your CRM
├── companies.json    # Target companies
├── drafts.json       # Saved drafts
├── templates.json    # Reusable templates + experiment stats
├── research.json     # Saved ideas
├── job_postings.json # Tracked opportunities + profile match scores
├── applications.json # Job application tracking
├── conversations.json # Message threads per contact
├── content_calendar.json # Scheduled posts
├── interview_prep.json # Saved interview prep
├── automation_usage.json # Daily browser-automation counters
├── li_session.json   # Saved LinkedIn browser session (cookies)
├── run_daily_state.json # Completed idempotency keys
├── run_daily.log.jsonl  # Structured run history
├── run_daily.lock    # Active run lock (ephemeral)
└── backups/          # Backup files
```

## Why Not Just Use LinkedIn?

This tool helps you:
- **Stay organized** - Track who you've contacted, who responded
- **Track companies** - Keep notes on target companies and who you know there
- **Save time** - AI writes personalized drafts instantly
- **Be strategic** - See conversion rates, optimize your approach
- **Get reminders** - Never forget to follow up
- **Build content** - Get ideas that actually get engagement
- **Keep your data** - Export, backup, and own your job search data

## Requirements

- Python 3.10+
- Anthropic API key (set `ANTHROPIC_API_KEY` environment variable)
- `uv` package manager (or pip)

## License

MIT
