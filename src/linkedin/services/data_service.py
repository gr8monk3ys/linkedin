"""Data import/export/backup service."""

import csv
import json
import zipfile
from datetime import datetime
from pathlib import Path

from linkedin.data.json_store import (
    APPLICATIONS_FILE,
    BACKUPS_DIR,
    CALENDAR_FILE,
    COMPANIES_FILE,
    CONTACTS_FILE,
    CONVERSATIONS_FILE,
    DRAFTS_FILE,
    INTERVIEW_PREP_FILE,
    JOB_POSTINGS_FILE,
    PROFILE_FILE,
    RESEARCH_FILE,
    RUN_DAILY_LOG_FILE,
    RUN_DAILY_STATE_FILE,
    TEMPLATES_FILE,
    ensure_dirs,
    load_json,
    save_json,
)


class DataService:
    def export_contacts(self, output: str | None = None, fmt: str = "csv") -> tuple[int, str]:
        """Export contacts. Returns (count, output_file)."""
        contacts = load_json(CONTACTS_FILE)
        if not contacts:
            return 0, ""

        if fmt == "csv":
            output_file = output or "contacts_export.csv"
            fieldnames = [
                "id", "name", "title", "company", "linkedin_url", "email",
                "status", "source", "notes", "follow_up_date", "created_at", "company_id",
            ]
            with open(output_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(contacts)
        else:
            output_file = output or "contacts_export.json"
            save_json(Path(output_file), contacts)

        return len(contacts), output_file

    def export_companies(self, output: str | None = None, fmt: str = "csv") -> tuple[int, str]:
        """Export companies. Returns (count, output_file)."""
        companies = load_json(COMPANIES_FILE)
        if not companies:
            return 0, ""

        if fmt == "csv":
            output_file = output or "companies_export.csv"
            fieldnames = [
                "id", "name", "industry", "size", "linkedin_url", "website",
                "why_target", "priority", "notes", "created_at",
            ]
            with open(output_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(companies)
        else:
            output_file = output or "companies_export.json"
            save_json(Path(output_file), companies)

        return len(companies), output_file

    def import_contacts(self, file_path: str, merge: bool = False) -> int:
        """Import contacts. Returns count imported."""
        path = Path(file_path)
        existing = load_json(CONTACTS_FILE) if merge else []

        if path.suffix == ".csv":
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    if row.get("id"):
                        row["id"] = int(row["id"])
                    else:
                        row["id"] = len(existing) + len(imported) + 1
                    if "company_id" in row and row["company_id"]:
                        row["company_id"] = int(row["company_id"])
                    else:
                        row["company_id"] = None
                    row.setdefault("status", "not_contacted")
                    row.setdefault("activities", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(path.read_text())

        if merge:
            max_id = max([c["id"] for c in existing], default=0)
            for contact in imported:
                max_id += 1
                contact["id"] = max_id
            final = existing + imported
        else:
            final = imported

        save_json(CONTACTS_FILE, final)
        return len(imported)

    def import_companies(self, file_path: str, merge: bool = False) -> int:
        """Import companies. Returns count imported."""
        path = Path(file_path)
        existing = load_json(COMPANIES_FILE) if merge else []

        if path.suffix == ".csv":
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                imported = []
                for row in reader:
                    if row.get("id"):
                        row["id"] = int(row["id"])
                    else:
                        row["id"] = len(existing) + len(imported) + 1
                    row.setdefault("key_people_to_find", [])
                    row.setdefault("created_at", datetime.now().isoformat())
                    imported.append(row)
        else:
            imported = json.loads(path.read_text())

        if merge:
            max_id = max([c["id"] for c in existing], default=0)
            for company in imported:
                max_id += 1
                company["id"] = max_id
            final = existing + imported
        else:
            final = imported

        save_json(COMPANIES_FILE, final)
        return len(imported)

    def create_backup(self, output: str | None = None) -> tuple[str, int]:
        """Create backup. Returns (backup_path, files_backed_up)."""
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = output or str(BACKUPS_DIR / f"linkedin_cli_backup_{timestamp}.zip")

        files_to_backup = [
            PROFILE_FILE,
            CONTACTS_FILE,
            COMPANIES_FILE,
            DRAFTS_FILE,
            RESEARCH_FILE,
            TEMPLATES_FILE,
            JOB_POSTINGS_FILE,
            APPLICATIONS_FILE,
            CONVERSATIONS_FILE,
            CALENDAR_FILE,
            INTERVIEW_PREP_FILE,
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

        target_path = (data_dir / member_path).resolve()
        if data_dir != target_path and data_dir not in target_path.parents:
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
                    target_path = self._validate_backup_member_path(member.filename, data_dir)
                    if target_path is None:
                        result["errors"].append(f"Unsafe path: {member.filename}")
                        return result

                    if member.is_dir():
                        continue

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
        backup_path = Path(backup_file)

        if not zipfile.is_zipfile(backup_path):
            return None

        ensure_dirs()

        restored = 0
        from linkedin.data.json_store import DATA_DIR

        data_dir = DATA_DIR.resolve()
        with zipfile.ZipFile(backup_path, "r") as zipf:
            for member in zipf.infolist():
                target_path = self._validate_backup_member_path(member.filename, data_dir)
                if target_path is None:
                    return None

                if member.is_dir():
                    if not dry_run:
                        target_path.mkdir(parents=True, exist_ok=True)
                    continue

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
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with target_path.open("wb") as dst:
                        dst.write(content)
                restored += 1

        return restored

    def list_backups(self) -> list[dict]:
        """List available backups. Returns list of {name, size_kb, created}."""
        if not BACKUPS_DIR.exists():
            return []

        backups = list(BACKUPS_DIR.glob("*.zip"))
        if not backups:
            return []

        backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        result = []
        for backup in backups:
            stat = backup.stat()
            result.append({
                "name": backup.name,
                "size_kb": stat.st_size / 1024,
                "created": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

        return result
