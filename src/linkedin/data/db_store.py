"""Database (SQLModel) implementation of repository interfaces."""

import json
from datetime import datetime

from sqlmodel import Session, select

from linkedin.data.repository import CompanyRepo, ContactRepo, DraftRepo, ProfileRepo, ResearchRepo
from linkedin.models.base import Activity, Company, Contact, Draft, Profile, Research, get_session
from linkedin.types import CompanyDict, ContactDict, DraftDict, ProfileDict, ResearchDict


def _contact_to_dict(contact: Contact) -> ContactDict:
    """Convert a Contact model to a ContactDict."""
    activities = []
    for a in contact.activities:
        activities.append({
            "date": a.date.isoformat() if a.date else "",
            "type": a.type,
            "note": a.note,
        })
    return {
        "id": contact.id,
        "name": contact.name,
        "title": contact.title,
        "company": contact.company,
        "linkedin_url": contact.linkedin_url,
        "notes": contact.notes,
        "status": contact.status,
        "created_at": contact.created_at.isoformat() if contact.created_at else "",
        "last_contact": contact.last_contact.isoformat() if contact.last_contact else None,
        "follow_up_date": contact.follow_up_date,
        "company_id": contact.company_id,
        "email": contact.email,
        "source": contact.source,
        "referral_contact_id": contact.referral_contact_id,
        "activities": activities,
    }


def _company_to_dict(company: Company) -> CompanyDict:
    """Convert a Company model to a CompanyDict."""
    key_people = json.loads(company.key_people_to_find) if company.key_people_to_find else []
    return {
        "id": company.id,
        "name": company.name,
        "industry": company.industry,
        "size": company.size,
        "linkedin_url": company.linkedin_url,
        "website": company.website,
        "why_target": company.why_target,
        "key_people_to_find": key_people,
        "priority": company.priority,
        "notes": company.notes,
        "created_at": company.created_at.isoformat() if company.created_at else "",
    }


def _draft_to_dict(draft: Draft) -> DraftDict:
    """Convert a Draft model to a DraftDict."""
    result: DraftDict = {
        "id": draft.id,
        "contact_id": draft.contact_id,
        "type": draft.type,
        "content": draft.content,
        "created_at": draft.created_at.isoformat() if draft.created_at else "",
    }
    if draft.target_contact_id:
        result["target_contact_id"] = draft.target_contact_id
    if draft.topic:
        result["topic"] = draft.topic
    return result


def _profile_to_dict(profile: Profile) -> ProfileDict:
    """Convert a Profile model to a ProfileDict."""
    return {
        "name": profile.name,
        "headline": profile.headline,
        "target_role": profile.target_role,
        "skills": profile.skills,
        "experience_summary": profile.experience_summary,
        "unique_value": profile.unique_value,
        "industries": profile.industries,
        "location": profile.location,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else "",
    }


class DbContactRepo(ContactRepo):
    def __init__(self, engine=None):
        self._engine = engine

    def _session(self) -> Session:
        return get_session(self._engine)

    def list_all(self) -> list[ContactDict]:
        with self._session() as session:
            contacts = session.exec(select(Contact)).all()
            return [_contact_to_dict(c) for c in contacts]

    def get(self, contact_id: int) -> ContactDict | None:
        with self._session() as session:
            contact = session.get(Contact, contact_id)
            if not contact:
                return None
            return _contact_to_dict(contact)

    def add(self, contact: ContactDict) -> ContactDict:
        with self._session() as session:
            db_contact = Contact(
                name=contact["name"],
                title=contact.get("title", ""),
                company=contact.get("company", ""),
                linkedin_url=contact.get("linkedin_url", ""),
                notes=contact.get("notes", ""),
                status=contact.get("status", "not_contacted"),
                company_id=contact.get("company_id"),
                email=contact.get("email", ""),
                source=contact.get("source", "linkedin_search"),
                referral_contact_id=contact.get("referral_contact_id"),
            )
            session.add(db_contact)
            session.commit()
            session.refresh(db_contact)
            contact["id"] = db_contact.id
            contact["created_at"] = db_contact.created_at.isoformat()
            return contact

    def update(self, contact: ContactDict) -> None:
        with self._session() as session:
            db_contact = session.get(Contact, contact["id"])
            if not db_contact:
                return
            db_contact.name = contact.get("name", db_contact.name)
            db_contact.title = contact.get("title", db_contact.title)
            db_contact.company = contact.get("company", db_contact.company)
            db_contact.linkedin_url = contact.get("linkedin_url", db_contact.linkedin_url)
            db_contact.notes = contact.get("notes", db_contact.notes)
            db_contact.status = contact.get("status", db_contact.status)
            db_contact.company_id = contact.get("company_id", db_contact.company_id)
            db_contact.email = contact.get("email", db_contact.email)
            db_contact.source = contact.get("source", db_contact.source)
            db_contact.follow_up_date = contact.get("follow_up_date", db_contact.follow_up_date)
            if contact.get("last_contact"):
                db_contact.last_contact = datetime.fromisoformat(contact["last_contact"])

            # Sync activities
            for activity_dict in contact.get("activities", []):
                existing_dates = {a.date.isoformat() for a in db_contact.activities}
                if activity_dict.get("date") not in existing_dates:
                    activity = Activity(
                        contact_id=contact["id"],
                        date=datetime.fromisoformat(activity_dict["date"]),
                        type=activity_dict.get("type", ""),
                        note=activity_dict.get("note", ""),
                    )
                    session.add(activity)

            session.commit()

    def delete(self, contact_id: int) -> bool:
        with self._session() as session:
            contact = session.get(Contact, contact_id)
            if not contact:
                return False
            session.delete(contact)
            session.commit()
            return True

    def next_id(self) -> int:
        with self._session() as session:
            contacts = session.exec(select(Contact)).all()
            return len(contacts) + 1

    def save_all(self, contacts: list[ContactDict]) -> None:
        with self._session() as session:
            for contact_dict in contacts:
                db_contact = Contact(
                    name=contact_dict["name"],
                    title=contact_dict.get("title", ""),
                    company=contact_dict.get("company", ""),
                    linkedin_url=contact_dict.get("linkedin_url", ""),
                    notes=contact_dict.get("notes", ""),
                    status=contact_dict.get("status", "not_contacted"),
                    company_id=contact_dict.get("company_id"),
                    email=contact_dict.get("email", ""),
                    source=contact_dict.get("source", "linkedin_search"),
                )
                session.add(db_contact)
            session.commit()


class DbCompanyRepo(CompanyRepo):
    def __init__(self, engine=None):
        self._engine = engine

    def _session(self) -> Session:
        return get_session(self._engine)

    def list_all(self) -> list[CompanyDict]:
        with self._session() as session:
            companies = session.exec(select(Company)).all()
            return [_company_to_dict(c) for c in companies]

    def get(self, company_id: int) -> CompanyDict | None:
        with self._session() as session:
            company = session.get(Company, company_id)
            if not company:
                return None
            return _company_to_dict(company)

    def add(self, company: CompanyDict) -> CompanyDict:
        with self._session() as session:
            key_people = json.dumps(company.get("key_people_to_find", []))
            db_company = Company(
                name=company["name"],
                industry=company.get("industry", ""),
                size=company.get("size", "51-200"),
                linkedin_url=company.get("linkedin_url", ""),
                website=company.get("website", ""),
                why_target=company.get("why_target", ""),
                key_people_to_find=key_people,
                priority=company.get("priority", "medium"),
                notes=company.get("notes", ""),
            )
            session.add(db_company)
            session.commit()
            session.refresh(db_company)
            company["id"] = db_company.id
            company["created_at"] = db_company.created_at.isoformat()
            return company

    def update(self, company: CompanyDict) -> None:
        with self._session() as session:
            db_company = session.get(Company, company["id"])
            if not db_company:
                return
            db_company.name = company.get("name", db_company.name)
            db_company.industry = company.get("industry", db_company.industry)
            db_company.size = company.get("size", db_company.size)
            db_company.linkedin_url = company.get("linkedin_url", db_company.linkedin_url)
            db_company.website = company.get("website", db_company.website)
            db_company.why_target = company.get("why_target", db_company.why_target)
            db_company.priority = company.get("priority", db_company.priority)
            db_company.notes = company.get("notes", db_company.notes)
            if "key_people_to_find" in company:
                db_company.key_people_to_find = json.dumps(company["key_people_to_find"])
            session.commit()

    def delete(self, company_id: int) -> bool:
        with self._session() as session:
            company = session.get(Company, company_id)
            if not company:
                return False
            session.delete(company)
            session.commit()
            return True

    def next_id(self) -> int:
        with self._session() as session:
            companies = session.exec(select(Company)).all()
            return len(companies) + 1


class DbProfileRepo(ProfileRepo):
    def __init__(self, engine=None):
        self._engine = engine

    def _session(self) -> Session:
        return get_session(self._engine)

    def get(self) -> ProfileDict:
        with self._session() as session:
            profile = session.exec(select(Profile)).first()
            if not profile:
                return {}
            return _profile_to_dict(profile)

    def save(self, profile_data: ProfileDict) -> None:
        with self._session() as session:
            profile = session.exec(select(Profile)).first()
            if not profile:
                profile = Profile()
                session.add(profile)

            profile.name = profile_data.get("name", "")
            profile.headline = profile_data.get("headline", "")
            profile.target_role = profile_data.get("target_role", "")
            profile.skills = profile_data.get("skills", "")
            profile.experience_summary = profile_data.get("experience_summary", "")
            profile.unique_value = profile_data.get("unique_value", "")
            profile.industries = profile_data.get("industries", "")
            profile.location = profile_data.get("location", "")
            profile.updated_at = datetime.now()

            session.commit()


class DbDraftRepo(DraftRepo):
    def __init__(self, engine=None):
        self._engine = engine

    def _session(self) -> Session:
        return get_session(self._engine)

    def list_all(self) -> list[DraftDict]:
        with self._session() as session:
            drafts = session.exec(select(Draft)).all()
            return [_draft_to_dict(d) for d in drafts]

    def get(self, draft_id: int) -> DraftDict | None:
        with self._session() as session:
            draft = session.get(Draft, draft_id)
            if not draft:
                return None
            return _draft_to_dict(draft)

    def add(self, draft: DraftDict) -> DraftDict:
        with self._session() as session:
            db_draft = Draft(
                contact_id=draft.get("contact_id"),
                target_contact_id=draft.get("target_contact_id"),
                type=draft.get("type", ""),
                content=draft.get("content", ""),
                topic=draft.get("topic"),
            )
            session.add(db_draft)
            session.commit()
            session.refresh(db_draft)
            draft["id"] = db_draft.id
            draft["created_at"] = db_draft.created_at.isoformat()
            return draft

    def next_id(self) -> int:
        with self._session() as session:
            drafts = session.exec(select(Draft)).all()
            return len(drafts) + 1


class DbResearchRepo(ResearchRepo):
    def __init__(self, engine=None):
        self._engine = engine

    def _session(self) -> Session:
        return get_session(self._engine)

    def get(self) -> ResearchDict:
        with self._session() as session:
            research = session.exec(select(Research)).first()
            if not research:
                return {"ideas": []}
            return json.loads(research.data_json)

    def save(self, data: ResearchDict) -> None:
        with self._session() as session:
            research = session.exec(select(Research)).first()
            if not research:
                research = Research()
                session.add(research)

            research.data_json = json.dumps(data, default=str)
            research.updated_at = datetime.now()
            session.commit()
