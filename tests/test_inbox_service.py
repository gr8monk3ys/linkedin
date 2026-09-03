"""Tests for the inbound-signal proposal matcher.

The matcher is the part of the inbox feature that can corrupt the CRM, so it is
a pure function over dicts and every case here runs without a browser.
"""

import datetime as _dt

import pytest

from linkedin.services.inbox_service import (
    InboxService,
    inbound_from_strangers,
    normalize_name,
    parse_thread_timestamp,
    review_proposals,
    strip_url_query,
    update_thread_index,
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


# --- LinkedIn's thread timestamps -------------------------------------------
# The messaging pane never shows an ISO date. Feeding these to a strict ISO
# parser made every thread unparseable, so the sync read 20 threads and
# proposed nothing — indistinguishable from a quiet inbox.

TODAY = _dt.date(2026, 8, 30)


@pytest.mark.parametrize("raw,expected", [
    ("Aug 29", _dt.date(2026, 8, 29)),
    ("Jul 1", _dt.date(2026, 7, 1)),
    ("May 26", _dt.date(2026, 5, 26)),
    ("Aug 30", _dt.date(2026, 8, 30)),
])
def test_parses_month_day_as_the_most_recent_occurrence(raw, expected):
    assert parse_thread_timestamp(raw, today=TODAY) == expected


def test_month_day_that_would_be_in_the_future_belongs_to_last_year():
    """"Dec 25" seen in August means last December, not four months from now."""
    assert parse_thread_timestamp("Dec 25", today=TODAY) == _dt.date(2025, 12, 25)


def test_explicit_year_is_honoured():
    assert parse_thread_timestamp("Aug 29, 2024", today=TODAY) == _dt.date(2024, 8, 29)


@pytest.mark.parametrize("raw", ["10:42 AM", "1:05 PM", "11:59 PM"])
def test_a_time_of_day_means_today(raw):
    assert parse_thread_timestamp(raw, today=TODAY) == TODAY


def test_yesterday():
    assert parse_thread_timestamp("Yesterday", today=TODAY) == _dt.date(2026, 8, 29)


def test_iso_still_parses():
    assert parse_thread_timestamp("2026-08-29T09:00:00", today=TODAY) == _dt.date(2026, 8, 29)


@pytest.mark.parametrize("raw", ["", "   ", "not a date", None])
def test_unparseable_returns_none(raw):
    assert parse_thread_timestamp(raw, today=TODAY) is None


def test_reply_with_a_linkedin_timestamp_produces_a_proposal():
    """End to end on the real shape: 'Aug 29' against a contact last touched Aug 27."""
    svc = InboxService()
    threads = [thread(url="", timestamp="Aug 29", name="Kobie Nikka")]
    contacts = [contact(id=4, name="Kobie Nikka", company="SpaceX",
                        status="connection_sent", last_contact="2026-08-27T00:00:00")]

    proposals = svc.propose_transitions(threads, [], contacts, today=TODAY)

    assert len(proposals) == 1
    assert proposals[0]["to_status"] == "responded"
    assert proposals[0]["confidence"] == "low"  # no URL on a thread card


# -- review: which proposals may be applied ----------------------------------------


def proposal(**overrides):
    base = {"contact_id": 1, "name": "Ryan Barner", "from_status": "messaged", "to_status": "responded", "confidence": "high"}
    base.update(overrides)
    return base


def test_review_applies_a_high_confidence_proposal_when_confirmed():
    review = review_proposals([proposal()], [contact()], confirm=lambda p, low: True)
    assert [p["contact_id"] for p in review.apply] == [1]
    assert review.kept == [] and review.dropped == []


def test_review_keeps_a_declined_proposal_for_later():
    review = review_proposals([proposal()], [contact()], confirm=lambda p, low: False)
    assert review.apply == [] and review.kept == [proposal()]


def test_review_drops_a_proposal_whose_contact_moved_on():
    """A status changed by hand since the sync wins over the proposal."""
    review = review_proposals([proposal()], [contact(status="call_scheduled")], confirm=lambda p, low: True)
    assert review.apply == [] and review.kept == []
    (dropped, why), = review.dropped
    assert "call_scheduled" in why


def test_review_drops_a_proposal_whose_contact_is_gone():
    review = review_proposals([proposal(contact_id=99)], [contact()], confirm=lambda p, low: True)
    assert review.dropped[0][1] == "contact no longer exists"


def test_yes_applies_high_confidence_without_asking():
    asked = []
    review = review_proposals([proposal()], [contact()], confirm=lambda p, low: asked.append(p) or False, yes=True)
    assert asked == [] and len(review.apply) == 1


def test_yes_still_asks_about_a_low_confidence_proposal():
    """A name is a guess; --yes must not silently apply it."""
    asked = []

    def confirm(p, low):
        asked.append(low)
        return False

    review = review_proposals([proposal(confidence="low")], [contact()], confirm=confirm, yes=True)
    assert asked == [True]
    assert review.apply == [] and len(review.kept) == 1


# -- thread index: who wrote, without what they wrote ------------------------------

IDX_TODAY = _dt.date(2026, 9, 2)
IDX_NOW = _dt.datetime(2026, 9, 2, 9, 0, 0)


def test_index_records_identity_and_timing_but_no_body():
    rows = update_thread_index([], [thread(snippet="Secret details")], [contact()], today=IDX_TODAY, now=IDX_NOW)
    (row,) = rows
    assert row["name"] == "Ryan Barner"
    assert row["url"] == "https://www.linkedin.com/in/ryanbarner"
    assert row["last_message_at"] == "2026-08-29"
    assert row["last_from_them"] is True
    assert row["is_contact"] is True
    assert row["first_seen"] == row["last_seen"] == "2026-09-02T09:00:00"
    assert "Secret details" not in str(row)


def test_index_merges_by_identity_and_keeps_first_seen():
    first = update_thread_index([], [thread()], [contact()], today=IDX_TODAY, now=IDX_NOW)
    later = _dt.datetime(2026, 9, 5, 9, 0, 0)
    rows = update_thread_index(first, [thread(timestamp="2026-09-04", url="https://www.linkedin.com/in/ryanbarner?trk=x")], [contact()], today=later.date(), now=later)
    (row,) = rows
    assert row["first_seen"] == "2026-09-02T09:00:00"
    assert row["last_seen"] == "2026-09-05T09:00:00"
    assert row["last_message_at"] == "2026-09-04"


def test_index_falls_back_to_the_name_when_there_is_no_url():
    rows = update_thread_index([], [thread(url=None, name="Sam Stranger")], [contact()], today=IDX_TODAY, now=IDX_NOW)
    assert rows[0]["key"] == "name:sam stranger"
    assert rows[0]["is_contact"] is False


def test_index_uses_linkedin_timestamps():
    rows = update_thread_index([], [thread(timestamp="Yesterday")], [], today=IDX_TODAY, now=IDX_NOW)
    assert rows[0]["last_message_at"] == "2026-09-01"


def test_strangers_are_non_contacts_who_had_the_last_word_in_the_window():
    threads = [
        thread(name="Sam Stranger", url="https://www.linkedin.com/in/sam", timestamp="2026-08-30"),
        thread(name="Echo Stranger", url="https://www.linkedin.com/in/echo", timestamp="2026-08-30", last_from_them=False),
        thread(name="Old Stranger", url="https://www.linkedin.com/in/old", timestamp="2026-06-01"),
        thread(),  # a contact
    ]
    index = update_thread_index([], threads, [contact()], today=IDX_TODAY, now=IDX_NOW)
    rows = inbound_from_strangers(index, IDX_TODAY - _dt.timedelta(days=30))
    assert [r["name"] for r in rows] == ["Sam Stranger"]


def test_a_stranger_who_becomes_a_contact_stops_counting():
    index = update_thread_index([], [thread(name="Sam", url="https://www.linkedin.com/in/sam", timestamp="2026-08-30")], [], today=IDX_TODAY, now=IDX_NOW)
    assert len(inbound_from_strangers(index, IDX_TODAY - _dt.timedelta(days=30))) == 1
    index = update_thread_index(index, [thread(name="Sam", url="https://www.linkedin.com/in/sam", timestamp="2026-08-30")], [contact(id=2, name="Sam", linkedin_url="https://www.linkedin.com/in/sam")], today=IDX_TODAY, now=IDX_NOW)
    assert inbound_from_strangers(index, IDX_TODAY - _dt.timedelta(days=30)) == []
