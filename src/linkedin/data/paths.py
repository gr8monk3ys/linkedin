"""The one root every file lives under.

`LINKEDIN_DATA_DIR` overrides the default `~/.linkedin-cli`. Everything that
touches disk takes its path from a `DataDir` at construction; nothing reads a
module-level constant at call time. That is what lets a test say
`DataDir(tmp_path)` once instead of monkeypatching twenty-two globals — a
list that had already drifted and left `daily-plan` tests reading the
developer's real applications file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "LINKEDIN_DATA_DIR"
DEFAULT_ROOT = Path.home() / ".linkedin-cli"


@dataclass(frozen=True)
class DataDir:
    root: Path

    @classmethod
    def from_env(cls) -> DataDir:
        override = os.environ.get(ENV_VAR, "").strip()
        return cls(Path(override).expanduser() if override else DEFAULT_ROOT)

    def ensure(self) -> DataDir:
        self.root.mkdir(parents=True, exist_ok=True)
        return self

    # -- CRM stores
    @property
    def profile(self) -> Path:
        return self.root / "my_profile.json"

    @property
    def contacts(self) -> Path:
        return self.root / "contacts.json"

    @property
    def companies(self) -> Path:
        return self.root / "companies.json"

    @property
    def drafts(self) -> Path:
        return self.root / "drafts.json"

    @property
    def research(self) -> Path:
        return self.root / "research.json"

    @property
    def templates(self) -> Path:
        return self.root / "templates.json"

    @property
    def job_postings(self) -> Path:
        return self.root / "job_postings.json"

    @property
    def applications(self) -> Path:
        return self.root / "applications.json"

    @property
    def conversations(self) -> Path:
        return self.root / "conversations.json"

    @property
    def calendar(self) -> Path:
        return self.root / "content_calendar.json"

    @property
    def interview_prep(self) -> Path:
        return self.root / "interview_prep.json"

    @property
    def inbox_proposals(self) -> Path:
        return self.root / "inbox_proposals.json"

    @property
    def posts(self) -> Path:
        return self.root / "posts.json"

    @property
    def thread_index(self) -> Path:
        return self.root / "thread_index.json"

    # -- run-daily
    @property
    def run_daily_state(self) -> Path:
        return self.root / "run_daily_state.json"

    @property
    def run_daily_log(self) -> Path:
        return self.root / "run_daily.log.jsonl"

    @property
    def run_daily_lock(self) -> Path:
        return self.root / "run_daily.lock"

    @property
    def recaps(self) -> Path:
        return self.root / "recaps"

    @property
    def cron_env(self) -> Path:
        return self.root / "cron.env"

    @property
    def cron_out_log(self) -> Path:
        return self.root / "run_daily.cron.out.log"

    @property
    def cron_err_log(self) -> Path:
        return self.root / "run_daily.cron.err.log"

    # -- automation
    @property
    def automation_usage(self) -> Path:
        return self.root / "automation_usage.json"

    @property
    def li_session(self) -> Path:
        return self.root / "li_session.json"

    @property
    def limits(self) -> Path:
        return self.root / "limits.json"

    # -- backups
    @property
    def backups(self) -> Path:
        return self.root / "backups"

    def backup_members(self) -> list[Path]:
        """Every data file a backup should carry.

        Enumerated from the directory, not from a list: a list is how the job
        postings, templates, and run log were once left out. Excluded: the
        browser session (cookies), the lock, temp files, and backups themselves.
        """
        skip = {self.li_session.name, self.run_daily_lock.name}
        members = [
            p
            for p in sorted(self.root.glob("*"))
            if p.is_file() and p.suffix in {".json", ".jsonl"} and p.name not in skip and not p.name.startswith(".")
        ]
        return members
