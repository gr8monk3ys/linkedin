"""One-time migration from JSON file storage to database."""

import json
import sys
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

from linkedin.models.base import Activity, Company, Contact, Draft, Profile, Research, create_tables, get_engine

DATA_DIR = Path.home() / ".linkedin-cli"


def load_json(path: Path, default):
    """Load JSON from file or return default."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def migrate(db_url: str | None = None):
    """Migrate all JSON data to the database."""
    engine = get_engine(db_url)
    create_tables(engine)

    profile_path = DATA_DIR / "profile.json"
    contacts_path = DATA_DIR / "contacts.json"
    companies_path = DATA_DIR / "companies.json"
    drafts_path = DATA_DIR / "drafts.json"
    research_path = DATA_DIR / "research.json"

    profile_data = load_json(profile_path, {})
    contacts_data = load_json(contacts_path, [])
    companies_data = load_json(companies_path, [])
    drafts_data = load_json(drafts_path, [])
    research_data = load_json(research_path, {"ideas": []})

    # Track old ID -> new ID mappings
    company_id_map: dict[int, int] = {}
    contact_id_map: dict[int, int] = {}

    with Session(engine) as session:
        # Migrate profile
        if profile_data:
            profile = Profile(
                name=profile_data.get("name", ""),
                headline=profile_data.get("headline", ""),
                target_role=profile_data.get("target_role", ""),
                skills=profile_data.get("skills", ""),
                experience_summary=profile_data.get("experience_summary", ""),
                unique_value=profile_data.get("unique_value", ""),
                industries=profile_data.get("industries", ""),
                location=profile_data.get("location", ""),
            )
            session.add(profile)
            print(f"Migrated profile: {profile_data.get('name', 'unnamed')}")

        # Migrate companies first (contacts reference them)
        for c in companies_data:
            key_people = json.dumps(c.get("key_people_to_find", []))
            company = Company(
                name=c["name"],
                industry=c.get("industry", ""),
                size=c.get("size", "51-200"),
                linkedin_url=c.get("linkedin_url", ""),
                website=c.get("website", ""),
                why_target=c.get("why_target", ""),
                key_people_to_find=key_people,
                priority=c.get("priority", "medium"),
                notes=c.get("notes", ""),
            )
            if c.get("created_at"):
                try:
                    company.created_at = datetime.fromisoformat(c["created_at"])
                except (ValueError, TypeError):
                    pass
            session.add(company)
            session.flush()  # Get the new ID
            old_id = c.get("id")
            if old_id is not None:
                company_id_map[old_id] = company.id
        print(f"Migrated {len(companies_data)} companies")

        # Migrate contacts
        for c in contacts_data:
            old_company_id = c.get("company_id")
            new_company_id = company_id_map.get(old_company_id) if old_company_id else None

            contact = Contact(
                name=c["name"],
                title=c.get("title", ""),
                company=c.get("company", ""),
                linkedin_url=c.get("linkedin_url", ""),
                notes=c.get("notes", ""),
                status=c.get("status", "not_contacted"),
                company_id=new_company_id,
                email=c.get("email", ""),
                source=c.get("source", "linkedin_search"),
            )
            if c.get("created_at"):
                try:
                    contact.created_at = datetime.fromisoformat(c["created_at"])
                except (ValueError, TypeError):
                    pass
            if c.get("last_contact"):
                try:
                    contact.last_contact = datetime.fromisoformat(c["last_contact"])
                except (ValueError, TypeError):
                    pass
            contact.follow_up_date = c.get("follow_up_date")
            session.add(contact)
            session.flush()
            old_id = c.get("id")
            if old_id is not None:
                contact_id_map[old_id] = contact.id

            # Migrate activities for this contact
            for a in c.get("activities", []):
                activity = Activity(
                    contact_id=contact.id,
                    type=a.get("type", ""),
                    note=a.get("note", ""),
                )
                if a.get("date"):
                    try:
                        activity.date = datetime.fromisoformat(a["date"])
                    except (ValueError, TypeError):
                        pass
                session.add(activity)
        print(f"Migrated {len(contacts_data)} contacts")

        # Fix referral_contact_id mappings
        session.flush()
        for c in contacts_data:
            old_referral = c.get("referral_contact_id")
            if old_referral and old_referral in contact_id_map:
                old_id = c.get("id")
                if old_id and old_id in contact_id_map:
                    new_id = contact_id_map[old_id]
                    db_contact = session.get(Contact, new_id)
                    if db_contact:
                        db_contact.referral_contact_id = contact_id_map[old_referral]

        # Migrate drafts
        for d in drafts_data:
            old_contact_id = d.get("contact_id")
            new_contact_id = contact_id_map.get(old_contact_id) if old_contact_id else None
            old_target_id = d.get("target_contact_id")
            new_target_id = contact_id_map.get(old_target_id) if old_target_id else None

            draft = Draft(
                contact_id=new_contact_id,
                target_contact_id=new_target_id,
                type=d.get("type", ""),
                content=d.get("content", ""),
                topic=d.get("topic"),
            )
            if d.get("created_at"):
                try:
                    draft.created_at = datetime.fromisoformat(d["created_at"])
                except (ValueError, TypeError):
                    pass
            session.add(draft)
        print(f"Migrated {len(drafts_data)} drafts")

        # Migrate research
        if research_data and research_data.get("ideas"):
            research = Research(data_json=json.dumps(research_data, default=str))
            session.add(research)
            print("Migrated research data")

        session.commit()

    print("\nMigration complete!")
    print(f"  Companies: {len(companies_data)}")
    print(f"  Contacts: {len(contacts_data)}")
    print(f"  Drafts: {len(drafts_data)}")
    print(f"  Profile: {'yes' if profile_data else 'no'}")
    print(f"  Research: {'yes' if research_data.get('ideas') else 'no'}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    migrate(url)
