# LinkedIn Job Hunt Assistant

A local CRM + AI-powered tool to accelerate your job search on LinkedIn.

## What It Does

**100% legal, no LinkedIn automation** - This is a personal productivity tool that:

1. **Companies** - Track target companies for networking
2. **CRM** - Track people you want to connect with, their status, follow-ups
3. **AI Drafts** - Generate personalized connection requests, messages, intro requests, and more
4. **Discovery** - AI-powered suggestions for who to connect with
5. **Content Research** - Get post ideas, engagement strategies, and draft posts
6. **Data Management** - Import, export, and backup your data

## Quick Start

```bash
cd linkedin-cli
uv sync

# 1. Set up your profile (used for personalization)
uv run python cli.py profile setup

# 2. Add target companies
uv run python cli.py companies add

# 3. Add contacts to track
uv run python cli.py contacts add --company-id 1

# 4. Generate personalized outreach
uv run python cli.py drafts connection 1

# 5. Get AI suggestions for more contacts
uv run python cli.py discover contacts --company "LangChain"

# 6. View your dashboard
uv run python cli.py dashboard
```

## Commands

### Profile (Your Info)
```bash
linkedin-cli profile setup     # Set up your info for AI personalization
linkedin-cli profile show      # View your saved profile
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
linkedin-cli contacts update 1 --email "x@y.com"   # Add email
linkedin-cli contacts link-company 1 2          # Link contact to company
linkedin-cli contacts activity 1                # View activity log
linkedin-cli contacts due                       # Show overdue follow-ups
linkedin-cli contacts due --days 7              # Show follow-ups due within 7 days
linkedin-cli contacts remind 1 --days 7         # Set follow-up reminder
linkedin-cli contacts stats                     # View pipeline stats
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

### Data Management
```bash
linkedin-cli data export contacts   # Export contacts to CSV
linkedin-cli data export companies  # Export companies to CSV
linkedin-cli data export all        # Export everything
linkedin-cli data export contacts --format json  # Export as JSON
linkedin-cli data import contacts contacts.csv   # Import contacts
linkedin-cli data import contacts contacts.csv --merge  # Merge with existing
linkedin-cli data backup            # Create backup of all data
linkedin-cli data backups           # List available backups
linkedin-cli data restore backup.zip  # Restore from backup
```

### Dashboard
```bash
linkedin-cli dashboard    # Overview of your job hunt
```

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
├── research.json     # Saved ideas
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
