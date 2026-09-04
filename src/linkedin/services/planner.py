"""The planner: one row per action, and the rules that emit them.

Everything the planner knows lives here so that it can be checked at import:

- `STATUS_RULES` / `APPLICATION_STATUS_RULES` — per status: how long to wait
  and which action to emit once that wait has elapsed.
- `ACTIONS` — per action name: how it is shown (`label`), what to run
  (`command`), and how to draft for it (`draft`, or None).

An action used to be a name emitted by a rule, with its label, command and
draft strategy in three unguarded `.get(name, default)` tables in the CLI.
`send_connection` and `follow_up_messaged` had rules but no draft branch, so
`run-daily` silently produced nothing for them. The coverage checks at the
bottom make that half-added state impossible to import.
"""

from linkedin.constants import ContactStatus

# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

# Statuses that end the pipeline; they carry no follow-up and generate no actions.
TERMINAL_STATUSES = frozenset({"hired", "rejected"})

# Actions the contact planner emits from dates rather than from a status rule.
FOLLOW_UP_OVERDUE = "follow_up_overdue"
FOLLOW_UP_TODAY = "follow_up_today"
REPAIR_CONTACT = "repair_contact"
SEND_CONNECTION = "send_connection"
DATE_DRIVEN_CONTACT_ACTIONS = frozenset({FOLLOW_UP_OVERDUE, FOLLOW_UP_TODAY, REPAIR_CONTACT})

# One row per pipeline status: how long to wait before the contact is due
# (`cadence_days`, which seeds `follow_up_date` on add and on every status
# change), and what to do once that wait has elapsed. Cadence and action in the
# same row is what makes a status with one and not the other unrepresentable —
# that hole is what made `messaged` contacts invisible to the planner.
STATUS_RULES: dict[str, dict] = {
    "not_contacted": {
        "cadence_days": 0,
        "after_days": 0,
        "priority": 60,
        "action": "send_connection",
        "reason": "Added {age} day(s) ago; send a connection request",
    },
    "connection_sent": {
        "cadence_days": 7,
        "after_days": 14,
        "priority": 85,
        "action": "stale_connection_sent",
        "reason": "Connection request sent {age} day(s) ago with no response",
    },
    "connected": {
        "cadence_days": 2,
        "after_days": 7,
        "priority": 70,
        "action": "send_first_message",
        "reason": "Connected {age} day(s) ago; send first message",
    },
    "messaged": {
        "cadence_days": 5,
        "after_days": 5,
        "priority": 75,
        "action": "follow_up_messaged",
        "reason": "Messaged {age} day(s) ago with no reply; follow up",
    },
    "responded": {
        "cadence_days": 2,
        "after_days": 3,
        "priority": 65,
        "action": "schedule_call",
        "reason": "Responded {age} day(s) ago; propose a call",
    },
    "call_scheduled": {
        "cadence_days": 7,
        "after_days": 7,
        "priority": 68,
        "action": "call_follow_up",
        "reason": "Call scheduled {age} day(s) ago; confirm or debrief",
    },
}

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

APPLICATION_STATUSES = [
    "saved",
    "applied",
    "phone_screen",
    "technical",
    "onsite",
    "offer_received",
    "accepted",
    "rejected",
    "ghosted",
]

# Statuses that end the lifecycle; they generate no actions.
TERMINAL_APPLICATION_STATUSES = frozenset({"accepted", "rejected", "ghosted"})

REPAIR_APPLICATION = "repair_application"
DATE_DRIVEN_APPLICATION_ACTIONS = frozenset({REPAIR_APPLICATION})

# Same shape as STATUS_RULES, same reason: a status with no rule is invisible
# to the planner forever, which is the hole that made twenty applications
# unplannable.
APPLICATION_STATUS_RULES: dict[str, dict] = {
    "saved": {
        "after_days": 0,
        "priority": 60,
        "action": "apply_to_saved",
        "reason": "Saved {age} day(s) ago and never applied",
    },
    "applied": {
        "after_days": 10,
        "priority": 70,
        "action": "chase_application",
        "reason": "Applied {age} day(s) ago with no response; follow up or mark ghosted",
    },
    "phone_screen": {
        "after_days": 5,
        "priority": 85,
        "action": "chase_interview",
        "reason": "Phone screen {age} day(s) ago with no next step",
    },
    "technical": {
        "after_days": 5,
        "priority": 88,
        "action": "chase_interview",
        "reason": "Technical round {age} day(s) ago with no next step",
    },
    "onsite": {
        "after_days": 5,
        "priority": 90,
        "action": "chase_interview",
        "reason": "Onsite {age} day(s) ago with no decision",
    },
    "offer_received": {
        "after_days": 2,
        "priority": 95,
        "action": "respond_to_offer",
        "reason": "Offer received {age} day(s) ago; respond",
    },
}

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

# A draft spec is data, not a callable, so this table imports without the
# draft module and the coverage check can inspect it. `generator` names a
# DraftService method that takes the contact id first; `kwargs` follow.
_FOLLOW_UP = {"type": "follow_up_1", "generator": "generate_follow_up", "kwargs": {"attempt": 1}}

ACTIONS: dict[str, dict] = {
    # -- contacts: date-driven
    FOLLOW_UP_OVERDUE: {
        "label": "Follow up (overdue)",
        "command": "linkedin-cli drafts follow-up {id}",
        "draft": _FOLLOW_UP,
    },
    FOLLOW_UP_TODAY: {
        "label": "Follow up (today)",
        "command": "linkedin-cli drafts follow-up {id}",
        "draft": _FOLLOW_UP,
    },
    REPAIR_CONTACT: {
        "label": "Repair missing dates",
        "command": "linkedin-cli contacts repair",
        "draft": None,
    },
    # -- contacts: from STATUS_RULES
    "send_connection": {
        "label": "Send connection request",
        "command": "linkedin-cli drafts connection {id}",
        "draft": {"type": "connection", "generator": "generate_connection", "kwargs": {}},
    },
    "stale_connection_sent": {
        "label": "Follow up on stale request",
        "command": "linkedin-cli drafts follow-up {id}",
        "draft": _FOLLOW_UP,
    },
    "send_first_message": {
        "label": "Send first message",
        "command": "linkedin-cli drafts message {id}",
        "draft": {
            "type": "message",
            "generator": "generate_message",
            "kwargs": {"context": "We're connected, and I want to send a concise first message."},
        },
    },
    "follow_up_messaged": {
        "label": "Follow up (no reply)",
        "command": "linkedin-cli drafts follow-up {id}",
        "draft": _FOLLOW_UP,
    },
    "schedule_call": {
        "label": "Propose a call",
        "command": "linkedin-cli contacts update {id} --status call_scheduled",
        "draft": {
            "type": "message",
            "generator": "generate_message",
            "kwargs": {"context": "They responded recently; propose a short call as the next step."},
        },
    },
    "call_follow_up": {
        "label": "Confirm or debrief call",
        "command": "linkedin-cli contacts view {id}",
        "draft": None,
    },
    # -- applications
    REPAIR_APPLICATION: {
        "label": "Repair missing dates",
        "command": "linkedin-cli applications view {id}",
        "draft": None,
    },
    "apply_to_saved": {
        "label": "Apply (saved, never submitted)",
        "command": "linkedin-cli applications advance {id} --status applied",
        "draft": None,
    },
    "chase_application": {
        "label": "Chase (no response)",
        "command": "linkedin-cli applications view {id}",
        "draft": None,
    },
    "chase_interview": {
        "label": "Chase interview outcome",
        "command": "linkedin-cli applications view {id}",
        "draft": None,
    },
    "respond_to_offer": {
        "label": "Respond to offer",
        "command": "linkedin-cli applications view {id}",
        "draft": None,
    },
}

_ACTION_COLUMNS = frozenset({"label", "command", "draft"})
_DRAFT_COLUMNS = frozenset({"type", "generator", "kwargs"})


def label_for(action_name: str) -> str:
    return ACTIONS[action_name]["label"]


def command_for(action_name: str, record_id: int) -> str:
    return ACTIONS[action_name]["command"].format(id=record_id)


def draft_spec_for(action_name: str) -> dict | None:
    return ACTIONS[action_name]["draft"]


def emittable_actions() -> set[str]:
    """Every action name a rule or a date branch can emit."""
    return (
        {rule["action"] for rule in STATUS_RULES.values()}
        | {rule["action"] for rule in APPLICATION_STATUS_RULES.values()}
        | set(DATE_DRIVEN_CONTACT_ACTIONS)
        | set(DATE_DRIVEN_APPLICATION_ACTIONS)
    )


# ---------------------------------------------------------------------------
# Coverage checks — run at import so a half-added status or action cannot ship
# ---------------------------------------------------------------------------


def _check_status_coverage() -> None:
    """Fail loudly if a pipeline status is neither terminal nor planned for.

    `ContactStatus` is where a new status gets added, and a status the planner has
    no rule for is invisible to it forever. Checking the tables against the enum
    rather than against each other is what makes that impossible to ship.
    """
    known = set(STATUS_RULES) | set(TERMINAL_STATUSES)
    declared = {status.value for status in ContactStatus}
    if known != declared:
        raise RuntimeError(
            "Pipeline status tables disagree with ContactStatus — a status with no "
            f"rule is invisible to the planner. Missing a rule: {sorted(declared - known)}; "
            f"rule for an unknown status: {sorted(known - declared)}"
        )


def _check_application_status_coverage() -> None:
    """Fail loudly if an application status is neither terminal nor planned for."""
    covered = set(APPLICATION_STATUS_RULES) | set(TERMINAL_APPLICATION_STATUSES)
    declared = set(APPLICATION_STATUSES)
    if covered != declared:
        raise RuntimeError(
            "Application status tables disagree with APPLICATION_STATUSES — a status with no "
            f"rule is invisible to the planner. Missing a rule: {sorted(declared - covered)}; "
            f"rule for an unknown status: {sorted(covered - declared)}"
        )


def _check_action_coverage() -> None:
    """Fail loudly if an action can be emitted but not rendered or drafted.

    Every action a rule or a date branch can emit must have a complete row, and
    no row may exist for an action nothing emits. A draft spec, when present,
    must name a type, a generator and its kwargs.
    """
    emitted = emittable_actions()
    declared = set(ACTIONS)
    if emitted != declared:
        raise RuntimeError(
            "ACTIONS disagrees with the rules — an action with no row renders as a bare slug "
            f"and drafts nothing. Emitted but no row: {sorted(emitted - declared)}; "
            f"row but never emitted: {sorted(declared - emitted)}"
        )
    for name, row in ACTIONS.items():
        missing = _ACTION_COLUMNS - set(row)
        if missing:
            raise RuntimeError(f"ACTIONS[{name!r}] is missing {sorted(missing)}")
        spec = row["draft"]
        if spec is not None and _DRAFT_COLUMNS - set(spec):
            raise RuntimeError(f"ACTIONS[{name!r}]['draft'] is missing {sorted(_DRAFT_COLUMNS - set(spec))}")


_check_status_coverage()
_check_application_status_coverage()
_check_action_coverage()
