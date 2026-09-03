"""TypedDict definitions for LinkedIn CLI data structures."""

from typing import TypedDict


class ActivityDict(TypedDict, total=False):
    date: str
    type: str
    note: str


class TemplateUsageDict(TypedDict, total=False):
    template_id: int
    template_type: str
    used_at: str
    response_recorded: bool
    response_status: str
    response_recorded_at: str


class CampaignStateDict(TypedDict, total=False):
    name: str
    active: bool
    step_index: int
    enrolled_at: str
    completed_at: str | None
    last_advanced_at: str | None


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
    last_template_id: int | None
    last_template_type: str
    template_usage_history: list[TemplateUsageDict]
    campaign: CampaignStateDict


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
    resume_text: str


class DraftDict(TypedDict, total=False):
    id: int
    contact_id: int | None
    target_contact_id: int | None
    type: str
    content: str
    #: "ai" or "template". Absent on rows saved before provenance was recorded;
    #: readers treat absent as unknown, never as "ai".
    source: str
    topic: str
    created_at: str


class ResearchDict(TypedDict, total=False):
    ideas: list[dict]


class ApplicationEventDict(TypedDict, total=False):
    status: str
    date: str
    notes: str


class ApplicationDict(TypedDict, total=False):
    id: int
    company: str
    title: str
    url: str
    jd_text: str
    status: str          # saved|applied|phone_screen|technical|onsite|offer_received|accepted|rejected|ghosted
    applied_date: str | None
    contact_id: int | None
    notes: str
    created_at: str
    history: list[ApplicationEventDict]
    resume_variant: str
    resume_path: str
    cover_letter_path: str
    source: str          # manual|autoapply|linkedin_easy_apply


class MessageDict(TypedDict, total=False):
    sender: str          # "me" or "them"
    text: str
    timestamp: str


class ConversationDict(TypedDict, total=False):
    contact_id: int
    messages: list[MessageDict]
    updated_at: str


class ContentPostDict(TypedDict, total=False):
    id: int
    title: str
    scheduled_date: str
    status: str          # scheduled|posted|skipped
    platform: str        # "linkedin"
    draft_id: int | None
    actual_posted_date: str | None
    created_at: str


class PostDict(TypedDict, total=False):
    """A post that went out. The URN is the join key for its metrics; it can be
    missing when LinkedIn's success link could not be read back."""

    id: int
    urn: str
    text: str
    posted_at: str
    draft_id: int | None
    calendar_id: int | None


class InterviewPrepDict(TypedDict, total=False):
    application_id: int
    questions: list[str]
    star_answers: list[str]
    company_research: str
    questions_to_ask: list[str]
    updated_at: str
