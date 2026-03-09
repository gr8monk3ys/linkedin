"""Tests for data import/export/backup service."""

import json
import zipfile

import pytest

from linkedin.services.data_service import DataService


@pytest.fixture
def data_svc(json_repos, tmp_path, monkeypatch):
    """DataService with patched paths matching json_repos."""
    import linkedin.services.data_service as ds

    monkeypatch.setattr(ds, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(ds, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(ds, "COMPANIES_FILE", tmp_path / "companies.json")
    monkeypatch.setattr(ds, "DRAFTS_FILE", tmp_path / "drafts.json")
    monkeypatch.setattr(ds, "TEMPLATES_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(ds, "RESEARCH_FILE", tmp_path / "research.json")
    monkeypatch.setattr(ds, "BACKUPS_DIR", tmp_path / "backups")

    return DataService()


class TestDataService:
    def test_export_contacts_csv(self, data_svc, json_repos, tmp_path):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "Alice", "title": "Engineer", "company": "Acme",
                          "linkedin_url": "", "status": "connected", "notes": ""})

        output = str(tmp_path / "contacts.csv")
        count, path = data_svc.export_contacts(output=output, fmt="csv")
        assert count == 1
        assert path == output

    def test_export_contacts_json(self, data_svc, json_repos, tmp_path):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "Alice", "title": "Engineer", "company": "Acme",
                          "linkedin_url": "", "status": "connected", "notes": ""})

        output = str(tmp_path / "out_contacts.json")
        count, path = data_svc.export_contacts(output=output, fmt="json")
        assert count == 1

    def test_export_contacts_empty(self, data_svc):
        count, path = data_svc.export_contacts()
        assert count == 0

    def test_export_companies_csv(self, data_svc, json_repos, tmp_path):
        company_repo = json_repos[1]
        company_repo.add({"id": 1, "name": "Acme", "industry": "Tech", "size": "51-200",
                          "priority": "high", "linkedin_url": "", "website": "", "notes": ""})

        output = str(tmp_path / "companies.csv")
        count, path = data_svc.export_companies(output=output, fmt="csv")
        assert count == 1

    def test_export_companies_json(self, data_svc, json_repos, tmp_path):
        company_repo = json_repos[1]
        company_repo.add({"id": 1, "name": "Acme", "industry": "Tech"})

        output = str(tmp_path / "out_companies.json")
        count, path = data_svc.export_companies(output=output, fmt="json")
        assert count == 1

    def test_export_companies_empty(self, data_svc):
        count, path = data_svc.export_companies()
        assert count == 0

    def test_import_contacts_csv(self, data_svc, tmp_path):
        csv_file = tmp_path / "import.csv"
        csv_file.write_text("id,name,title,company,status\n1,Alice,Engineer,Acme,not_contacted\n")

        count = data_svc.import_contacts(str(csv_file))
        assert count == 1

    def test_import_contacts_json(self, data_svc, tmp_path):
        json_file = tmp_path / "import_c.json"
        json_file.write_text(json.dumps([{"id": 1, "name": "Alice", "status": "connected"}]))

        count = data_svc.import_contacts(str(json_file))
        assert count == 1

    def test_import_contacts_merge(self, data_svc, json_repos, tmp_path):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "Existing", "status": "connected"})

        json_file = tmp_path / "merge_c.json"
        json_file.write_text(json.dumps([{"id": 1, "name": "New", "status": "not_contacted"}]))

        count = data_svc.import_contacts(str(json_file), merge=True)
        assert count == 1

    def test_import_companies_csv(self, data_svc, tmp_path):
        csv_file = tmp_path / "companies_import.csv"
        csv_file.write_text("id,name,industry\n1,Acme,Tech\n")

        count = data_svc.import_companies(str(csv_file))
        assert count == 1

    def test_import_companies_json(self, data_svc, tmp_path):
        json_file = tmp_path / "import_co.json"
        json_file.write_text(json.dumps([{"id": 1, "name": "Acme"}]))

        count = data_svc.import_companies(str(json_file))
        assert count == 1

    def test_import_companies_merge(self, data_svc, json_repos, tmp_path):
        company_repo = json_repos[1]
        company_repo.add({"id": 1, "name": "Existing"})

        json_file = tmp_path / "merge_co.json"
        json_file.write_text(json.dumps([{"id": 1, "name": "New"}]))

        count = data_svc.import_companies(str(json_file), merge=True)
        assert count == 1

    def test_create_and_restore_backup(self, data_svc, json_repos, tmp_path):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "Alice", "status": "connected"})

        backup_path = str(tmp_path / "backup.zip")
        path, files = data_svc.create_backup(output=backup_path)
        assert files >= 1

        restored = data_svc.restore_backup(backup_path)
        assert restored is not None
        assert restored >= 1

    def test_restore_invalid_backup(self, data_svc, tmp_path):
        bad_file = tmp_path / "not_a_zip.txt"
        bad_file.write_text("not a zip")
        assert data_svc.restore_backup(str(bad_file)) is None

    def test_restore_rejects_unsafe_backup_member(self, data_svc, tmp_path):
        backup_path = tmp_path / "unsafe.zip"
        with zipfile.ZipFile(backup_path, "w") as zipf:
            zipf.writestr("../outside.json", "{}")

        assert data_svc.restore_backup(str(backup_path)) is None
        assert not (tmp_path.parent / "outside.json").exists()

    def test_list_backups_empty(self, data_svc):
        assert data_svc.list_backups() == []

    def test_list_backups_with_data(self, data_svc, json_repos):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "Alice"})

        data_svc.create_backup()
        backups = data_svc.list_backups()
        assert len(backups) >= 1
        assert "name" in backups[0]
        assert "size_kb" in backups[0]

    def test_export_contacts_uses_active_backend_repos(self, db_repos, tmp_path):
        contact_repo, company_repo, *_ = db_repos
        contact_repo.add({"name": "Alice", "title": "Engineer", "company": "Acme"})
        svc = DataService(contact_repo, company_repo, backend="db")

        output = str(tmp_path / "db_contacts.json")
        count, path = svc.export_contacts(output=output, fmt="json")
        assert count == 1
        assert path == output

    def test_backup_requires_json_backend(self, db_repos):
        contact_repo, company_repo, *_ = db_repos
        svc = DataService(contact_repo, company_repo, backend="db")
        with pytest.raises(RuntimeError, match="LINKEDIN_BACKEND=json"):
            svc.create_backup()
