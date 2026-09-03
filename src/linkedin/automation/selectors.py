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
#: The login fields are addressed by autocomplete attribute, not accessible
#: name. Measured 2026-08-30: "Email or phone" matches two inputs and "Password"
#: matches four (the "Show password" toggle shares the name), and Playwright
#: raises on an action against a multi-match locator. The autocomplete tokens are
#: a browser standard rather than LinkedIn markup, so they are the sturdier key.
LOGIN_EMAIL_INPUT = "input[autocomplete='username']"
LOGIN_PASSWORD_INPUT = "input[autocomplete='current-password']"
LOGIN_EMAIL_LABEL = "Email or phone"
LOGIN_PASSWORD_LABEL = "Password"

#: Matched exactly: "Sign in" as a substring also matches "Sign in with Apple",
#: which is the *first* button on the page.
SIGN_IN_BUTTON = "Sign in"

CONNECT_BUTTON = "Connect"
#: Shown in place of Connect while an invitation is outstanding.
PENDING_BUTTON = re.compile(r"^Pending\b", re.I)
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
#: The thread list carries no profile URL (verified live 2026-08-30), so this is
#: optional and every thread match falls back to the display name. That is why
#: messaging proposals are low confidence by construction.
THREAD_LINK = "a.msg-conversation-listitem__link"
THREAD_UNREAD_BADGE = ".msg-conversation-card__unread-count"

#: LinkedIn prefixes the snippet with "You:" when the last message is the user's
#: own. That prefix is the only thing distinguishing a reply from an echo of the
#: outbound message we sent, so the whole inbound signal rests on it.
THREAD_OWN_MESSAGE_PREFIX = re.compile(r"^\s*you\s*:", re.I)

# Sent-invitation manager. LinkedIn rebuilt this page with fully obfuscated class
# names (`aa13b50b ce9c4d83 ...`, verified 2026-08-30), so there is no semantic
# class left to key on and `li.invitation-card` matches nothing. Profile links are
# the only stable handle, and they are what the matcher actually needs.
INVITATION_PROFILE_LINK = "main a[href*='/in/']"
#: The links themselves carry no text — the name lives in the surrounding card,
#: which has no usable class either. This walks up to the nearest ancestor that
#: has any text at all, whose first line is the name.
INVITATION_NAME_ANCESTOR = "xpath=ancestor::div[normalize-space(text()) or .//text()][1]"
#: LinkedIn prints its own count as "People (7)". Comparing it against the number
#: of links found is what distinguishes a genuinely empty list from a page that
#: did not render — the reader must never report [] on a guess, because the
#: caller reads [] as "every invitation was accepted".
INVITATION_COUNT_TEXT = re.compile(r"People\s*\((\d+)\)", re.I)

# Job search results. LinkedIn serves two different markups for the same search:
# `job-card-*` when authenticated and `base-search-card` / `job-search-card` to
# guests. Both are listed because a session can silently drop to the guest view,
# and a search that reported nothing there would look like a market with no jobs.
# Verified against the live guest page 2026-08-30.
JOB_CARD = "div.job-card-container, div.job-search-card"
JOB_TITLE = "a.job-card-list__title, .job-card-list__title--link, h3.base-search-card__title"
JOB_COMPANY = (
    ".job-card-container__primary-description, .artdeco-entity-lockup__subtitle, "
    "h4.base-search-card__subtitle"
)
#: `metadata-item` is gone from the authenticated card (verified 2026-08-31,
#: every location came back empty); the wrapper and the lockup caption are what
#: carry it now.
JOB_LOCATION = (
    ".job-card-container__metadata-wrapper, .artdeco-entity-lockup__caption, "
    ".job-card-container__metadata-item, span.job-search-card__location"
)
JOB_LINK = "a.job-card-list__title, a.job-card-container__link, a.base-card__full-link"
JOB_POSTED = "time"

#: Scrolls the virtualized job list. The results pane is an inner scroll
#: container whose class name is obfuscated, so it is found by walking up from a
#: card to the first ancestor that actually scrolls.
JOB_LIST_SCROLL_SCRIPT = """() => {
  const card = document.querySelector('div.job-card-container, div.job-search-card');
  if (!card) return false;
  let el = card.parentElement;
  while (el && el !== document.body) {
    if (el.scrollHeight > el.clientHeight + 50) {
      const before = el.scrollTop;
      // One viewport at a time. Jumping to scrollHeight skips the middle of a
      // virtualized list: the cards in between are recycled without ever
      // having been rendered.
      el.scrollTop = before + el.clientHeight;
      return el.scrollTop !== before;
    }
    el = el.parentElement;
  }
  const before = window.scrollY;
  window.scrollBy(0, window.innerHeight);
  return window.scrollY !== before;
}"""
JOB_EASY_APPLY = (
    ".job-card-container__easy-apply-label, li.job-card-container__footer-item, "
    ".job-search-card__easy-apply-label"
)

#: The old Quill editor. Present in the catalogue so a page that shows it can be
#: named, never typed into: a post goes out publicly under the user's name, and
#: an editor we no longer recognise is a page we do not understand.
POST_EDITOR_FALLBACK = "div.ql-editor[contenteditable='true']"
#: After a successful post LinkedIn shows a "View post" link whose href carries
#: the activity URN. It is the only way to join a published post to its metrics.
POST_SUCCESS_LINK = "a[href*='/feed/update/urn:li:']"
FILE_INPUT = "input[type='file']"
FORM_ERROR = ".artdeco-inline-feedback--error"

#: Selectors whose absence cannot be told apart from an empty page — the first
#: suspects when a run reports zero results. Names match the `selector_misses`
#: entries. Mostly CSS keyed on LinkedIn class names, plus the accessible-name
#: patterns that a relabelled button would break just as silently.
FRAGILE_SELECTORS = {
    # -- reads
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
    "invitation_profile_link": INVITATION_PROFILE_LINK,
    "job_card": JOB_CARD,
    "job_title": JOB_TITLE,
    # -- writes: a relabelled button here used to be a bare False, indistinguishable
    # from "already connected", and the health report stayed silent for all of them.
    "login_email_input": LOGIN_EMAIL_INPUT,
    "login_password_input": LOGIN_PASSWORD_INPUT,
    "sign_in_button": SIGN_IN_BUTTON,
    "connect_button": CONNECT_BUTTON,
    "send_button": SEND_BUTTON,
    "message_button": MESSAGE_BUTTON,
    "message_textbox": MESSAGE_TEXTBOX,
    "start_post_button": START_POST_BUTTON.pattern,
    "post_editor": POST_EDITOR_TEXTBOX.pattern,
    "post_submit_button": POST_SUBMIT_BUTTON.pattern,
    "post_success_link": POST_SUCCESS_LINK,
    "comment_button": COMMENT_BUTTON.pattern,
    "comment_textbox": COMMENT_TEXTBOX.pattern,
    "comment_submit_button": COMMENT_SUBMIT_BUTTON.pattern,
    "edit_intro_button": EDIT_INTRO_BUTTON.pattern,
    "headline_field": HEADLINE_FIELD_LABEL.pattern,
    "save_button": SAVE_BUTTON.pattern,
    "edit_about_button": EDIT_ABOUT_BUTTON.pattern,
}
