"""Data import/export/backup service."""

import csv
import json
import zipfile
from datetime import datetime
from pathlib import Path

from linkedin.data.factory import create_repos, get_backend
from linkedin.data.json_store import (
    BACKUPS_DIR,
    COMPANIES_FILE,
    CONTACTS_FILE,
    DRAFTS_FILE,
    JOB_POSTINGS_FILE,
    PROFILE_FILE,
    RESEARCH_FILE,
    RUN_DAILY_LOG_FILE,
    RUN_DAILY_STATE_FILE,
    TEMPLATES_FILE,
    ensure_dirs,
)
from linkedin.data.repository import CompanyRepo, ContactRepo


class DataService:
    def __init__(
        self,
        contact_repo: ContactRepo | None = None,
        company_repo: CompanyRepo | None = None,
        backend: str | None = None,
    ):
        if contact_repo is None or company_repo is None:
            resolved_contact_repo, resolved_company_repo, *_ = create_repos()
            contact_repo = contact_repo or resolved_contact_repo
            company_repo = company_repo or resolved_company_repo

        self.contacts = contact_repo
        self.companies = company_repo
        self.backend = (backend or get_backend()).lower()

    @staticmethod
    def _allowed_backup_members() -> set[str]:
        return {
            PROFILE_FILE.name,
            CONTACTS_FILE.name,
            COMPANIES_FILE.name,
            DRAFTS_FILE.name,
            TEMPLATES_FILE.name,
            RESEARCH_FILE.name,
            JOB_POSTINGS_FILE.name,
            RUN_DAILY_STATE_FILE.name,
            RUN_DAILY_LOG_FILE.name,
        }

    def _clear_contacts(self) -> None:
        for contact in self.contacts.list_all():
            self.contacts.delete(contact["id"])

    def _clear_companies(self) -> None:
        for company in self.companies.list_all():
            self.companies.delete(company["id"])

    def _require_json_backend(self, operation: str) -> None:
        if self.backend != "json":
            raise RuntimeError(f"`linkedin data {operation}` is only supported with LINKEDIN_BACKEND=json.")

    def _normalize_contact_ids(self, contacts: list[dict], starting_id: int = 0) -> list[dict]:
        if self.backend != "json":
            return contacts

        next_id = starting_id
        normalized = []
        for contact in contacts:
            entry = dict(contact)
            raw_id = entry.get("id")
            if not raw_id:
                next_id += 1
                entry["id"] = next_id
            else:
                next_id = max(next_id, int(raw_id))
                entry["id"] = int(raw_id)
            normalized.append(entry)
        return normalized

    def _normalize_company_ids(self, companies: list[dict], starting_id: int = 0) -> list[dict]:
        if self.backend != "json":
            return companies

        next_id = starting_id
        normalized = []
        for company in companies:
            entry = dict(company)
            raw_id = entry.get("id")
            if not raw_id:
                next_id += 1
                entry["id"] = next_id
            else:
                next_id = max(next_id, int(raw_id))
                entry["id"] = int(raw_id)
            normalized.append(entry)
        return normalized

    def export_contacts(self, output: str | None = None, fmt: str = "csv") -> tuple[int, str]:
        """Export contacts. Returns (count, output_file)."""
        contacts = self.contacts.list_all()
        if not contacts:
            return 0, ""

        if fmt == "csv":
            output_file = output or "contacts_export.csv"
            fieldnames = [
                "id",
                "name",
                "title",
                "company",
                "linkedin_url",
                "email",
                "status",
                "source",
                "notes",
                "follow_up_date",
                "created_at",
                "company_id",
            ]
            with open(output_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(contacts)
        else:
            output_file = output or "contacts_export.json"
            Path(output_file).write_text(json.dumps(contacts, indent=2, default=str))

        return len(contacts), output_file

    def export_companies(self, output: str | None = None, fmt: str = "csv") -> tuple[int, str]:
        """Export companies. Returns (count, output_file)."""
        companies = self.companies.list_all()
        if not companies:
            return 0, ""

        if fmt == "csv":
            output_file = output or "companies_export.csv"
            fieldnames = [
                "id",
                "name",
                "industry",
                "size",
                "linkedin_url",
                "website",
                "why_target",
                "priority",
                "notes",
                "created_at",
            ]
            with open(output_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(companies)
        else:
            output_file = output or "companies_export.json"
            Path(output_file).write_text(json.dumps(companies, indent=2, default=str))

        return len(companies), output_file

    def import_contacts(self, file_path: str, merge: bool = False) -> int:
        """Import contacts. Returns count imported."""
        path = Path(file_path)
        existing = self.contacts.list_all() if merge else []

        if path.suffix == ".csv":
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    if "id" in row and row["id"]:
                        row["id"] = int(row["id"])
                    if row.get("company_id"):
                        row["company_id"] = int(row["company_id"])
                    else:
                        row["company_id"] = None
                    row.setdefault("status", "not_contacted")
                    row.setdefault("activities", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(path.read_text())

        max_existing_id = max([int(c["id"]) for c in existing if c.get("id")], default=0)
        if merge:
            imported = [{**contact, "id": max_existing_id + i + 1} for i, contact in enumerate(imported)]
        else:
            self._clear_contacts()

        for contact in self._normalize_contact_ids(imported, max_existing_id):
            self.contacts.add(contact)
        return len(imported)

    def import_companies(self, file_path: str, merge: bool = False) -> int:
        """Import companies. Returns count imported."""
        path = Path(file_path)
        existing = self.companies.list_all() if merge else []

        if path.suffix == ".csv":
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    if "id" in row and row["id"]:
                        row["id"] = int(row["id"])
                    row.setdefault("key_people_to_find", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(path.read_text())

        max_existing_id = max([int(c["id"]) for c in existing if c.get("id")], default=0)
        if merge:
            imported = [{**company, "id": max_existing_id + i + 1} for i, company in enumerate(imported)]
        else:
            self._clear_companies()

        for company in self._normalize_company_ids(imported, max_existing_id):
            self.companies.add(company)
        return len(imported)

    def create_backup(self, output: str | None = None) -> tuple[str, int]:
        """Create backup. Returns (backup_path, files_backed_up)."""
        self._require_json_backend("backup")
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = output or str(BACKUPS_DIR / f"linkedin_cli_backup_{timestamp}.zip")
        files_to_backup = [
            PROFILE_FILE,
            CONTACTS_FILE,
            COMPANIES_FILE,
            DRAFTS_FILE,
            TEMPLATES_FILE,
            RESEARCH_FILE,
            JOB_POSTINGS_FILE,
            RUN_DAILY_STATE_FILE,
            RUN_DAILY_LOG_FILE,
        ]

        backed_up = 0
        with zipfile.ZipFile(backup_name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_backup:
                if file_path.exists():
                    zipf.write(file_path, file_path.name)
                    backed_up += 1

        return backup_name, backed_up

    def _validate_backup_member_path(self, member_name: str, data_dir: Path) -> Path | None:
        member_path = Path(member_name)
        if member_path.is_absolute() or ".." in member_path.parts:
            return None
        if member_path.name != member_name or member_name not in self._allowed_backup_members():
            return None

        target_path = (data_dir / member_path).resolve()
        if target_path.parent != data_dir:
            return None
        return target_path

    def verify_backup(self, backup_file: str) -> dict:
        """Verify backup integrity, path safety, and JSON readability."""
        backup_path = Path(backup_file)
        result = {
            "valid": False,
            "files_checked": 0,
            "json_files_checked": 0,
            "errors": [],
        }

        if not zipfile.is_zipfile(backup_path):
            result["errors"].append("Not a zip archive.")
            return result

        from linkedin.data.json_store import DATA_DIR

        data_dir = DATA_DIR.resolve()
        try:
            with zipfile.ZipFile(backup_path, "r") as zipf:
                for member in zipf.infolist():
                    if member.is_dir():
                        result["errors"].append(f"Directories are not allowed in backups: {member.filename}")
                        return result

                    target_path = self._validate_backup_member_path(member.filename, data_dir)
                    if target_path is None:
                        result["errors"].append(f"Unsafe path: {member.filename}")
                        return result

                    result["files_checked"] += 1
                    content = zipf.read(member)
                    suffix = target_path.suffix.lower()
                    if suffix == ".json":
                        json.loads(content.decode("utf-8"))
                        result["json_files_checked"] += 1
                    elif suffix == ".jsonl":
                        for line in content.decode("utf-8").splitlines():
                            if line.strip():
                                json.loads(line)
                        result["json_files_checked"] += 1
        except Exception as exc:
            result["errors"].append(str(exc))
            return result

        result["valid"] = result["files_checked"] > 0 and not result["errors"]
        return result

    def restore_backup(self, backup_file: str, dry_run: bool = False) -> int | None:
        """Restore from backup. Returns files_restored or None if invalid."""
        self._require_json_backend("restore")
        backup_path = Path(backup_file)
        if not zipfile.is_zipfile(backup_path):
            return None

        ensure_dirs()

        restored = 0
        from linkedin.data.json_store import DATA_DIR

        data_dir = DATA_DIR.resolve()
        with zipfile.ZipFile(backup_path, "r") as zipf:
            for member in zipf.infolist():
                if member.is_dir():
                    return None

                target_path = self._validate_backup_member_path(member.filename, data_dir)
                if target_path is None:
                    return None

                with zipf.open(member, "r") as src:
                    content = src.read()

                if dry_run:
                    suffix = target_path.suffix.lower()
                    if suffix == ".json":
                        json.loads(content.decode("utf-8"))
                    elif suffix == ".jsonl":
                        for line in content.decode("utf-8").splitlines():
                            if line.strip():
                                json.loads(line)
                else:
                    target_path.write_bytes(content)

                restored += 1

        return restored

    def list_backups(self) -> list[dict]:
        """List available backups. Returns list of {name, size_kb, created}."""
        self._require_json_backend("backups")
        if not BACKUPS_DIR.exists():
            return []

        backups = list(BACKUPS_DIR.glob("*.zip"))
        backups.sort(key=lambda backup: backup.stat().st_mtime, reverse=True)

        result = []
        for backup in backups:
            stat = backup.stat()
            result.append({
                "name": backup.name,
                "size_kb": stat.st_size / 1024,
                "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

        return result
