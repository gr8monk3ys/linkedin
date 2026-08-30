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

POST_EDITOR_FALLBACK = "div.ql-editor[contenteditable='true']"
FILE_INPUT = "input[type='file']"
FORM_ERROR = ".artdeco-inline-feedback--error"

#: CSS selectors keyed on LinkedIn class names — the first suspects when a run
#: reports zero results. Names match the `selector_misses` entries.
FRAGILE_SELECTORS = {
    "feed_card": FEED_CARD,
    "feed_author": FEED_AUTHOR,
    "feed_content": FEED_CONTENT,
    "search_result_card": SEARCH_RESULT_CARD,
    "search_result_name": SEARCH_RESULT_NAME,
    "profile_name": PROFILE_NAME,
    "profile_headline": PROFILE_HEADLINE,
    "profile_about": PROFILE_ABOUT_TEXT,
}
