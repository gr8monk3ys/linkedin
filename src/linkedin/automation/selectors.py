"""Every LinkedIn selector this package depends on, in one place.

LinkedIn changes its markup without notice. When it does, the failure is silent
by nature: a locator matches nothing, the calling method returns 0 / [] / False,
and the run looks like a quiet day. Keeping the selectors here means a breakage
is fixed in one file, and `LinkedInPage.selector_misses` names which of these
stopped matching so the CLI can say so out loud.

Role-based locators are preferred over CSS: accessible names survive class-name
churn. The CSS constants are the ones with no accessible equivalent.
"""

import re

# --- Role/label locators (resilient: keyed on accessible names) --------------
LOGIN_EMAIL_LABEL = "Email or phone"
LOGIN_PASSWORD_LABEL = "Password"
SIGN_IN_BUTTON = "Sign in"

CONNECT_BUTTON = "Connect"
MORE_BUTTON = "More"
CONNECT_MENU_ITEM = "Connect"
ADD_NOTE_BUTTON = "Add a note"
ADD_NOTE_TEXTBOX = "Add a note"
SEND_BUTTON = "Send"

MESSAGE_BUTTON = "Message"
MESSAGE_TEXTBOX = "Write a message"

START_POST_BUTTON = re.compile("Start a post", re.I)
POST_EDITOR_TEXTBOX = re.compile("Text editor", re.I)
POST_SUBMIT_BUTTON = re.compile(r"^Post$", re.I)

LIKE_BUTTON = re.compile(r"^React Like|^Like\b", re.I)
COMMENT_BUTTON = re.compile(r"^Comment\b", re.I)
COMMENT_TEXTBOX = re.compile("Add a comment", re.I)
COMMENT_SUBMIT_BUTTON = re.compile(r"^Post\b", re.I)

EDIT_INTRO_BUTTON = re.compile("Edit intro", re.I)
HEADLINE_FIELD_LABEL = re.compile("Headline", re.I)
EDIT_ABOUT_BUTTON = re.compile("Edit about", re.I)
SAVE_BUTTON = re.compile(r"^Save$", re.I)

EASY_APPLY_BUTTON = re.compile("Easy Apply", re.I)
EASY_APPLY_SUBMIT_BUTTON = re.compile("Submit application", re.I)
EASY_APPLY_NEXT_BUTTON = re.compile("Next|Review|Continue", re.I)

# --- CSS locators (fragile: keyed on LinkedIn class names) -------------------
# These are the ones that break on a markup change. `FRAGILE_SELECTORS` names
# them for the doctor output so a human knows where to look first.
FEED_CARD = "div.feed-shared-update-v2"
FEED_AUTHOR = ".update-components-actor__name span[aria-hidden='true']"
FEED_AUTHOR_HEADLINE = ".update-components-actor__description span[aria-hidden='true']"
FEED_CONTENT = ".feed-shared-update-v2__description, .update-components-text"

SEARCH_RESULT_CARD = ".reusable-search__result-container"
SEARCH_RESULT_NAME = "a.app-aware-link span[aria-hidden='true']"
SEARCH_RESULT_HEADLINE = ".entity-result__primary-subtitle"
SEARCH_RESULT_LINK = "a.app-aware-link"

PROFILE_NAME = "h1.text-heading-xlarge"
PROFILE_HEADLINE = ".text-body-medium.break-words"
PROFILE_LOCATION = ".text-body-small.inline.t-black--light.break-words"
PROFILE_ABOUT_SECTION = "#about"
PROFILE_ABOUT_TEXT = "#about ~ div .visually-hidden"
PROFILE_ABOUT_EDIT_FALLBACK = (
    "xpath=ancestor::section//button[contains(@aria-label, 'about') "
    "or contains(@aria-label, 'About')]"
)

# Messaging pane. The list is virtualized and lazy-loaded, which makes these the
# likeliest of all the CSS here to need a second pass after a markup change.
THREAD_CARD = "li.msg-conversation-listitem"
THREAD_NAME = ".msg-conversation-listitem__participant-names span"
THREAD_SNIPPET = ".msg-conversation-card__message-snippet"
THREAD_TIMESTAMP = "time.msg-conversation-listitem__time-stamp"
THREAD_LINK = "a.msg-conversation-listitem__link"
THREAD_UNREAD_BADGE = ".msg-conversation-card__unread-count"

#: LinkedIn prefixes the snippet with "You:" when the last message is the user's
#: own. That prefix is the only thing distinguishing a reply from an echo of the
#: outbound message we sent, so the whole inbound signal rests on it.
THREAD_OWN_MESSAGE_PREFIX = re.compile(r"^\s*you\s*:", re.I)

# Sent-invitation manager.
INVITATION_CARD = "li.invitation-card"
INVITATION_NAME = ".invitation-card__title"
INVITATION_LINK = "a.invitation-card__link"
#: An explicit empty state is what tells a genuinely empty invitation list apart
#: from a selector that stopped matching. Without it the reader cannot return []
#: safely, because the caller reads [] as "every invitation was accepted".
INVITATION_EMPTY_STATE = ".mn-invitation-manager__empty-state, .artdeco-empty-state"

# Job search results.
JOB_CARD = "div.job-card-container"
JOB_TITLE = "a.job-card-list__title, .job-card-list__title--link"
JOB_COMPANY = ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle"
JOB_LOCATION = ".job-card-container__metadata-item"
JOB_LINK = "a.job-card-list__title, a.job-card-container__link"
JOB_EASY_APPLY = ".job-card-container__easy-apply-label, li.job-card-container__footer-item"

POST_EDITOR_FALLBACK = "div.ql-editor[contenteditable='true']"
FILE_INPUT = "input[type='file']"
FORM_ERROR = ".artdeco-inline-feedback--error"

#: Selectors whose absence cannot be told apart from an empty page — the first
#: suspects when a run reports zero results. Names match the `selector_misses`
#: entries. Mostly CSS keyed on LinkedIn class names, plus the accessible-name
#: patterns that a relabelled button would break just as silently.
FRAGILE_SELECTORS = {
    "feed_card": FEED_CARD,
    "like_button": LIKE_BUTTON.pattern,
    "feed_author": FEED_AUTHOR,
    "feed_content": FEED_CONTENT,
    "search_result_card": SEARCH_RESULT_CARD,
    "search_result_name": SEARCH_RESULT_NAME,
    "profile_name": PROFILE_NAME,
    "profile_headline": PROFILE_HEADLINE,
    "profile_about": PROFILE_ABOUT_TEXT,
    "thread_card": THREAD_CARD,
    "thread_name": THREAD_NAME,
    "invitation_card": INVITATION_CARD,
    "invitation_name": INVITATION_NAME,
    "job_card": JOB_CARD,
    "job_title": JOB_TITLE,
}
