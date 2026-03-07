"""JSON file-based implementation of repository interfaces."""

import json
from pathlib import Path

from linkedin.data.repository import CompanyRepo, ContactRepo, DraftRepo, ProfileRepo, ResearchRepo
from linkedin.types import CompanyDict, ContactDict, DraftDict, ProfileDict, ResearchDict

DATA_DIR = Path.home() / ".linkedin-cli"
PROFILE_FILE = DATA_DIR / "my_profile.json"
CONTACTS_FILE = DATA_DIR / "contacts.json"
COMPANIES_FILE = DATA_DIR / "companies.json"
DRAFTS_FILE = DATA_DIR / "drafts.json"
RESEARCH_FILE = DATA_DIR / "research.json"
BACKUPS_DIR = DATA_DIR / "backups"


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default=None):
    if default is None:
        default = []
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data):
    ensure_dirs()
    path.write_text(json.dumps(data, indent=2, default=str))


def next_id(items: list[dict]) -> int:
    """Return the next available integer ID for a collection."""
    return max((int(item.get("id", 0) or 0) for item in items), default=0) + 1


class JsonContactRepo(ContactRepo):
    def list_all(self) -> list[ContactDict]:
        return load_json(CONTACTS_FILE)

    def get(self, contact_id: int) -> ContactDict | None:
        return next((c for c in self.list_all() if c["id"] == contact_id), None)

    def add(self, contact: ContactDict) -> ContactDict:
        contacts = self.list_all()
        contacts.append(contact)
        save_json(CONTACTS_FILE, contacts)
        return contact

    def update(self, contact: ContactDict) -> None:
        contacts = self.list_all()
        for i, c in enumerate(contacts):
            if c["id"] == contact["id"]:
                contacts[i] = contact
                break
        save_json(CONTACTS_FILE, contacts)

    def delete(self, contact_id: int) -> bool:
        contacts = self.list_all()
        new_contacts = [c for c in contacts if c["id"] != contact_id]
        if len(new_contacts) == len(contacts):
            return False
        save_json(CONTACTS_FILE, new_contacts)
        return True

    def next_id(self) -> int:
        return next_id(self.list_all())

    def save_all(self, contacts: list[ContactDict]) -> None:
        save_json(CONTACTS_FILE, contacts)


class JsonCompanyRepo(CompanyRepo):
    def list_all(self) -> list[CompanyDict]:
        return load_json(COMPANIES_FILE)

    def get(self, company_id: int) -> CompanyDict | None:
        return next((c for c in self.list_all() if c["id"] == company_id), None)

    def add(self, company: CompanyDict) -> CompanyDict:
        companies = self.list_all()
        companies.append(company)
        save_json(COMPANIES_FILE, companies)
        return company

    def update(self, company: CompanyDict) -> None:
        companies = self.list_all()
        for i, c in enumerate(companies):
            if c["id"] == company["id"]:
                companies[i] = company
                break
        save_json(COMPANIES_FILE, companies)

    def delete(self, company_id: int) -> bool:
        companies = self.list_all()
        new_companies = [c for c in companies if c["id"] != company_id]
        if len(new_companies) == len(companies):
            return False
        save_json(COMPANIES_FILE, new_companies)
        return True

    def next_id(self) -> int:
        return next_id(self.list_all())


class JsonProfileRepo(ProfileRepo):
    def get(self) -> ProfileDict:
        return load_json(PROFILE_FILE, {})

    def save(self, profile: ProfileDict) -> None:
        save_json(PROFILE_FILE, profile)


class JsonDraftRepo(DraftRepo):
    def list_all(self) -> list[DraftDict]:
        return load_json(DRAFTS_FILE)

    def get(self, draft_id: int) -> DraftDict | None:
        return next((d for d in self.list_all() if d["id"] == draft_id), None)

    def add(self, draft: DraftDict) -> DraftDict:
        drafts = self.list_all()
        drafts.append(draft)
        save_json(DRAFTS_FILE, drafts)
        return draft

    def next_id(self) -> int:
        return next_id(self.list_all())


class JsonResearchRepo(ResearchRepo):
    def get(self) -> ResearchDict:
        return load_json(RESEARCH_FILE, {"ideas": []})

    def save(self, data: ResearchDict) -> None:
        save_json(RESEARCH_FILE, data)
