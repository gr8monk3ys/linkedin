"""Tests for the inbound-signal proposal matcher.

The matcher is the part of the inbox feature that can corrupt the CRM, so it is
a pure function over dicts and every case here runs without a browser.
"""

import pytest

from linkedin.services.inbox_service import (
    InboxService,
    normalize_name,
    strip_url_query,
)


def contact(**overrides):
    base = {
        "id": 1,
        "name": "Ryan Barner",
        "company": "Netflix",
        "status": "messaged",
        "linkedin_url": "https://www.linkedin.com/in/ryanbarner",
        "last_contact": "2026-08-27T10:00:00",
        "created_at": "2026-08-27T10:00:00",
    }
    base.update(overrides)
    return base


def thread(**overrides):
    base = {
        "name": "Ryan Barner",
        "url": "https://www.linkedin.com/in/ryanbarner",
        "snippet": "Happy to chat next week.",
        "timestamp": "2026-08-29T09:00:00",
        "unread": True,
        "last_from_them": True,
    }
    base.update(overrides)
    return base


# --- URL and name normalization ---------------------------------------------


def test_strip_url_query_removes_tracking_params():
    assert strip_url_query("https://www.linkedin.com/in/ryan?trk=abc") == "https://www.linkedin.com/in/ryan"


def test_strip_url_query_ignores_trailing_slash_and_case():
    assert strip_url_query("https://www.LinkedIn.com/in/Ryan/") == strip_url_query("https://www.linkedin.com/in/ryan")


def test_normalize_name_folds_case_and_whitespace():
    assert normalize_name("  Ryan   Barner ") == normalize_name("ryan barner")


def test_normalize_name_drops_parenthetical_and_credentials():
    assert normalize_name("Qiwei (Steve) Chen, MBA") == normalize_name("Qiwei Chen")


# --- Reply detection ---------------------------------------------------------


def test_reply_newer_than_last_contact_proposes_responded():
    svc = InboxService()
    proposals = svc.propose_transitions([thread()], [], [contact()])

    assert len(proposals) == 1
    assert proposals[0]["contact_id"] == 1
    assert proposals[0]["from_status"] == "messaged"
    assert proposals[0]["to_status"] == "responded"
    assert proposals[0]["confidence"] == "high"


def test_reply_older_than_last_contact_is_not_a_new_signal():
    """A thread we already knew about must not re-propose forever."""
    svc = InboxService()
    proposals = svc.propose_transitions(
        [thread(timestamp="2026-08-20T09:00:00")], [], [contact()]
    )
    assert proposals == []


def test_own_message_is_not_a_reply():
    svc = InboxService()
    proposals = svc.propose_transitions([thread(last_from_them=False)], [], [contact()])
    assert proposals == []


def test_reply_from_connected_contact_also_proposes_responded():
    svc = InboxService()
    proposals = svc.propose_transitions([thread()], [], [contact(status="connected")])
    assert proposals[0]["to_status"] == "responded"


def test_reply_from_terminal_contact_is_ignored():
    svc = InboxService()
    proposals = svc.propose_transitions([thread()], [], [contact(status="hired")])
    assert proposals == []


def test_contact_already_responded_is_not_re_proposed():
    svc = InboxService()
    proposals = svc.propose_transitions([thread()], [], [contact(status="responded")])
    assert proposals == []


# --- Matching ----------------------------------------------------------------


def test_url_match_wins_over_a_conflicting_name():
    """The URL is the identity; a display name that differs must not split it."""
    svc = InboxService()
    proposals = svc.propose_transitions(
        [thread(name="Ryan B.")], [], [contact()]
    )
    assert len(proposals) == 1
    assert proposals[0]["confidence"] == "high"


def test_name_only_match_is_low_confidence():
    svc = InboxService()
    proposals = svc.propose_transitions(
        [thread(url="")], [], [contact()]
    )
    assert len(proposals) == 1
    assert proposals[0]["confidence"] == "low"
    assert "name" in proposals[0]["evidence"].lower()


def test_ambiguous_name_matching_two_contacts_proposes_nothing():
    """Two people with the same name and no URL is not evidence about either."""
    svc = InboxService()
    contacts = [contact(id=1), contact(id=2, linkedin_url="https://www.linkedin.com/in/other")]
    proposals = svc.propose_transitions([thread(url="")], [], contacts)
    assert proposals == []


def test_unknown_thread_participant_proposes_nothing():
    svc = InboxService()
    proposals = svc.propose_transitions(
        [thread(name="Nobody Here", url="https://www.linkedin.com/in/nobody")],
        [],
        [contact()],
    )
    assert proposals == []


# --- Invitation acceptance ---------------------------------------------------


def test_sent_invite_no_longer_pending_proposes_connected():
    svc = InboxService()
    c = contact(status="connection_sent")
    proposals = svc.propose_transitions([], [], [c])

    assert len(proposals) == 1
    assert proposals[0]["to_status"] == "connected"
    assert proposals[0]["source"] == "invitations"


def test_still_pending_invite_proposes_nothing():
    svc = InboxService()
    c = contact(status="connection_sent")
    pending = [{"name": "Ryan Barner", "url": "https://www.linkedin.com/in/ryanbarner"}]
    proposals = svc.propose_transitions([], pending, [c])
    assert proposals == []


def test_invitation_signal_requires_a_pending_list_that_was_read():
    """An empty pending list from a broken selector must not mean 'all accepted'.

    This is the failure that would advance every outstanding invitation at once,
    so absence of the list is distinguished from a genuinely empty list.
    """
    svc = InboxService()
    c = contact(status="connection_sent")
    proposals = svc.propose_transitions([], None, [c])
    assert proposals == []


def test_only_connection_sent_contacts_get_invitation_proposals():
    svc = InboxService()
    proposals = svc.propose_transitions([], [], [contact(status="messaged")])
    assert proposals == []


# --- Combining ---------------------------------------------------------------


def test_one_contact_yields_at_most_one_proposal():
    """A reply from someone whose invite also vanished is one transition, not two."""
    svc = InboxService()
    c = contact(status="connection_sent")
    proposals = svc.propose_transitions([thread()], [], [c])

    assert len(proposals) == 1
    # The reply is the stronger signal: it implies the connection was accepted.
    assert proposals[0]["to_status"] == "responded"


def test_proposals_are_sorted_high_confidence_first():
    svc = InboxService()
    contacts = [
        contact(id=1),
        contact(id=2, name="Michele Chung", linkedin_url="https://www.linkedin.com/in/michele"),
    ]
    threads = [thread(), thread(name="Michele Chung", url="")]
    proposals = svc.propose_transitions(threads, [], contacts)

    assert [p["confidence"] for p in proposals] == ["high", "low"]


@pytest.mark.parametrize("missing", ["timestamp", "name"])
def test_malformed_thread_is_skipped_not_fatal(missing):
    svc = InboxService()
    bad = thread()
    del bad[missing]
    assert svc.propose_transitions([bad], [], [contact()]) == []
