"""Following: the only action available on the contacts this CRM ranks highest."""

from click.testing import CliRunner

from linkedin.app import App
from linkedin.automation.session import ActionResult
from linkedin.cli import _app, cli
from linkedin.data.paths import DataDir
from linkedin.services.automation_service import empty_follow_outcome, follow_due_profiles
from tests.fake_session import FakeSession


def _actions(*ids):
    return [{"action": "send_connection", "contact_id": i, "name": f"C{i}", "priority": 100 - i} for i in ids]


def _crm(tmp_path, ids, without_url=()):
    app = App(DataDir(tmp_path))
    for i in ids:
        app.contact_svc.add_contact(
            f"C{i}", "Solutions Engineer", "Co", "" if i in without_url else f"https://li/in/c{i}"
        )
    return app


def _follow(app, session, actions, **kw):
    return follow_due_profiles(session, actions, app.contact_repo, app.contact_svc, **kw)


def test_follows_in_rank_order_and_records_each_one(tmp_path):
    app = _crm(tmp_path, [1, 2, 3], without_url=[3])
    session = FakeSession()
    session.results["follow"] = [
        ActionResult("ok", "", None),
        ActionResult("skipped", "already following", None),
    ]

    outcome = _follow(app, session, _actions(1, 2, 3))
    assert [r["contact_id"] for r in outcome["followed"]] == [1]
    assert {r["contact_id"] for r in outcome["skipped"]} == {2, 3}
    followed = {c["id"] for c in app.contact_repo.list_all() if c.get("followed_at")}
    assert followed == {1, 2}, "the page saying 'already following' is recorded too"


def test_someone_already_followed_costs_no_page_load(tmp_path):
    app = _crm(tmp_path, [1, 2])
    app.contact_svc.record_followed(1)
    session = FakeSession()
    session.results["follow"] = ActionResult("ok", "", None)

    outcome = _follow(app, session, _actions(1, 2))
    assert len(session.calls_to("follow")) == 1, "only the one not already followed"
    assert outcome["skipped"][0]["reason"] == "already followed"


def test_the_budget_stops_the_sweep(tmp_path):
    app = _crm(tmp_path, [1, 2, 3])
    session = FakeSession()
    session.results["follow"] = ActionResult("refused", "daily follow limit reached", None)

    outcome = _follow(app, session, _actions(1, 2, 3))
    assert outcome["followed"] == [] and outcome["stopped"] == "daily follow limit reached"
    assert len(session.calls_to("follow")) == 1


def test_limit_caps_attempts_and_a_run_of_failures_stops_it(tmp_path):
    app = _crm(tmp_path, list(range(1, 30)))
    session = FakeSession()
    session.results["follow"] = ActionResult("failed", "follow_button not found", None)

    capped = _follow(app, session, _actions(*range(1, 30)), limit=1)
    assert len(session.calls_to("follow")) == 1 and capped["stopped"] == "limit of 1 reached"

    session.calls.clear()
    swept = _follow(app, session, _actions(*range(1, 30)))
    assert len(session.calls_to("follow")) == 3
    assert "3 follows failed in a row" in swept["stopped"]


def test_an_unconfirmed_follow_is_not_recorded(tmp_path):
    app = _crm(tmp_path, [1, 2])
    session = FakeSession()
    session.results["follow"] = ActionResult("unconfirmed", "button did not change to Following", None)

    outcome = _follow(app, session, _actions(1, 2))
    assert outcome["followed"] == [] and len(outcome["unconfirmed"]) == 1
    assert not any(c.get("followed_at") for c in app.contact_repo.list_all())
    assert outcome["stopped"] == "a follow could not be confirmed; stopping"


def test_a_dry_run_records_nothing(tmp_path):
    app = _crm(tmp_path, [1])
    session = FakeSession(dry_run=True)
    session.results["follow"] = ActionResult("ok", "dry_run", None)

    outcome = _follow(app, session, _actions(1))
    assert len(outcome["followed"]) == 1
    assert not any(c.get("followed_at") for c in app.contact_repo.list_all())


def test_every_bucket_is_present_even_when_nothing_ran():
    blank = empty_follow_outcome("browser gone")
    assert set(blank) == {"followed", "skipped", "failed", "unconfirmed", "stopped"}


# -- through the CLI -----------------------------------------------------------


def _add(runner, name, url):
    assert runner.invoke(cli, ["contacts", "add"], input=f"{name}\nSolutions Engineer\nCo\n{url}\n\n").exit_code == 0


def test_automate_follow_records_the_follow(fake_session):
    runner = CliRunner()
    _add(runner, "Ada", "https://li/in/ada")
    fake_session.results["follow"] = ActionResult("ok", "", None)

    result = runner.invoke(cli, ["automate", "follow", "1"])
    assert result.exit_code == 0, result.output
    assert "Now following Ada" in result.output
    assert _app.contact_repo.list_all()[0]["followed_at"]


def test_automate_follow_due_walks_the_ranked_queue(fake_session):
    runner = CliRunner()
    _add(runner, "Ada", "https://li/in/ada")
    _add(runner, "Grace", "https://li/in/grace")
    fake_session.results["follow"] = ActionResult("ok", "", None)

    result = runner.invoke(cli, ["automate", "follow-due", "--headless"])
    assert result.exit_code == 0, result.output
    assert "Followed Ada" in result.output and "Followed Grace" in result.output
    assert all(c.get("followed_at") for c in _app.contact_repo.list_all())
