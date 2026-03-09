# LinkedIn Job Hunt Assistant

Local CRM + AI assistant for running a LinkedIn-heavy job search. The repo ships with:

- `linkedin`: CLI for CRM, AI drafting, research, analytics, and data management
- `linkedin-web`: Reflex web UI for the same local data
- Optional browser automation for search, connection requests, and feed engagement
- Pluggable storage backends: local JSON, SQLModel database, or Twenty CRM

## Features

- Track target companies and contacts
- Generate AI drafts for connection requests, follow-ups, intro asks, and thank-you notes
- Research post ideas, hashtags, and engagement strategies
- Review analytics, market insights, and profile optimization suggestions
- Import/export data and create local backups
- Use a local web dashboard in addition to the CLI

## Install

Base CLI:

```bash
uv sync
```

Web UI:

```bash
uv sync --extra web
```

Browser automation:

```bash
uv sync --extra automation
```

Everything:

```bash
uv sync --extra web --extra automation
```

## Quick Start

CLI:

```bash
uv run linkedin profile setup
uv run linkedin companies add
uv run linkedin contacts add --company-id 1
uv run linkedin drafts connection 1
uv run linkedin dashboard
```

Web UI:

```bash
uv run linkedin-web
```

Then open `http://localhost:3000`.

## Common Commands

Profile:

```bash
linkedin profile setup
linkedin profile show
```

Companies:

```bash
linkedin companies add
linkedin companies list
linkedin companies view 1
linkedin companies update 1 --priority high
linkedin companies contacts 1
```

Contacts:

```bash
linkedin contacts add --company-id 1
linkedin contacts list --status connected
linkedin contacts view 1
linkedin contacts update 1 --status connected
linkedin contacts due --days 7
linkedin contacts remind 1 --days 7
```

Drafts and templates:

```bash
linkedin drafts connection 1
linkedin drafts message 1 --context "Ask about open roles"
linkedin drafts follow-up 1 --attempt 2
linkedin templates list
```

Discovery and research:

```bash
linkedin discover contacts --company "LangChain"
linkedin discover companies
linkedin research ideas --topic "job search lessons"
linkedin research draft-post "networking lessons" --style story
```

Analytics and optimization:

```bash
linkedin analytics summary
linkedin market salary --role "Staff Engineer" --location "San Francisco"
linkedin optimize full
```

Data management:

```bash
linkedin data export contacts --format csv
linkedin data import contacts contacts.csv --merge
linkedin data backup
linkedin data backups
linkedin data restore backup.zip
```

Automation:

```bash
linkedin auto status
linkedin auto connect --dry-run --limit 5
linkedin auto engage --dry-run --limit 5 --comments 2
```

## Backends

Default storage is local JSON files under `~/.linkedin-cli/`.

To use the SQLModel backend:

```bash
export LINKEDIN_BACKEND=db
```

Optional:

```bash
export DATABASE_URL=sqlite:///$HOME/.linkedin-cli/linkedin.db
```

To use Twenty CRM:

```bash
export LINKEDIN_BACKEND=twenty
export TWENTY_API_URL=http://localhost:3000
export TWENTY_API_KEY=your-api-key
```

`linkedin data export` works with any configured backend.
`linkedin data backup`, `restore`, and `backups` currently operate on the JSON backend only.

## AI

AI-powered commands use Anthropic via `ANTHROPIC_API_KEY`.

```bash
export ANTHROPIC_API_KEY=your-key
```

Without that key, AI features return an error message instead of generated content.

## Local Data

JSON mode stores data in `~/.linkedin-cli/`:

```text
~/.linkedin-cli/
├── my_profile.json
├── contacts.json
├── companies.json
├── drafts.json
├── templates.json
├── research.json
├── backups/
└── linkedin.db        # when using LINKEDIN_BACKEND=db
```

## Automation Note

This repo includes optional LinkedIn browser automation. Use it carefully, keep rate limits conservative, and make sure you understand the platform and account risk before using anything beyond `--dry-run`.

## Requirements

- Python 3.10+
- `uv`
- `ANTHROPIC_API_KEY` for AI features
- `reflex` extra for the web UI
- `playwright` and `keyring` extras for automation

## License

MIT
