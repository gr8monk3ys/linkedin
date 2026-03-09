"""TypedDict definitions for LinkedIn CLI data structures."""

from typing import Any, NamedTuple, TypedDict


class Result(NamedTuple):
    """Standardized service return type. Backward-compatible with tuple unpacking."""

    error: str | None
    data: Any = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ActivityDict(TypedDict, total=False):
    date: str
    type: str
    note: str


class ContactDict(TypedDict, total=False):
    id: int
    name: str
    title: str
    company: str
    linkedin_url: str
    notes: str
    status: str
    created_at: str
    last_contact: str | None
    follow_up_date: str | None
    company_id: int | None
    email: str
    source: str
    referral_contact_id: int | None
    activities: list[ActivityDict]


class CompanyDict(TypedDict, total=False):
    id: int
    name: str
    industry: str
    size: str
    linkedin_url: str
    website: str
    why_target: str
    key_people_to_find: list[str]
    priority: str
    notes: str
    created_at: str


class ProfileDict(TypedDict, total=False):
    name: str
    headline: str
    target_role: str
    skills: str
    experience_summary: str
    unique_value: str
    industries: str
    location: str
    updated_at: str


class DraftDict(TypedDict, total=False):
    id: int
    contact_id: int | None
    target_contact_id: int | None
    type: str
    content: str
    topic: str
    created_at: str


class TemplateDict(TypedDict, total=False):
    id: int
    name: str
    template_type: str
    content: str
    variant: str
    usage_count: int
    response_count: int
    created_at: str


class ResearchDict(TypedDict, total=False):
    ideas: list[dict]
