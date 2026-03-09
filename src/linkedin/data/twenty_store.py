"""Twenty CRM repository implementations.

Maps ContactDict/CompanyDict/DraftDict to Twenty's Person/Company/Note
objects via GraphQL API, bridging int IDs to Twenty UUIDs.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from linkedin.data.repository import CompanyRepo, ContactRepo, DraftRepo
from linkedin.types import CompanyDict, ContactDict, DraftDict

if TYPE_CHECKING:
    from linkedin.data.twenty_client import TwentyClient


# ---------------------------------------------------------------------------
# ID Mapper — bidirectional int <-> UUID mapping
# ---------------------------------------------------------------------------


class _IdMapper:
    """Persist bidirectional int <-> UUID mapping to a JSON file.

    The abstract repo interfaces use sequential int IDs, but Twenty
    uses UUID strings.  This mapper bridges the two worlds.
    """

    def __init__(self, path: Path):
        self._path = path
        self._data: dict[str, dict[str, str]] = {}  # entity_type -> {str(local_id): uuid}
        self._load()

    # -- persistence --

    def _load(self) -> None:
        if self._path.exists():
            self._data = json.loads(self._path.read_text())

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    # -- public API --

    def get_uuid(self, entity_type: str, local_id: int) -> str | None:
        return self._data.get(entity_type, {}).get(str(local_id))

    def get_local_id(self, entity_type: str, uuid: str) -> int | None:
        for lid, uid in self._data.get(entity_type, {}).items():
            if uid == uuid:
                return int(lid)
        return None

    def register(self, entity_type: str, local_id: int, uuid: str) -> None:
        self._data.setdefault(entity_type, {})[str(local_id)] = uuid
        self._save()

    def next_local_id(self, entity_type: str) -> int:
        ids = self._data.get(entity_type, {})
        if not ids:
            return 1
        return max(int(k) for k in ids) + 1

    def remove(self, entity_type: str, local_id: int) -> None:
        bucket = self._data.get(entity_type, {})
        bucket.pop(str(local_id), None)
        self._save()

    def rebuild_from_twenty(self, entity_type: str, uuid_list: list[str]) -> None:
        """Rebuild mappings from a list of Twenty UUIDs (recovery path)."""
        self._data[entity_type] = {str(i + 1): uid for i, uid in enumerate(uuid_list)}
        self._save()

    def all_mappings(self, entity_type: str) -> dict[int, str]:
        """Return {local_id: uuid} for an entity type."""
        return {int(k): v for k, v in self._data.get(entity_type, {}).items()}


# ---------------------------------------------------------------------------
# GraphQL fragments & queries
# ---------------------------------------------------------------------------

_PERSON_FIELDS = """
    id
    name { firstName lastName }
    emails { primaryEmail }
    linkedinLink { primaryLinkUrl primaryLinkLabel }
    jobTitle
    city
    companyId
    createdAt
    contactStatus
    followUpDate
    lastContactDate
    contactSource
    contactNotes
"""

_COMPANY_FIELDS = """
    id
    name
    domainName { primaryLinkUrl primaryLinkLabel }
    linkedinLink { primaryLinkUrl primaryLinkLabel }
    employees
    createdAt
    companyIndustry
    whyTarget
    companyPriority
    companyNotes
"""

_NOTE_FIELDS = """
    id
    title
    body
    createdAt
    noteTargets {
        edges {
            node {
                id
                personId
                companyId
            }
        }
    }
"""


# ---------------------------------------------------------------------------
# Helper converters
# ---------------------------------------------------------------------------


def _split_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (first, last). Extra parts go to last name."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""


def _join_name(first: str, last: str) -> str:
    return f"{first} {last}".strip()


def _person_to_contact(node: dict, mapper: _IdMapper) -> ContactDict:
    """Convert a Twenty Person node to a ContactDict."""
    name_obj = node.get("name") or {}
    emails_obj = node.get("emails") or {}
    linkedin_obj = node.get("linkedinLink") or {}
    uuid = node["id"]
    local_id = mapper.get_local_id("contact", uuid)

    contact: ContactDict = {
        "id": local_id or 0,
        "name": _join_name(name_obj.get("firstName", ""), name_obj.get("lastName", "")),
        "title": node.get("jobTitle") or "",
        "company": "",
        "linkedin_url": linkedin_obj.get("primaryLinkUrl") or "",
        "email": emails_obj.get("primaryEmail") or "",
        "notes": node.get("contactNotes") or "",
        "status": node.get("contactStatus") or "not_contacted",
        "created_at": node.get("createdAt") or "",
        "last_contact": node.get("lastContactDate"),
        "follow_up_date": node.get("followUpDate"),
        "source": node.get("contactSource") or "linkedin_search",
        "company_id": None,
        "referral_contact_id": None,
        "activities": [],
    }

    # Map company UUID back to local id
    company_uuid = node.get("companyId")
    if company_uuid:
        contact["company_id"] = mapper.get_local_id("company", company_uuid)

    return contact


def _company_node_to_dict(node: dict, mapper: _IdMapper) -> CompanyDict:
    """Convert a Twenty Company node to a CompanyDict."""
    domain_obj = node.get("domainName") or {}
    linkedin_obj = node.get("linkedinLink") or {}
    uuid = node["id"]
    local_id = mapper.get_local_id("company", uuid)

    return {
        "id": local_id or 0,
        "name": node.get("name") or "",
        "industry": node.get("companyIndustry") or "",
        "size": str(node.get("employees") or ""),
        "linkedin_url": linkedin_obj.get("primaryLinkUrl") or "",
        "website": domain_obj.get("primaryLinkUrl") or "",
        "why_target": node.get("whyTarget") or "",
        "key_people_to_find": [],
        "priority": node.get("companyPriority") or "medium",
        "notes": node.get("companyNotes") or "",
        "created_at": node.get("createdAt") or "",
    }


def _note_to_draft(node: dict, mapper: _IdMapper) -> DraftDict | None:
    """Convert a Twenty Note node to a DraftDict, or None if not a draft."""
    title = node.get("title") or ""
    if not title.startswith("[Draft:"):
        return None

    # Parse "[Draft:connection] - topic" format
    bracket_end = title.find("]")
    draft_type = title[7:bracket_end] if bracket_end > 7 else ""
    topic = ""
    if " - " in title[bracket_end:]:
        topic = title[bracket_end + 4:]  # skip "] - "

    uuid = node["id"]
    local_id = mapper.get_local_id("draft", uuid)

    # Find linked person via noteTargets
    contact_id = None
    targets = node.get("noteTargets", {}).get("edges", [])
    for edge in targets:
        person_uuid = edge["node"].get("personId")
        if person_uuid:
            contact_id = mapper.get_local_id("contact", person_uuid)
            break

    return {
        "id": local_id or 0,
        "contact_id": contact_id,
        "type": draft_type,
        "content": node.get("body") or "",
        "topic": topic,
        "created_at": node.get("createdAt") or "",
    }


# ---------------------------------------------------------------------------
# Repository implementations
# ---------------------------------------------------------------------------


class TwentyContactRepo(ContactRepo):
    def __init__(self, client: TwentyClient, mapper: _IdMapper):
        self._client = client
        self._mapper = mapper

    def list_all(self) -> list[ContactDict]:
        query = """
        query ListPeople($after: String) {
            people(paging: { first: 50, after: $after }) {
                edges { node { %s } }
                pageInfo { hasNextPage endCursor }
            }
        }
        """ % _PERSON_FIELDS
        nodes = self._client.paginate(query, {}, "people")

        # Ensure all UUIDs have local IDs
        for node in nodes:
            if self._mapper.get_local_id("contact", node["id"]) is None:
                lid = self._mapper.next_local_id("contact")
                self._mapper.register("contact", lid, node["id"])

        return [_person_to_contact(n, self._mapper) for n in nodes]

    def get(self, contact_id: int) -> ContactDict | None:
        uuid = self._mapper.get_uuid("contact", contact_id)
        if not uuid:
            return None
        query = """
        query GetPerson($id: ID!) {
            person(id: $id) { %s }
        }
        """ % _PERSON_FIELDS
        data = self._client.query(query, {"id": uuid})
        node = data.get("person")
        if not node:
            return None
        return _person_to_contact(node, self._mapper)

    def add(self, contact: ContactDict) -> ContactDict:
        first, last = _split_name(contact.get("name", ""))

        variables: dict = {
            "input": {
                "name": {"firstName": first, "lastName": last},
                "emails": {"primaryEmail": contact.get("email", "")},
                "linkedinLink": {"primaryLinkUrl": contact.get("linkedin_url", ""), "primaryLinkLabel": "LinkedIn"},
                "jobTitle": contact.get("title", ""),
                "contactStatus": contact.get("status", "not_contacted"),
                "contactSource": contact.get("source", "linkedin_search"),
                "contactNotes": contact.get("notes", ""),
            }
        }

        if contact.get("follow_up_date"):
            variables["input"]["followUpDate"] = contact["follow_up_date"]
        if contact.get("last_contact"):
            variables["input"]["lastContactDate"] = contact["last_contact"]

        # Map company local id to UUID
        if contact.get("company_id"):
            company_uuid = self._mapper.get_uuid("company", contact["company_id"])
            if company_uuid:
                variables["input"]["companyId"] = company_uuid

        mutation = """
        mutation CreatePerson($input: PersonCreateInput!) {
            createPerson(data: $input) { %s }
        }
        """ % _PERSON_FIELDS
        data = self._client.mutate(mutation, variables)
        node = data["createPerson"]

        local_id = contact.get("id") or self._mapper.next_local_id("contact")
        self._mapper.register("contact", local_id, node["id"])

        result = _person_to_contact(node, self._mapper)
        result["id"] = local_id
        result["created_at"] = node.get("createdAt", datetime.now().isoformat())
        return result

    def update(self, contact: ContactDict) -> None:
        uuid = self._mapper.get_uuid("contact", contact["id"])
        if not uuid:
            return

        update_input: dict = {}

        if "name" in contact:
            first, last = _split_name(contact["name"])
            update_input["name"] = {"firstName": first, "lastName": last}
        if "email" in contact:
            update_input["emails"] = {"primaryEmail": contact["email"]}
        if "linkedin_url" in contact:
            update_input["linkedinLink"] = {"primaryLinkUrl": contact["linkedin_url"], "primaryLinkLabel": "LinkedIn"}
        if "title" in contact:
            update_input["jobTitle"] = contact["title"]
        if "status" in contact:
            update_input["contactStatus"] = contact["status"]
        if "source" in contact:
            update_input["contactSource"] = contact["source"]
        if "notes" in contact:
            update_input["contactNotes"] = contact["notes"]
        if "follow_up_date" in contact:
            update_input["followUpDate"] = contact["follow_up_date"]
        if "last_contact" in contact:
            update_input["lastContactDate"] = contact["last_contact"]
        if "company_id" in contact and contact["company_id"]:
            company_uuid = self._mapper.get_uuid("company", contact["company_id"])
            if company_uuid:
                update_input["companyId"] = company_uuid

        if not update_input:
            return

        mutation = """
        mutation UpdatePerson($id: ID!, $input: PersonUpdateInput!) {
            updatePerson(id: $id, data: $input) { id }
        }
        """
        self._client.mutate(mutation, {"id": uuid, "input": update_input})

    def delete(self, contact_id: int) -> bool:
        uuid = self._mapper.get_uuid("contact", contact_id)
        if not uuid:
            return False
        mutation = """
        mutation DeletePerson($id: ID!) {
            deletePerson(id: $id) { id }
        }
        """
        self._client.mutate(mutation, {"id": uuid})
        self._mapper.remove("contact", contact_id)
        return True

    def next_id(self) -> int:
        return self._mapper.next_local_id("contact")

    def save_all(self, contacts: list[ContactDict]) -> None:
        for contact in contacts:
            if contact.get("id") and self._mapper.get_uuid("contact", contact["id"]):
                self.update(contact)
            else:
                self.add(contact)


class TwentyCompanyRepo(CompanyRepo):
    def __init__(self, client: TwentyClient, mapper: _IdMapper):
        self._client = client
        self._mapper = mapper

    def list_all(self) -> list[CompanyDict]:
        query = """
        query ListCompanies($after: String) {
            companies(paging: { first: 50, after: $after }) {
                edges { node { %s } }
                pageInfo { hasNextPage endCursor }
            }
        }
        """ % _COMPANY_FIELDS
        nodes = self._client.paginate(query, {}, "companies")

        for node in nodes:
            if self._mapper.get_local_id("company", node["id"]) is None:
                lid = self._mapper.next_local_id("company")
                self._mapper.register("company", lid, node["id"])

        return [_company_node_to_dict(n, self._mapper) for n in nodes]

    def get(self, company_id: int) -> CompanyDict | None:
        uuid = self._mapper.get_uuid("company", company_id)
        if not uuid:
            return None
        query = """
        query GetCompany($id: ID!) {
            company(id: $id) { %s }
        }
        """ % _COMPANY_FIELDS
        data = self._client.query(query, {"id": uuid})
        node = data.get("company")
        if not node:
            return None
        return _company_node_to_dict(node, self._mapper)

    def add(self, company: CompanyDict) -> CompanyDict:
        employees = 0
        size_str = company.get("size", "")
        if size_str and "-" in size_str:
            try:
                employees = int(size_str.split("-")[0])
            except ValueError:
                pass
        elif size_str.endswith("+"):
            try:
                employees = int(size_str.rstrip("+"))
            except ValueError:
                pass

        variables: dict = {
            "input": {
                "name": company.get("name", ""),
                "domainName": {"primaryLinkUrl": company.get("website", ""), "primaryLinkLabel": "Website"},
                "linkedinLink": {"primaryLinkUrl": company.get("linkedin_url", ""), "primaryLinkLabel": "LinkedIn"},
                "employees": employees,
                "companyIndustry": company.get("industry", ""),
                "whyTarget": company.get("why_target", ""),
                "companyPriority": company.get("priority", "medium"),
                "companyNotes": company.get("notes", ""),
            }
        }

        mutation = """
        mutation CreateCompany($input: CompanyCreateInput!) {
            createCompany(data: $input) { %s }
        }
        """ % _COMPANY_FIELDS
        data = self._client.mutate(mutation, variables)
        node = data["createCompany"]

        local_id = company.get("id") or self._mapper.next_local_id("company")
        self._mapper.register("company", local_id, node["id"])

        result = _company_node_to_dict(node, self._mapper)
        result["id"] = local_id
        result["created_at"] = node.get("createdAt", datetime.now().isoformat())
        # Preserve key_people_to_find (stored locally, not in Twenty)
        result["key_people_to_find"] = company.get("key_people_to_find", [])
        return result

    def update(self, company: CompanyDict) -> None:
        uuid = self._mapper.get_uuid("company", company["id"])
        if not uuid:
            return

        update_input: dict = {}

        if "name" in company:
            update_input["name"] = company["name"]
        if "website" in company:
            update_input["domainName"] = {"primaryLinkUrl": company["website"], "primaryLinkLabel": "Website"}
        if "linkedin_url" in company:
            update_input["linkedinLink"] = {"primaryLinkUrl": company["linkedin_url"], "primaryLinkLabel": "LinkedIn"}
        if "industry" in company:
            update_input["companyIndustry"] = company["industry"]
        if "why_target" in company:
            update_input["whyTarget"] = company["why_target"]
        if "priority" in company:
            update_input["companyPriority"] = company["priority"]
        if "notes" in company:
            update_input["companyNotes"] = company["notes"]
        if "size" in company:
            size_str = company["size"]
            employees = 0
            if size_str and "-" in size_str:
                try:
                    employees = int(size_str.split("-")[0])
                except ValueError:
                    pass
            elif size_str and size_str.endswith("+"):
                try:
                    employees = int(size_str.rstrip("+"))
                except ValueError:
                    pass
            update_input["employees"] = employees

        if not update_input:
            return

        mutation = """
        mutation UpdateCompany($id: ID!, $input: CompanyUpdateInput!) {
            updateCompany(id: $id, data: $input) { id }
        }
        """
        self._client.mutate(mutation, {"id": uuid, "input": update_input})

    def delete(self, company_id: int) -> bool:
        uuid = self._mapper.get_uuid("company", company_id)
        if not uuid:
            return False
        mutation = """
        mutation DeleteCompany($id: ID!) {
            deleteCompany(id: $id) { id }
        }
        """
        self._client.mutate(mutation, {"id": uuid})
        self._mapper.remove("company", company_id)
        return True

    def next_id(self) -> int:
        return self._mapper.next_local_id("company")


class TwentyDraftRepo(DraftRepo):
    """Store drafts as Twenty Notes with a title convention: [Draft:{type}] - {topic}."""

    def __init__(self, client: TwentyClient, mapper: _IdMapper):
        self._client = client
        self._mapper = mapper

    def _build_title(self, draft: DraftDict) -> str:
        title = f"[Draft:{draft.get('type', 'message')}]"
        topic = draft.get("topic", "")
        if topic:
            title += f" - {topic}"
        return title

    def list_all(self) -> list[DraftDict]:
        query = """
        query ListNotes($after: String) {
            notes(
                filter: { title: { startsWith: "[Draft:" } }
                paging: { first: 50, after: $after }
            ) {
                edges { node { %s } }
                pageInfo { hasNextPage endCursor }
            }
        }
        """ % _NOTE_FIELDS
        nodes = self._client.paginate(query, {}, "notes")

        results: list[DraftDict] = []
        for node in nodes:
            if self._mapper.get_local_id("draft", node["id"]) is None:
                lid = self._mapper.next_local_id("draft")
                self._mapper.register("draft", lid, node["id"])
            draft = _note_to_draft(node, self._mapper)
            if draft:
                results.append(draft)
        return results

    def get(self, draft_id: int) -> DraftDict | None:
        uuid = self._mapper.get_uuid("draft", draft_id)
        if not uuid:
            return None
        query = """
        query GetNote($id: ID!) {
            note(id: $id) { %s }
        }
        """ % _NOTE_FIELDS
        data = self._client.query(query, {"id": uuid})
        node = data.get("note")
        if not node:
            return None
        return _note_to_draft(node, self._mapper)

    def add(self, draft: DraftDict) -> DraftDict:
        title = self._build_title(draft)
        variables: dict = {
            "input": {
                "title": title,
                "body": draft.get("content", ""),
            }
        }

        mutation = """
        mutation CreateNote($input: NoteCreateInput!) {
            createNote(data: $input) { %s }
        }
        """ % _NOTE_FIELDS
        data = self._client.mutate(mutation, variables)
        node = data["createNote"]

        local_id = draft.get("id") or self._mapper.next_local_id("draft")
        self._mapper.register("draft", local_id, node["id"])

        # Link to person via noteTarget if contact_id provided
        contact_id = draft.get("contact_id")
        if contact_id:
            person_uuid = self._mapper.get_uuid("contact", contact_id)
            if person_uuid:
                link_mutation = """
                mutation CreateNoteTarget($input: NoteTargetCreateInput!) {
                    createNoteTarget(data: $input) { id }
                }
                """
                self._client.mutate(link_mutation, {
                    "input": {"noteId": node["id"], "personId": person_uuid}
                })

        result = _note_to_draft(node, self._mapper) or {}
        result["id"] = local_id
        result["contact_id"] = contact_id
        result["created_at"] = node.get("createdAt", datetime.now().isoformat())
        return result

    def next_id(self) -> int:
        return self._mapper.next_local_id("draft")
