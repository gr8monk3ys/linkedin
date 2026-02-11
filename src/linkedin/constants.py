"""Enums and constant mappings for LinkedIn CLI."""

from enum import Enum


class ContactStatus(str, Enum):
    NOT_CONTACTED = "not_contacted"
    CONNECTION_SENT = "connection_sent"
    CONNECTED = "connected"
    MESSAGED = "messaged"
    RESPONDED = "responded"
    CALL_SCHEDULED = "call_scheduled"
    REJECTED = "rejected"
    HIRED = "hired"


class CompanyPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CompanySize(str, Enum):
    TINY = "1-10"
    SMALL = "11-50"
    MEDIUM = "51-200"
    MEDIUM_LARGE = "201-500"
    LARGE = "501-1000"
    VERY_LARGE = "1001-5000"
    ENTERPRISE = "5000+"


class ContactSource(str, Enum):
    LINKEDIN_SEARCH = "linkedin_search"
    REFERRAL = "referral"
    EVENT = "event"
    INMAIL = "inmail"
    OTHER = "other"


class DraftType(str, Enum):
    CONNECTION = "connection"
    MESSAGE = "message"
    INTRO_REQUEST = "intro_request"
    THANK_YOU = "thank_you"
    FOLLOW_UP_1 = "follow_up_1"
    FOLLOW_UP_2 = "follow_up_2"
    FOLLOW_UP_3 = "follow_up_3"
    POST_STORY = "post_story"
    POST_LISTICLE = "post_listicle"
    POST_CONTRARIAN = "post_contrarian"
    POST_HOW_TO = "post_how_to"


CONTACT_STATUSES = [s.value for s in ContactStatus]
COMPANY_PRIORITIES = [p.value for p in CompanyPriority]
COMPANY_SIZES = [s.value for s in CompanySize]
CONTACT_SOURCES = [s.value for s in ContactSource]

STATUS_EMOJI = {
    ContactStatus.NOT_CONTACTED: "⚪",
    ContactStatus.CONNECTION_SENT: "📤",
    ContactStatus.CONNECTED: "🤝",
    ContactStatus.MESSAGED: "💬",
    ContactStatus.RESPONDED: "✉️",
    ContactStatus.CALL_SCHEDULED: "📅",
    ContactStatus.REJECTED: "❌",
    ContactStatus.HIRED: "🎉",
}

PRIORITY_EMOJI = {
    CompanyPriority.HIGH: "🔴",
    CompanyPriority.MEDIUM: "🟡",
    CompanyPriority.LOW: "🟢",
}

ACTIVITY_EMOJI = {
    "connection_sent": "📤",
    "connected": "🤝",
    "messaged": "💬",
    "responded": "✉️",
    "call_scheduled": "📅",
    "note_added": "📝",
}

PIPELINE_DISPLAY = [
    (ContactStatus.NOT_CONTACTED, "⚪ Not Contacted"),
    (ContactStatus.CONNECTION_SENT, "📤 Connection Sent"),
    (ContactStatus.CONNECTED, "🤝 Connected"),
    (ContactStatus.MESSAGED, "💬 Messaged"),
    (ContactStatus.RESPONDED, "✉️ Responded"),
    (ContactStatus.CALL_SCHEDULED, "📅 Call Scheduled"),
    (ContactStatus.HIRED, "🎉 Hired!"),
]

DASHBOARD_PIPELINE = [
    (ContactStatus.NOT_CONTACTED, "⚪ Not Contacted"),
    (ContactStatus.CONNECTION_SENT, "📤 Pending"),
    (ContactStatus.CONNECTED, "🤝 Connected"),
    (ContactStatus.MESSAGED, "💬 Messaged"),
    (ContactStatus.RESPONDED, "✉️ Responded"),
    (ContactStatus.CALL_SCHEDULED, "📅 Calls"),
]
