"""JSON file stores. Each repo is constructed with the file it owns."""

import json
import os
import tempfile
from pathlib import Path

from linkedin.types import (
    ApplicationDict,
    CompanyDict,
    ContactDict,
    ContentPostDict,
    ConversationDict,
    DraftDict,
    InterviewPrepDict,
    ProfileDict,
    ResearchDict,
)


def load_json(path: Path, default=None):
    if default is None:
        default = []
    if path.exists():
        return json.loads(path.read_text())
    return default


def save_json(path: Path, data):
    """Write `data` to `path` atomically.

    Every mutation rewrites the whole file, so a plain write that is interrupted
    (crash, Ctrl-C, full disk) leaves a truncated file and loses every record.
    Serialize first, write to a sibling temp file, fsync, then rename — on POSIX
    the rename is atomic, so readers see either the old file or the new one.
    """
    payload = json.dumps(data, indent=2, default=str)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


class _JsonRepo:
    """A store over one JSON file, given at construction."""

    def __init__(self, path: Path):
        self.path = path


def _next_id(items: list[dict]) -> int:
    """Return the next integer ID, resilient to deletions and sparse IDs."""
    max_id = 0
    for item in items:
        raw_id = item.get("id")
        if isinstance(raw_id, int):
            max_id = max(max_id, raw_id)
        elif isinstance(raw_id, str) and raw_id.isdigit():
            max_id = max(max_id, int(raw_id))
    return max_id + 1


class JsonContactRepo(_JsonRepo):
    def list_all(self) -> list[ContactDict]:
        return load_json(self.path)

    def get(self, contact_id: int) -> ContactDict | None:
        return next((c for c in self.list_all() if c["id"] == contact_id), None)

    def add(self, contact: ContactDict) -> ContactDict:
        contacts = self.list_all()
        contacts.append(contact)
        save_json(self.path, contacts)
        return contact

    def update(self, contact: ContactDict) -> None:
        contacts = self.list_all()
        for i, c in enumerate(contacts):
            if c["id"] == contact["id"]:
                contacts[i] = contact
                break
        save_json(self.path, contacts)

    def delete(self, contact_id: int) -> bool:
        contacts = self.list_all()
        new_contacts = [c for c in contacts if c["id"] != contact_id]
        if len(new_contacts) == len(contacts):
            return False
        save_json(self.path, new_contacts)
        return True

    def next_id(self) -> int:
        contacts = self.list_all()
        return _next_id(contacts)

    def save_all(self, contacts: list[ContactDict]) -> None:
        save_json(self.path, contacts)


class JsonCompanyRepo(_JsonRepo):
    def list_all(self) -> list[CompanyDict]:
        return load_json(self.path)

    def get(self, company_id: int) -> CompanyDict | None:
        return next((c for c in self.list_all() if c["id"] == company_id), None)

    def add(self, company: CompanyDict) -> CompanyDict:
        companies = self.list_all()
        companies.append(company)
        save_json(self.path, companies)
        return company

    def update(self, company: CompanyDict) -> None:
        companies = self.list_all()
        for i, c in enumerate(companies):
            if c["id"] == company["id"]:
                companies[i] = company
                break
        save_json(self.path, companies)

    def delete(self, company_id: int) -> bool:
        companies = self.list_all()
        new_companies = [c for c in companies if c["id"] != company_id]
        if len(new_companies) == len(companies):
            return False
        save_json(self.path, new_companies)
        return True

    def next_id(self) -> int:
        companies = self.list_all()
        return _next_id(companies)


class JsonProfileRepo(_JsonRepo):
    def get(self) -> ProfileDict:
        return load_json(self.path, {})

    def save(self, profile: ProfileDict) -> None:
        save_json(self.path, profile)


class JsonDraftRepo(_JsonRepo):
    def list_all(self) -> list[DraftDict]:
        return load_json(self.path)

    def get(self, draft_id: int) -> DraftDict | None:
        return next((d for d in self.list_all() if d["id"] == draft_id), None)

    def add(self, draft: DraftDict) -> DraftDict:
        drafts = self.list_all()
        drafts.append(draft)
        save_json(self.path, drafts)
        return draft

    def next_id(self) -> int:
        drafts = self.list_all()
        return _next_id(drafts)

    def delete(self, draft_id: int) -> bool:
        drafts = self.list_all()
        remaining = [d for d in drafts if d["id"] != draft_id]
        if len(remaining) == len(drafts):
            return False
        save_json(self.path, remaining)
        return True


class JsonResearchRepo(_JsonRepo):
    def get(self) -> ResearchDict:
        return load_json(self.path, {"ideas": []})

    def save(self, data: ResearchDict) -> None:
        save_json(self.path, data)


class JsonApplicationRepo(_JsonRepo):
    def list_all(self) -> list[ApplicationDict]:
        return load_json(self.path)

    def get(self, application_id: int) -> ApplicationDict | None:
        return next((a for a in self.list_all() if a["id"] == application_id), None)

    def add(self, application: ApplicationDict) -> ApplicationDict:
        apps = self.list_all()
        apps.append(application)
        save_json(self.path, apps)
        return application

    def update(self, application: ApplicationDict) -> None:
        apps = self.list_all()
        for i, a in enumerate(apps):
            if a["id"] == application["id"]:
                apps[i] = application
                break
        save_json(self.path, apps)

    def delete(self, application_id: int) -> bool:
        apps = self.list_all()
        new_apps = [a for a in apps if a["id"] != application_id]
        if len(new_apps) == len(apps):
            return False
        save_json(self.path, new_apps)
        return True

    def next_id(self) -> int:
        return _next_id(self.list_all())


class JsonConversationRepo(_JsonRepo):
    def list_all(self) -> list[ConversationDict]:
        return load_json(self.path)

    def get_by_contact(self, contact_id: int) -> ConversationDict | None:
        return next((c for c in self.list_all() if c["contact_id"] == contact_id), None)

    def upsert(self, conversation: ConversationDict) -> None:
        convs = self.list_all()
        for i, c in enumerate(convs):
            if c["contact_id"] == conversation["contact_id"]:
                convs[i] = conversation
                save_json(self.path, convs)
                return
        convs.append(conversation)
        save_json(self.path, convs)


class JsonCalendarRepo(_JsonRepo):
    def list_all(self) -> list[ContentPostDict]:
        return load_json(self.path)

    def get(self, post_id: int) -> ContentPostDict | None:
        return next((p for p in self.list_all() if p["id"] == post_id), None)

    def add(self, post: ContentPostDict) -> ContentPostDict:
        posts = self.list_all()
        posts.append(post)
        save_json(self.path, posts)
        return post

    def update(self, post: ContentPostDict) -> None:
        posts = self.list_all()
        for i, p in enumerate(posts):
            if p["id"] == post["id"]:
                posts[i] = post
                break
        save_json(self.path, posts)

    def delete(self, post_id: int) -> bool:
        posts = self.list_all()
        new_posts = [p for p in posts if p["id"] != post_id]
        if len(new_posts) == len(posts):
            return False
        save_json(self.path, new_posts)
        return True

    def next_id(self) -> int:
        return _next_id(self.list_all())


class JsonInterviewPrepRepo(_JsonRepo):
    def get_by_application(self, application_id: int) -> InterviewPrepDict | None:
        all_prep = load_json(self.path)
        return next((p for p in all_prep if p["application_id"] == application_id), None)

    def upsert(self, prep: InterviewPrepDict) -> None:
        all_prep = load_json(self.path)
        for i, p in enumerate(all_prep):
            if p["application_id"] == prep["application_id"]:
                all_prep[i] = prep
                save_json(self.path, all_prep)
                return
        all_prep.append(prep)
        save_json(self.path, all_prep)
