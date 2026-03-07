"""SQLModel table definitions and database engine setup."""

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{Path.home() / '.linkedin-cli' / 'linkedin.db'}",
)

_engine = None


def get_engine(url: str | None = None):
    """Get or create database engine."""
    global _engine
    if _engine is None or url is not None:
        db_url = url or DATABASE_URL
        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

            # Ensure parent directory exists for SQLite
            if ":///" in db_url and not db_url.endswith(":memory:"):
                db_path = db_url.split("///", 1)[1]
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        engine = create_engine(db_url, connect_args=connect_args)

        # Enable WAL mode for SQLite for better concurrency
        if db_url.startswith("sqlite") and ":memory:" not in db_url:

            @event.listens_for(engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        if url is None:
            _engine = engine
        return engine
    return _engine


def get_session(engine=None) -> Session:
    """Create a new database session."""
    return Session(engine or get_engine())


def create_tables(engine=None):
    """Create all tables."""
    SQLModel.metadata.create_all(engine or get_engine())


def reset_engine():
    """Reset the cached engine (useful for testing)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


# =============================================================================
# Models
# =============================================================================


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    id: int | None = Field(default=None, primary_key=True)
    name: str = ""
    headline: str = ""
    target_role: str = ""
    skills: str = ""
    experience_summary: str = ""
    unique_value: str = ""
    industries: str = ""
    location: str = ""
    updated_at: datetime = Field(default_factory=datetime.now)


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    industry: str = ""
    size: str = "51-200"
    linkedin_url: str = ""
    website: str = ""
    why_target: str = ""
    key_people_to_find: str = ""  # JSON-encoded list
    priority: str = "medium"
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

    contacts: list["Contact"] = Relationship(back_populates="company_rel")


class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    title: str = ""
    company: str = ""
    linkedin_url: str = ""
    notes: str = ""
    status: str = "not_contacted"
    created_at: datetime = Field(default_factory=datetime.now)
    last_contact: datetime | None = None
    follow_up_date: str | None = None
    company_id: int | None = Field(default=None, foreign_key="companies.id")
    email: str = ""
    source: str = "linkedin_search"
    referral_contact_id: int | None = Field(default=None, foreign_key="contacts.id")

    company_rel: Company | None = Relationship(back_populates="contacts")
    activities: list["Activity"] = Relationship(back_populates="contact")


class Activity(SQLModel, table=True):
    __tablename__ = "activities"

    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contacts.id")
    date: datetime = Field(default_factory=datetime.now)
    type: str = ""
    note: str = ""

    contact: Contact | None = Relationship(back_populates="activities")


class Draft(SQLModel, table=True):
    __tablename__ = "drafts"

    id: int | None = Field(default=None, primary_key=True)
    contact_id: int | None = None
    target_contact_id: int | None = None
    type: str = ""
    content: str = ""
    topic: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class Research(SQLModel, table=True):
    __tablename__ = "research"

    id: int | None = Field(default=None, primary_key=True)
    data_json: str = '{"ideas": []}'  # JSON-encoded research data
    updated_at: datetime = Field(default_factory=datetime.now)


# =============================================================================
# Phase 4 Models
# =============================================================================


class OutreachEvent(SQLModel, table=True):
    """Tracks outreach events for analytics."""

    __tablename__ = "outreach_events"

    id: int | None = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contacts.id")
    event_type: str = ""  # connection_sent, message_sent, response_received, etc.
    draft_type: str = ""  # connection, message, follow_up, etc.
    occurred_at: datetime = Field(default_factory=datetime.now)
    notes: str = ""


class JobPosting(SQLModel, table=True):
    """Manually tracked job postings for market intelligence."""

    __tablename__ = "job_postings"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    company: str = ""
    location: str = ""
    salary_min: int | None = None
    salary_max: int | None = None
    skills_required: str = ""  # comma-separated
    url: str = ""
    source: str = ""
    posted_date: str | None = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.now)


class MarketInsight(SQLModel, table=True):
    """Cached market insights from AI analysis."""

    __tablename__ = "market_insights"

    id: int | None = Field(default=None, primary_key=True)
    insight_type: str = ""  # salary, trend, skill_demand
    data_json: str = "{}"
    created_at: datetime = Field(default_factory=datetime.now)


class ProfileSuggestion(SQLModel, table=True):
    """AI-generated profile optimization suggestions."""

    __tablename__ = "profile_suggestions"

    id: int | None = Field(default=None, primary_key=True)
    suggestion_type: str = ""  # headline, about, skills, experience
    original: str = ""
    suggested: str = ""
    accepted: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class Template(SQLModel, table=True):
    """Reusable message templates with placeholders."""

    __tablename__ = "templates"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    template_type: str = ""  # connection, message, follow_up
    content: str = ""  # content with {{placeholders}}
    variant: str = "A"  # A/B variant
    usage_count: int = 0
    response_count: int = 0
    created_at: datetime = Field(default_factory=datetime.now)


class TemplateUsage(SQLModel, table=True):
    """Tracks template usage for A/B testing."""

    __tablename__ = "template_usages"

    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="templates.id")
    contact_id: int | None = Field(default=None, foreign_key="contacts.id")
    got_response: bool = False
    used_at: datetime = Field(default_factory=datetime.now)
