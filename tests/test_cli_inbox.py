"""CLI tests for the inbox group and `automate jobs`.

Both drive a browser, so the automation stack is patched the way the rest of the
CLI automation tests do it: `_require_automation` and `_open_linkedin_session`
in `linkedin.cli`.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

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


def _fake_automation(threads=None, pending=None, jobs=None):
    auto = {
        "inbox": MagicMock(),
        "jobs": MagicMock(),
        "SafetyLimits": MagicMock(),
        "PersistentSafetyLimits": MagicMock(),
        "RateLimiter": MagicMock(),
    }
    auto["inbox"].read_inbox.return_value = {
        "threads": threads if threads is not None else [],
        "pending_invitations": pending,
    }
    auto["jobs"].search_jobs.return_value = jobs or []
    return auto


def _run(runner, args, auto, input=None):
    with patch("linkedin.cli._require_automation", return_value=auto), patch(
        "linkedin.cli._open_linkedin_session", return_value=(MagicMock(), MagicMock())
    ), patch("linkedin.cli._close_linkedin_session"):
        return runner.invoke(cli, args, input=input)


class TestInboxSync:
    def test_sync_saves_a_proposal_from_a_reply(self, runner, contact):
        threads = [{
            "name": "Ryan Barner",
            "url": "https://www.linkedin.com/in/ryanbarner",
            "snippet": "Happy to chat next week.",
            "timestamp": "2026-08-29T09:00:00",
            "unread": True,
            "last_from_them": True,
        }]
        result = _run(runner, ["inbox", "sync"], _fake_automation(threads=threads, pending=[]))

        assert result.exit_code == 0
        assert "Ryan Barner" in result.output
        assert "responded" in result.output

    def test_sync_warns_when_the_invitation_list_is_unreadable(self, runner, contact):
        result = _run(runner, ["inbox", "sync"], _fake_automation(pending=None))

        assert result.exit_code == 0
        assert "Could not read the sent-invitation list" in result.output

    def test_sync_reports_a_quiet_inbox(self, runner, contact):
        result = _run(runner, ["inbox", "sync"], _fake_automation(pending=[]))
        assert "No pipeline changes to propose" in result.output


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

    def test_imports_postings(self, runner):
        auto = _fake_automation(jobs=[self.JOB])
        auto["jobs"].import_job_results.return_value = ([self.JOB], 0)

        result = _run(runner, ["automate", "jobs", "-q", "ML Engineer"], auto)

        assert result.exit_code == 0
        assert "ML Engineer" in result.output
        assert "Imported 1 posting" in result.output

    def test_dry_run_does_not_import(self, runner):
        auto = _fake_automation(jobs=[self.JOB])

        result = _run(runner, ["automate", "jobs", "-q", "ML Engineer", "--dry-run"], auto)

        assert "not imported" in result.output
        auto["jobs"].import_job_results.assert_not_called()

    def test_no_results_says_so(self, runner):
        result = _run(runner, ["automate", "jobs", "-q", "Nothing"], _fake_automation(jobs=[]))
        assert "No job results" in result.output
