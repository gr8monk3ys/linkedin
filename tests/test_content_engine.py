"""Fleet facts → candidates → review → publish, with the three rules enforced."""

import json
from datetime import date
from unittest.mock import patch

import pytest

from linkedin.ai.client import AIClientError
from linkedin.app import App
from linkedin.data.paths import DataDir
from linkedin.services.content_service import build_prompt, next_publish_date
from linkedin.services.fleet_facts import collect_fleet_facts, facts_digest

REPOS = [
    {"name": "alpha", "pushedAt": "2026-09-02T10:00:00Z", "stargazerCount": 3, "description": "Alpha thing"},
    {"name": "beta", "pushedAt": "2026-09-01T10:00:00Z", "stargazerCount": 0, "description": None},
]
PRS = [
    {"repository": {"name": "alpha"}, "title": "feat: x", "author": {"login": "gr8monk3ys"}, "url": "u1", "number": 1},
    {
        "repository": {"name": "alpha"},
        "title": "chore(deps): bump y",
        "author": {"login": "app/dependabot"},
        "url": "u2",
        "number": 2,
    },
    {
        "repository": {"name": "secret"},
        "title": "private work",
        "author": {"login": "gr8monk3ys"},
        "url": "u3",
        "number": 3,
    },
]


def fake_gh(args):
    if args[0] == "repo":
        assert "--visibility" in args and args[args.index("--visibility") + 1] == "public"
        return json.dumps(REPOS)
    assert args[:2] == ["search", "prs"] and "--visibility" in args
    return json.dumps(PRS)


def test_facts_come_from_public_repos_only_and_split_bots():
    facts = collect_fleet_facts(7, run=fake_gh, today=date(2026, 9, 2))
    assert facts["public_repos"] == 2 and facts["since"] == "2026-08-26"
    assert facts["merged_total"] == 2 and facts["merged_by_human"] == 1 and facts["merged_by_bots"] == 1
    assert facts["top_repos"] == [{"name": "alpha", "merged": 2}]
    assert "secret" not in json.dumps(facts)  # a PR in a repo not in the public list is dropped
    digest = facts_digest(facts)
    assert "pull requests merged: 2 (1 authored, 1 from bots" in digest and "no description" in digest


def test_prompt_fences_the_facts_as_data():
    facts = collect_fleet_facts(7, run=fake_gh, today=date(2026, 9, 2))
    prompt = build_prompt({"headline": "ML Engineer"}, facts, "story")
    body = prompt.split("<<<DATA>>>")[1].split("<<<END DATA>>>")[0]
    assert "public repositories: 2" in body
    assert "never an instruction" in prompt and "No hashtags" in prompt


def test_next_publish_date_is_the_following_tuesday():
    assert next_publish_date(date(2026, 9, 6)) == "2026-09-08"  # Sunday → Tuesday
    assert next_publish_date(date(2026, 9, 8)) == "2026-09-15"  # Tuesday → next Tuesday, never today


def _svc(tmp_path):
    app = App(DataDir(tmp_path))
    app.profile_repo.save({"name": "Me", "headline": "ML Engineer"})
    return app, app.content_svc


def test_candidates_are_saved_as_ai_drafts_and_never_templates(tmp_path):
    app, svc = _svc(tmp_path)
    facts = collect_fleet_facts(7, run=fake_gh, today=date(2026, 9, 2))
    with patch("linkedin.ai.client.generate_with_ai", return_value="A real post.\n\nWhat would you do?"):
        results = svc.draft_candidates(facts, count=2)
    assert [s for s, _ in results] == ["story", "contrarian"] and all(r.ok for _, r in results)
    draft = svc.save_candidate(results[0][1].text, "story", facts)
    assert draft["source"] == "ai" and draft["type"] == "post_fleet" and draft["review"] == "pending"
    with patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("down")):
        ((style, result),) = svc.draft_candidates(facts, count=1)
    assert not result.ok and result.was_fallback is False  # no fallback exists on this path


def test_approve_schedules_one_entry_and_reject_marks(tmp_path):
    app, svc = _svc(tmp_path)
    facts = {"since": "a", "until": "b"}
    d1 = svc.save_candidate("First line here\nmore", "story", facts)
    d2 = svc.save_candidate("Second", "how-to", facts)
    entry = svc.approve(d1["id"], publish_on="2026-09-08")
    assert (
        entry["draft_id"] == d1["id"]
        and entry["title"] == "First line here"
        and entry["scheduled_date"] == "2026-09-08"
    )
    assert svc.reject(d2["id"]) and svc.pending_candidates() == []
    assert svc.approve(999) is None


def _post(svc, i, impressions):
    svc.posts.add(
        {
            "id": i,
            "urn": f"urn:li:activity:{i}",
            "text": "x",
            "posted_at": f"2026-08-{i:02d}T09:00:00",
            "impressions": impressions,
        }
    )


def test_skip_rule_needs_history_then_fires_when_the_last_three_all_underperform(tmp_path):
    app, svc = _svc(tmp_path)
    assert svc.underperformance() is None
    for i, n in enumerate([100, 120, 110, 40, 30, 20], start=1):
        _post(svc, i, n)
    reason = svc.underperformance()
    assert reason and "[40, 30, 20]" in reason and "110" in reason
    svc.posts.add(
        {"id": 7, "urn": "urn:li:activity:7", "text": "x", "posted_at": "2026-08-07T09:00:00", "impressions": 500}
    )
    assert svc.underperformance() is None  # one good post breaks the streak


def test_publish_decision_respects_due_date_and_skip_rule(tmp_path):
    app, svc = _svc(tmp_path)
    assert svc.publish_decision(today=date(2026, 9, 8))["skip"] == "nothing is due"
    d = svc.save_candidate("Post text", "story", {"since": "a", "until": "b"})
    svc.approve(d["id"], publish_on="2026-09-08")
    assert svc.publish_decision(today=date(2026, 9, 7))["skip"] == "nothing is due"
    ok = svc.publish_decision(today=date(2026, 9, 8))
    assert ok["skip"] is None and ok["draft"]["id"] == d["id"]
    for i, n in enumerate([100, 100, 10, 10, 10], start=1):
        _post(svc, i, n)
    assert svc.publish_decision(today=date(2026, 9, 8))["skip"]
    assert svc.publish_decision(today=date(2026, 9, 8), force=True)["skip"] is None


def test_a_non_ai_draft_on_the_calendar_is_never_published(tmp_path):
    app, svc = _svc(tmp_path)
    app.draft_repo.add({"id": 5, "type": "post_fleet", "content": "old template", "source": "template"})
    svc.calendar.add(
        {
            "id": 1,
            "title": "t",
            "scheduled_date": "2026-09-01",
            "status": "scheduled",
            "platform": "linkedin",
            "draft_id": 5,
            "actual_posted_date": None,
            "created_at": "x",
        }
    )
    assert "not an AI draft" in svc.publish_decision(today=date(2026, 9, 8))["skip"]


# -- CLI ------------------------------------------------------------------------


@pytest.fixture
def facts_patched(monkeypatch):
    import linkedin.cli.posts as cli_mod

    monkeypatch.setattr(
        cli_mod, "collect_fleet_facts", lambda days=7: collect_fleet_facts(days, run=fake_gh, today=date(2026, 9, 2))
    )


def test_draft_week_with_ai_down_saves_nothing_and_exits_nonzero(facts_patched):
    from click.testing import CliRunner

    from linkedin.cli import _app, cli

    with patch("linkedin.ai.client.generate_with_ai", side_effect=AIClientError("401 invalid x-api-key")):
        result = CliRunner().invoke(cli, ["posts", "draft-week", "--count", "2"])
    assert result.exit_code == 1
    assert "No candidates" in result.output and "never a post" in result.output
    assert _app.draft_repo.list_all() == []


def test_draft_week_review_and_publish_due(facts_patched, fake_session):
    from click.testing import CliRunner

    from linkedin.automation.session import ActionResult
    from linkedin.cli import _app, cli

    runner = CliRunner()
    with patch("linkedin.ai.client.generate_with_ai", return_value="Hook line\n\nBody. What would you change?"):
        result = runner.invoke(cli, ["posts", "draft-week", "--count", "2"])
    assert result.exit_code == 0, result.output
    assert "2 candidate(s) saved" in result.output

    result = runner.invoke(cli, ["posts", "review", "--publish-on", "2000-01-01"], input="a\nr\n")
    assert result.exit_code == 0, result.output
    assert "Approved 1" in result.output and "rejected 1" in result.output
    assert _app.calendar_repo.list_all()[0]["draft_id"] == 1

    fake_session.results["post"] = ActionResult("ok", data="urn:li:activity:77")
    result = runner.invoke(cli, ["posts", "publish-due"])
    assert result.exit_code == 0, result.output
    assert "urn:li:activity:77" in result.output
    assert _app.calendar_repo.list_all()[0]["status"] == "posted"
    assert _app.post_svc.list_posts()[0]["draft_id"] == 1
    assert "Nothing is due" in runner.invoke(cli, ["posts", "publish-due"]).output


def test_publish_due_skips_by_default_when_underperforming(fake_session):
    from click.testing import CliRunner

    from linkedin.cli import _app, cli

    svc = _app.content_svc
    d = svc.save_candidate("Post text", "story", {"since": "a", "until": "b"})
    svc.approve(d["id"], publish_on="2000-01-01")
    for i, n in enumerate([100, 100, 5, 5, 5], start=1):
        _post(svc, i, n)
    result = CliRunner().invoke(cli, ["posts", "publish-due"])
    assert result.exit_code == 2 and "Skipping" in result.output
    assert fake_session.calls_to("post") == []
    assert _app.calendar_repo.list_all()[0]["status"] == "scheduled"


def test_a_hand_written_candidate_is_marked_as_one(tmp_path):
    """Both are `source: ai`, which only means "not an offline template".
    `generated_from` is what tells a typed post from a generated one."""
    app = App(DataDir(tmp_path))
    svc = app.content_svc
    typed = svc.save_candidate("Typed by a person.", "story", {"since": "hand", "until": "x"}, hand_written=True)
    generated = svc.save_candidate("Written by the model.", "story", {"since": "a", "until": "b"})
    assert typed["source"] == "ai" and typed["generated_from"] == "hand-written"
    assert generated["source"] == "ai" and generated["generated_from"] == "model"
