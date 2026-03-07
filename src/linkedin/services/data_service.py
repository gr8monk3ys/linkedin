"""Data import/export/backup service."""

import csv
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from linkedin.data.json_store import (
    BACKUPS_DIR,
    COMPANIES_FILE,
    CONTACTS_FILE,
    DRAFTS_FILE,
    PROFILE_FILE,
    RESEARCH_FILE,
    ensure_dirs,
    load_json,
    save_json,
)


class DataService:
    @staticmethod
    def _allowed_backup_members() -> set[str]:
        return {
            PROFILE_FILE.name,
            CONTACTS_FILE.name,
            COMPANIES_FILE.name,
            DRAFTS_FILE.name,
            RESEARCH_FILE.name,
        }

    @classmethod
    def _is_safe_backup_member(cls, filename: str) -> bool:
        path = Path(filename)
        return not path.is_absolute() and path.name == filename and filename in cls._allowed_backup_members()

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
                    if "id" in row:
                        row["id"] = int(row["id"]) if row["id"] else len(existing) + len(imported) + 1
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
                    if "id" in row:
                        row["id"] = int(row["id"]) if row["id"] else len(existing) + len(imported) + 1
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

        files_to_backup = [PROFILE_FILE, CONTACTS_FILE, COMPANIES_FILE, DRAFTS_FILE, RESEARCH_FILE]

        backed_up = 0
        with zipfile.ZipFile(backup_name, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_backup:
                if file_path.exists():
                    zipf.write(file_path, file_path.name)
                    backed_up += 1

        return backup_name, backed_up

    def restore_backup(self, backup_file: str) -> int | None:
        """Restore from backup. Returns files_restored or None if invalid."""
        backup_path = Path(backup_file)

        if not zipfile.is_zipfile(backup_path):
            return None

        ensure_dirs()

        restored = 0
        from linkedin.data.json_store import DATA_DIR

        with zipfile.ZipFile(backup_path, "r") as zipf:
            members = zipf.infolist()
            if any(info.is_dir() or not self._is_safe_backup_member(info.filename) for info in members):
                return None

            for info in members:
                target_path = DATA_DIR / info.filename
                with zipf.open(info, "r") as src, target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
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
