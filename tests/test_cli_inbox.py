"""CLI tests for the inbox group and `automate jobs`.

Both drive a browser, so they go through the session port: `fake_session`
yields a FakeSession with scripted `inbox` / `jobs` results.
"""

import pytest
from click.testing import CliRunner

from linkedin.automation.session import ActionResult
from linkedin.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def contact(runner):
    from linkedin.cli import _app

    record = {
        "id": 1,
        "name": "Ryan Barner",
        "company": "Netflix",
        "status": "messaged",
        "linkedin_url": "https://www.linkedin.com/in/ryanbarner",
        "last_contact": "2026-08-20T10:00:00",
        "created_at": "2026-08-20T10:00:00",
        "activities": [],
    }
    _app.contact_repo.add(record)
    return record


def _run(runner, args, fake_session, threads=None, pending=None, jobs=None, status="ok", input=None):
    fake_session.results["inbox"] = ActionResult(status, data={"threads": threads or [], "pending_invitations": pending})
    fake_session.results["jobs"] = ActionResult(status, data=jobs or [])
    return runner.invoke(cli, args, input=input)


class TestInboxSync:
    def test_sync_saves_a_proposal_from_a_reply(self, runner, contact, fake_session):
        threads = [{
            "name": "Ryan Barner",
            "url": "https://www.linkedin.com/in/ryanbarner",
            "snippet": "Happy to chat next week.",
            "timestamp": "2026-08-29T09:00:00",
            "unread": True,
            "last_from_them": True,
        }]
        result = _run(runner, ["inbox", "sync"], fake_session, threads=threads, pending=[])

        assert result.exit_code == 0
        assert "Ryan Barner" in result.output
        assert "responded" in result.output

    def test_sync_warns_when_the_invitation_list_is_unreadable(self, runner, contact, fake_session):
        result = _run(runner, ["inbox", "sync"], fake_session, pending=None)

        assert result.exit_code == 0
        assert "Could not read the sent-invitation list" in result.output

    def test_sync_reports_a_quiet_inbox(self, runner, contact, fake_session):
        result = _run(runner, ["inbox", "sync"], fake_session, pending=[])
        assert "No pipeline changes to propose" in result.output

    def test_sync_keeps_a_thread_index_and_counts_strangers(self, runner, contact, fake_session):
        from linkedin.cli import _app
        from linkedin.data.json_store import load_json

        threads = [
            {"name": "Ryan Barner", "url": "https://www.linkedin.com/in/ryanbarner", "snippet": "hi", "timestamp": "Yesterday", "unread": False, "last_from_them": True},
            {"name": "Sam Stranger", "url": "https://www.linkedin.com/in/sam", "snippet": "Are you open to a role?", "timestamp": "Yesterday", "unread": True, "last_from_them": True},
        ]
        result = _run(runner, ["inbox", "sync"], fake_session, threads=threads, pending=[])
        assert result.exit_code == 0, result.output
        assert "1 inbound from strangers" in result.output
        index = load_json(_app.data_dir.thread_index, [])
        assert {r["name"] for r in index} == {"Ryan Barner", "Sam Stranger"}
        assert "Are you open" not in str(index)

        listing = runner.invoke(cli, ["inbox", "strangers"])
        assert "Sam Stranger" in listing.output and "Ryan Barner" not in listing.output

    def test_strangers_with_no_index_points_at_sync(self, runner):
        result = runner.invoke(cli, ["inbox", "strangers"])
        assert result.exit_code == 0
        assert "0" in result.output and "inbox sync" in result.output

    def test_sync_refused_by_budget_proposes_nothing_and_says_why(self, runner, contact, fake_session):
        result = _run(runner, ["inbox", "sync"], fake_session, pending=None, status="refused")
        assert result.exit_code == 0
        assert "Inbox not read" in result.output
        assert "skipping acceptance checks" in result.output


class TestInboxReview:
    @pytest.fixture
    def proposal(self):
        from linkedin.cli import save_inbox_proposals

        save_inbox_proposals([{
            "contact_id": 1,
            "name": "Ryan Barner",
            "company": "Netflix",
            "from_status": "messaged",
            "to_status": "responded",
            "source": "messaging",
            "confidence": "high",
            "evidence": 'Replied: "Happy to chat"',
            "detected_at": "2026-08-30T20:00:00",
        }])

    def test_confirming_applies_the_transition(self, runner, contact, proposal):
        from linkedin.cli import _app, load_inbox_proposals

        result = runner.invoke(cli, ["inbox", "review"], input="y\n")

        assert result.exit_code == 0
        assert _app.contact_repo.get(1)["status"] == "responded"
        assert load_inbox_proposals() == []

    def test_declining_leaves_the_contact_alone_and_keeps_the_proposal(self, runner, contact, proposal):
        from linkedin.cli import _app, load_inbox_proposals

        result = runner.invoke(cli, ["inbox", "review"], input="n\n")

        assert result.exit_code == 0
        assert _app.contact_repo.get(1)["status"] == "messaged"
        assert len(load_inbox_proposals()) == 1

    def test_stale_proposal_is_dropped_when_the_status_moved_on(self, runner, contact, proposal):
        """A status changed by hand since the sync must win over the proposal."""
        from linkedin.cli import _app

        record = _app.contact_repo.get(1)
        record["status"] = "call_scheduled"
        _app.contact_repo.update(record)

        result = runner.invoke(cli, ["inbox", "review"], input="\n")

        assert "dropping this proposal" in result.output
        assert _app.contact_repo.get(1)["status"] == "call_scheduled"

    def test_yes_flag_applies_high_confidence_without_prompting(self, runner, contact, proposal):
        from linkedin.cli import _app

        result = runner.invoke(cli, ["inbox", "review", "--yes"])

        assert result.exit_code == 0
        assert _app.contact_repo.get(1)["status"] == "responded"

    def test_yes_flag_still_prompts_for_a_low_confidence_proposal(self, runner, contact):
        """--yes must not silently apply a match made on display name alone."""
        from linkedin.cli import _app, save_inbox_proposals

        save_inbox_proposals([{
            "contact_id": 1,
            "name": "Ryan Barner",
            "from_status": "messaged",
            "to_status": "responded",
            "source": "messaging",
            "confidence": "low",
            "evidence": "matched on name only",
        }])

        result = runner.invoke(cli, ["inbox", "review", "--yes"], input="n\n")

        assert "Apply?" in result.output
        assert _app.contact_repo.get(1)["status"] == "messaged"

    def test_review_with_nothing_pending(self, runner):
        result = runner.invoke(cli, ["inbox", "review"])
        assert "No pending proposals" in result.output


class TestAutomateJobs:
    JOB = {
        "title": "ML Engineer",
        "company": "Netflix",
        "location": "Los Angeles",
        "url": "https://www.linkedin.com/jobs/view/1",
        "easy_apply": True,
    }

    def test_imports_postings(self, runner, fake_session):
        from linkedin.cli import _app

        result = _run(runner, ["automate", "jobs", "-q", "ML Engineer"], fake_session, jobs=[self.JOB])

        assert result.exit_code == 0, result.output
        assert "ML Engineer" in result.output
        assert "Imported 1 posting" in result.output
        assert _app.market_svc.list_postings()[0]["company"] == "Netflix"
        assert fake_session.calls_to("jobs") == [(("ML Engineer",), {"location": "", "limit": 25})]

    def test_dry_run_does_not_import(self, runner, fake_session):
        from linkedin.cli import _app

        result = _run(runner, ["automate", "jobs", "-q", "ML Engineer", "--dry-run"], fake_session, jobs=[self.JOB])

        assert "not imported" in result.output
        assert _app.market_svc.list_postings() == []
        assert fake_session.opened_with["dry_run"] is True

    def test_no_results_says_so(self, runner, fake_session):
        result = _run(runner, ["automate", "jobs", "-q", "Nothing"], fake_session, jobs=[])
        assert "No job results" in result.output
