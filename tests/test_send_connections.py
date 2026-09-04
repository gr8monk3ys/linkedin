"""The invitation sender: who, how many, and what stops it. No browser."""

from unittest.mock import patch

from click.testing import CliRunner

from linkedin.automation.session import ActionResult
from linkedin.cli import _app, cli
from linkedin.services.automation_service import connection_note_for, send_due_connections
from linkedin.services.daily_run import DailyRun, RunConfig, build_plan
from tests.fake_session import FakeSession


def _actions(*ids):
    return [{"action": "send_connection", "contact_id": i, "name": f"C{i}", "priority": 100 - i} for i in ids]


def test_sends_in_planner_order_and_records_each_outcome():
    session = FakeSession()
    responses = iter(
        [
            ActionResult("ok", "", None),
            ActionResult("skipped", "already connected", None),
            ActionResult("failed", "Connect button missing", None),
            ActionResult("ok", "", None),
        ]
    )
    session.results["connect"] = None
    with patch.object(session, "_verb", side_effect=lambda name, *a, **k: next(responses)):
        sent_ids = []
        outcome = send_due_connections(
            session,
            [{"action": "follow_up_today", "contact_id": 9, "name": "Not an invitation"}, *_actions(1, 2, 3, 4, 5)],
            url_for=lambda cid: "" if cid == 5 else f"https://linkedin.com/in/c{cid}",
            note_for=lambda cid: "",
            on_sent=sent_ids.append,
        )
    assert [r["contact_id"] for r in outcome["sent"]] == [1, 4] and sent_ids == [1, 4]
    assert outcome["skipped"] == [
        {"contact_id": 2, "name": "C2", "reason": "already connected"},
        {"contact_id": 5, "name": "C5", "reason": "no linkedin_url"},
    ]
    assert outcome["failed"] == [{"contact_id": 3, "name": "C3", "reason": "Connect button missing"}]
    assert outcome["stopped"] == ""


def test_a_budget_refusal_stops_the_loop_without_touching_the_rest():
    session = FakeSession()
    session.results["connect"] = ActionResult("refused", "daily connection limit reached", None)
    sent_ids = []
    outcome = send_due_connections(
        session, _actions(1, 2, 3), url_for=lambda cid: "u", note_for=lambda cid: "", on_sent=sent_ids.append
    )
    assert outcome["sent"] == [] and sent_ids == [] and outcome["stopped"] == "daily connection limit reached"
    assert len(session.calls_to("connect")) == 1


def test_limit_caps_below_the_budget():
    session = FakeSession()
    session.results["connect"] = ActionResult("ok", "", None)
    outcome = send_due_connections(
        session, _actions(1, 2, 3), url_for=lambda cid: "u", note_for=lambda cid: "", on_sent=lambda cid: None, limit=2
    )
    assert len(outcome["sent"]) == 2 and outcome["stopped"] == "limit of 2 reached"


def test_note_is_the_newest_real_connection_draft_or_nothing():
    drafts = [
        {"id": 1, "contact_id": 1, "type": "connection", "content": "old", "source": "ai"},
        {"id": 2, "contact_id": 1, "type": "message", "content": "wrong type", "source": "ai"},
        {"id": 3, "contact_id": 1, "type": "connection", "content": "template", "source": "template"},
        {"id": 4, "contact_id": 1, "type": "connection", "content": "x" * 400, "source": "ai"},
    ]
    assert connection_note_for(1, drafts) == "x" * 300
    assert connection_note_for(2, drafts) == ""


def _add(runner, name, url):
    r = runner.invoke(cli, ["contacts", "add"], input=f"{name}\nEngineer\nCo\n{url}\n\n")
    assert r.exit_code == 0, r.output


def test_connect_due_sends_the_ranked_actions_and_advances_status(fake_session):
    runner = CliRunner()
    _add(runner, "Ann", "https://linkedin.com/in/ann")
    _add(runner, "Bob", "https://linkedin.com/in/bob")
    _app.draft_repo.add({"id": 1, "contact_id": 1, "type": "connection", "content": "Hi Ann", "source": "ai"})
    fake_session.results["connect"] = ActionResult("ok", "", None)

    result = runner.invoke(cli, ["automate", "connect-due", "--headless"])
    assert result.exit_code == 0, result.output
    assert "Sent invitation to Ann" in result.output and "Sent invitation to Bob" in result.output
    calls = fake_session.calls_to("connect")
    assert {(a[0], k.get("note")) for a, k in calls} == {
        ("https://linkedin.com/in/ann", "Hi Ann"),
        ("https://linkedin.com/in/bob", ""),
    }
    assert {c["status"] for c in _app.contact_repo.list_all()} == {"connection_sent"}

    again = runner.invoke(cli, ["automate", "connect-due"])
    assert "No connection actions due" in again.output


def test_connect_due_dry_run_sends_nothing_and_changes_nothing(fake_session):
    runner = CliRunner()
    _add(runner, "Ann", "https://linkedin.com/in/ann")
    fake_session.results["connect"] = ActionResult("ok", "", None)
    result = runner.invoke(cli, ["automate", "connect-due", "--dry-run"])
    assert result.exit_code == 0 and "Would send" in result.output
    assert fake_session.dry_run
    assert _app.contact_repo.list_all()[0]["status"] == "not_contacted"


def test_run_daily_sends_after_the_plan_and_never_fails_on_a_browser_error(fake_session):
    runner = CliRunner()
    _add(runner, "Ann", "https://linkedin.com/in/ann")
    fake_session.results["connect"] = ActionResult("ok", "", None)
    run = DailyRun(
        _app.get(),
        RunConfig(send_connections=True),
        connection_sender=lambda actions: {
            "sent": [{"name": "Ann"}],
            "skipped": [],
            "failed": [],
            "stopped": "daily connection limit reached",
        },
    )
    data = run.cycle()
    assert data["connections"]["sent"] == [{"name": "Ann"}]
    plan = build_plan(data)
    section = next(s for s in plan.sections if s.key == "invitations")
    assert section.rows == [["Ann", "sent"]] and section.hint == "daily connection limit reached"
    assert "## Invitations Sent\n- Ann | sent" in plan.to_markdown()

    def boom(actions):
        raise RuntimeError("browser gone")

    data = DailyRun(_app.get(), RunConfig(send_connections=True), connection_sender=boom).cycle()
    assert data["connections"]["stopped"] == "RuntimeError: browser gone"
    assert run.classify(data)[0] == "success"

    off = DailyRun(_app.get(), RunConfig(send_connections=False), connection_sender=boom).cycle()
    assert "connections" not in off


def test_run_daily_cli_flag_sends_through_the_session(fake_session):
    runner = CliRunner()
    _add(runner, "Ann", "https://linkedin.com/in/ann")
    fake_session.results["connect"] = ActionResult("ok", "", None)
    result = runner.invoke(cli, ["run-daily", "--send-connections"])
    assert result.exit_code == 0, result.output
    assert "Invitations Sent" in result.output and "Ann" in result.output
    assert fake_session.calls_to("connect") and _app.contact_repo.list_all()[0]["status"] == "connection_sent"


def test_the_sender_draws_from_the_whole_queue_not_the_plan_slice(fake_session):
    """Eight overdue follow-ups fill the plan; the invitations still go out."""
    runner = CliRunner()
    for i in range(9):
        _add(runner, f"Old{i}", f"https://linkedin.com/in/old{i}")
        _app.contact_svc.update_contact(i + 1, status="messaged")
        _app.contact_svc.set_reminder(i + 1, date="2026-01-01")
    _add(runner, "Fresh", "https://linkedin.com/in/fresh")
    fake_session.results["connect"] = ActionResult("ok", "", None)

    run = DailyRun(_app.get(), RunConfig(actions_limit=8))
    assert [a["action"] for a in run.plan_data()["actions"]] == ["follow_up_overdue"] * 8
    assert [a["name"] for a in run.invitation_queue()] == ["Fresh"]


def test_limit_caps_attempts_not_successes():
    """A --limit 1 run whose send fails must stop at one profile, not walk the queue.

    This is what happened live: every send failed, `limit` only counted
    successes, and the run loaded 28 profiles against LinkedIn.
    """
    session = FakeSession()
    session.results["connect"] = ActionResult("failed", "send_button not found", None)
    outcome = send_due_connections(
        session,
        _actions(*range(1, 30)),
        url_for=lambda cid: "u",
        note_for=lambda cid: "",
        on_sent=lambda cid: None,
        limit=1,
    )
    assert len(session.calls_to("connect")) == 1
    assert len(outcome["failed"]) == 1 and outcome["stopped"] == "limit of 1 reached"


def test_a_run_of_failures_stops_the_sweep():
    """Three identical failures is a markup breakage; the next twenty-five say nothing new."""
    session = FakeSession()
    session.results["connect"] = ActionResult("failed", "send_button not found", None)
    outcome = send_due_connections(
        session, _actions(*range(1, 30)), url_for=lambda cid: "u", note_for=lambda cid: "", on_sent=lambda cid: None
    )
    assert len(session.calls_to("connect")) == 3
    assert "3 sends failed in a row" in outcome["stopped"] and "send_button not found" in outcome["stopped"]


def test_a_success_or_skip_resets_the_failure_run():
    session = FakeSession()
    responses = iter(
        [
            ActionResult("failed", "x", None),
            ActionResult("failed", "x", None),
            ActionResult("ok", "", None),
            ActionResult("failed", "x", None),
            ActionResult("failed", "x", None),
            ActionResult("skipped", "already connected", None),
            ActionResult("failed", "x", None),
            ActionResult("failed", "x", None),
            ActionResult("failed", "x", None),
        ]
    )
    with patch.object(session, "_verb", side_effect=lambda name, *a, **k: next(responses)):
        outcome = send_due_connections(
            session, _actions(*range(1, 30)), url_for=lambda cid: "u", note_for=lambda cid: "", on_sent=lambda cid: None
        )
    assert len(outcome["sent"]) == 1 and len(outcome["skipped"]) == 1 and len(outcome["failed"]) == 7
    assert "3 sends failed in a row" in outcome["stopped"]


def test_an_unconfirmed_send_is_not_a_sent_one():
    """The page clicked Send but would not confirm delivery. The contact must not
    advance on a maybe: the tool reported "Sent invitation to Jonathan Shin" for
    an invitation that never appeared in LinkedIn's sent list."""
    from linkedin.automation.linkedin_page import INVITATION_UNCONFIRMED

    session = FakeSession()
    session.results["connect"] = ActionResult("ok", INVITATION_UNCONFIRMED, None)
    sent_ids = []
    outcome = send_due_connections(
        session, _actions(1, 2, 3), url_for=lambda cid: "u", note_for=lambda cid: "", on_sent=sent_ids.append
    )
    assert outcome["sent"] == [] and sent_ids == []
    assert [r["contact_id"] for r in outcome["unconfirmed"]] == [1]
    assert outcome["stopped"] == "a send could not be confirmed; stopping"
    assert len(session.calls_to("connect")) == 1
