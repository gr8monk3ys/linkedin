"""CLI tests for the `automate` group and the resume-repo applications commands.

Browser-touching commands are tested through the session port: `fake_session`
(conftest) makes `LinkedInSession.open` yield a FakeSession with scripted
results, so no Playwright install is needed and the test checks what the
command asked the session to do.
"""

import sqlite3

import pytest
from click.testing import CliRunner

import linkedin.cli as cli_mod
from linkedin.automation.session import ActionResult
from linkedin.cli import cli
from linkedin.data.json_store import load_json, save_json


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def resume_repo(tmp_path):
    root = tmp_path / "resume"
    (root / "variants" / "ai-engineer" / "sections").mkdir(parents=True)
    (root / "variants" / "ai-engineer" / "sections" / "skills.tex").write_text(
        "\\skillrow{LLM}{RAG, LangChain, PyTorch}\n"
    )
    (root / "output").mkdir()
    (root / "output" / "ai-engineer-resume.pdf").write_bytes(b"%PDF-fake")
    return root


def _add_contact(runner, name="Alice", url="https://linkedin.com/in/alice"):
    result = runner.invoke(
        cli,
        ["contacts", "add"],
        input=f"{name}\nEngineer\nAcme\n{url}\nnotes\n",
    )
    assert result.exit_code == 0, result.output


def test_automate_connect_sends_and_advances_status(runner, fake_session):
    _add_contact(runner)
    result = runner.invoke(cli, ["automate", "connect", "1", "--note", "Hi!"])
    assert result.exit_code == 0, result.output
    assert "connection_sent" in result.output
    assert fake_session.calls_to("connect") == [(("https://linkedin.com/in/alice",), {"note": "Hi!"})]
    assert fake_session.closed
    contacts = load_json(cli_mod._app.data_dir.contacts)
    assert contacts[0]["status"] == "connection_sent"


def test_automate_connect_skipped_exits_nonzero_and_keeps_status(runner, fake_session):
    _add_contact(runner)
    fake_session.results["connect"] = ActionResult("skipped", "no Connect button, or already connected/pending")
    result = runner.invoke(cli, ["automate", "connect", "1"])
    assert result.exit_code == 1
    assert "no Connect button" in result.output
    assert load_json(cli_mod._app.data_dir.contacts)[0]["status"] == "not_contacted"


def test_automate_connect_refused_by_budget(runner, fake_session):
    _add_contact(runner)
    fake_session.results["connect"] = ActionResult("refused", "daily connection limit reached")
    result = runner.invoke(cli, ["automate", "connect", "1"])
    assert result.exit_code == 1
    assert "limit" in result.output


def test_selector_misses_are_reported_after_the_session(runner, fake_session):
    _add_contact(runner)
    fake_session.health = {"healthy": False, "misses": ["connect_button"], "selectors": {"connect_button": "button.x"}}
    result = runner.invoke(cli, ["automate", "connect", "1"])
    assert "markup may have changed" in result.output
    assert "button.x" in result.output


def test_automate_connect_requires_linkedin_url(runner, fake_session):
    save_json(cli_mod._app.data_dir.contacts, [{"id": 1, "name": "NoUrl", "status": "not_contacted", "activities": []}])
    result = runner.invoke(cli, ["automate", "connect", "1"])
    assert result.exit_code == 1
    assert "no linkedin_url" in result.output


def test_automate_connect_missing_contact(runner, fake_session):
    result = runner.invoke(cli, ["automate", "connect", "99"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_automate_connect_dry_run_keeps_status(runner, fake_session):
    _add_contact(runner)
    result = runner.invoke(cli, ["automate", "connect", "1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert fake_session.opened_with["dry_run"] is True
    contacts = load_json(cli_mod._app.data_dir.contacts)
    assert contacts[0]["status"] == "not_contacted"


def test_automate_message_uses_draft(runner, fake_session, tmp_path):
    _add_contact(runner)
    save_json(cli_mod._app.data_dir.drafts, [{"id": 1, "content": "Hello from draft", "type": "message", "source": "ai"}])
    result = runner.invoke(cli, ["automate", "message", "1", "--draft-id", "1"])
    assert result.exit_code == 0, result.output
    (args, _), = fake_session.calls_to("message")
    assert args[1] == "Hello from draft"
    assert load_json(cli_mod._app.data_dir.contacts)[0]["status"] == "messaged"


def test_automate_message_requires_text(runner, fake_session):
    _add_contact(runner)
    result = runner.invoke(cli, ["automate", "message", "1"])
    assert result.exit_code == 1
    assert "Nothing to send" in result.output


def test_automate_post_from_calendar_marks_posted(runner, fake_session):
    save_json(cli_mod._app.data_dir.drafts, [{"id": 1, "content": "My scheduled post", "type": "post", "source": "ai"}])
    result = runner.invoke(cli, ["calendar", "add", "--title", "Post", "--date", "2026-03-01", "--draft-id", "1"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["automate", "post", "--calendar-id", "1"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "published" in result.output
    listing = runner.invoke(cli, ["calendar", "list"])
    assert "posted" in listing.output


def test_automate_post_records_the_urn(runner, fake_session):
    fake_session.results["post"] = ActionResult("ok", data="urn:li:activity:42")
    result = runner.invoke(cli, ["automate", "post", "--text", "Shipped"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "urn:li:activity:42" in result.output
    assert cli_mod._app.post_svc.list_posts()[0]["urn"] == "urn:li:activity:42"
    listing = runner.invoke(cli, ["posts", "list"])
    assert "urn:li:activity:42" in listing.output


def test_automate_post_degraded_says_the_id_is_missing(runner, fake_session):
    """The post is live; the CLI must say it cannot be joined to metrics, not 'published'."""
    fake_session.results["post"] = ActionResult("ok", "posted, but the post's URN could not be read back")
    result = runner.invoke(cli, ["automate", "post", "--text", "Shipped"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "could not be read back" in result.output
    assert cli_mod._app.post_svc.unmeasurable()
    listing = runner.invoke(cli, ["posts", "list"])
    assert "unreadable" in listing.output and "cannot be joined" in listing.output


def test_automate_post_failed_records_nothing(runner, fake_session):
    fake_session.results["post"] = ActionResult("failed", "post_editor not found")
    result = runner.invoke(cli, ["automate", "post", "--text", "Shipped"], input="y\n")
    assert result.exit_code == 1
    assert cli_mod._app.post_svc.list_posts() == []


def test_automate_post_refuses_template_draft(runner, fake_session):
    """A template is not a draft; it must never go out under the user's name."""
    save_json(cli_mod._app.data_dir.drafts, [{"id": 1, "content": "Hi there", "type": "post", "source": "template"}])
    result = runner.invoke(cli, ["automate", "post", "--draft-id", "1"], input="y\n")
    assert result.exit_code == 1
    assert "offline template" in result.output
    assert fake_session.calls_to("post") == []


def test_automate_post_refuses_draft_of_unknown_provenance(runner, fake_session):
    """Rows saved before provenance was recorded include the templates from 150 unattended runs."""
    save_json(cli_mod._app.data_dir.drafts, [{"id": 1, "content": "Hi there", "type": "post"}])
    result = runner.invoke(cli, ["automate", "post", "--draft-id", "1"], input="y\n")
    assert result.exit_code == 1
    assert "unknown provenance" in result.output
    assert fake_session.calls_to("post") == []


def test_automate_message_refuses_template_draft(runner, fake_session):
    _add_contact(runner)
    save_json(cli_mod._app.data_dir.drafts, [{"id": 1, "content": "Hi there", "type": "message", "source": "template"}])
    result = runner.invoke(cli, ["automate", "message", "1", "--draft-id", "1"])
    assert result.exit_code == 1
    assert fake_session.calls_to("message") == []


def test_automate_post_requires_content(runner, fake_session):
    result = runner.invoke(cli, ["automate", "post"])
    assert result.exit_code == 1
    assert "Nothing to post" in result.output


def test_automate_post_declined_confirmation(runner, fake_session):
    result = runner.invoke(cli, ["automate", "post", "--text", "hello"], input="n\n")
    assert result.exit_code == 0
    assert fake_session.calls_to("post") == []


def test_automate_engage_contacts_and_feed(runner, fake_session):
    _add_contact(runner)
    fake_session.results["react"] = ActionResult("ok", data=2)
    result = runner.invoke(cli, ["automate", "engage", "--contact-id", "1", "--feed", "--likes", "2"])
    assert result.exit_code == 0, result.output
    assert "4 post(s) total" in result.output
    calls = fake_session.calls_to("react")
    assert calls == [((2,), {"profile_url": "https://linkedin.com/in/alice"}), ((2,), {})]


def test_automate_engage_requires_target(runner, fake_session):
    result = runner.invoke(cli, ["automate", "engage"])
    assert result.exit_code == 1


def test_automate_sync_profile(runner, fake_session):
    fake_session.results["sync_profile"] = ActionResult("ok", data={"headline": "updated"})
    result = runner.invoke(cli, ["automate", "sync-profile", "--headline", "Builder of things"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "updated" in result.output
    assert fake_session.calls_to("sync_profile") == [((), {"headline": "Builder of things", "about": ""})]


def test_automate_sync_profile_failure_exits_nonzero(runner, fake_session):
    fake_session.results["sync_profile"] = ActionResult("failed", "editor", data={"headline": "failed"})
    result = runner.invoke(cli, ["automate", "sync-profile", "--headline", "X"], input="y\n")
    assert result.exit_code == 1


def test_automate_easy_apply_submits_and_advances(runner, fake_session, resume_repo, monkeypatch):
    monkeypatch.setenv("LINKEDIN_RESUME_REPO", str(resume_repo))
    result = runner.invoke(
        cli,
        [
            "applications",
            "add",
            "-c",
            "Acme",
            "-t",
            "AI Engineer",
            "-u",
            "https://linkedin.com/jobs/view/1",
            "--jd",
            "RAG and LangChain work",
        ],
    )
    assert result.exit_code == 0, result.output
    fake_session.results["easy_apply"] = ActionResult("ok", data={"status": "submitted", "detail": "ok"})
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--submit", "--headless"])
    assert result.exit_code == 0, result.output
    assert "applied" in result.output
    # The matched variant's PDF was passed through
    (_, kwargs), = fake_session.calls_to("easy_apply")
    assert kwargs["resume_path"].endswith("ai-engineer-resume.pdf")
    assert kwargs["submit"] is True
    view = runner.invoke(cli, ["applications", "view", "1"])
    assert "applied" in view.output


def test_automate_easy_apply_dry_run_skips_browser(runner, fake_session, monkeypatch):
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev", "-u", "https://x/1"])
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert fake_session.opened_with == {}  # no session was opened at all


def test_automate_easy_apply_requires_url(runner, fake_session):
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev"])
    result = runner.invoke(cli, ["automate", "easy-apply", "1"])
    assert result.exit_code == 1
    assert "no job URL" in result.output


def test_automate_limits_table_and_set(runner):
    result = runner.invoke(cli, ["automate", "limits"])
    assert result.exit_code == 0, result.output
    assert "connection" in result.output and "easy_apply" in result.output
    assert "limits.json" in result.output
    result = runner.invoke(cli, ["automate", "limits", "set", "reaction", "9"])
    assert result.exit_code == 0, result.output
    assert "9" in runner.invoke(cli, ["automate", "limits"]).output
    result = runner.invoke(cli, ["automate", "limits", "set", "likes", "9"])
    assert result.exit_code == 1
    assert "Unknown kind" in result.output


# ---------------------------------------------------------------------------
# applications × resume repo commands
# ---------------------------------------------------------------------------


def test_applications_suggest_resume(runner, resume_repo):
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "AI Engineer", "--jd", "RAG, LangChain, PyTorch"])
    result = runner.invoke(cli, ["applications", "suggest-resume", "1", "--resume-repo", str(resume_repo)])
    assert result.exit_code == 0, result.output
    assert "ai-engineer" in result.output


def test_applications_suggest_resume_no_repo(runner, monkeypatch):
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev"])
    result = runner.invoke(cli, ["applications", "suggest-resume", "1"])
    assert result.exit_code == 1
    assert "LINKEDIN_RESUME_REPO" in result.output


def test_applications_attach_resume_auto_match(runner, resume_repo):
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "AI Engineer", "--jd", "RAG and LangChain"])
    result = runner.invoke(cli, ["applications", "attach-resume", "1", "--resume-repo", str(resume_repo)])
    assert result.exit_code == 0, result.output
    assert "ai-engineer" in result.output
    apps = load_json(cli_mod._app.data_dir.applications)
    assert apps[0]["resume_variant"] == "ai-engineer"
    assert apps[0]["resume_path"].endswith("ai-engineer-resume.pdf")


def test_applications_attach_resume_unknown_variant(runner, resume_repo):
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev"])
    result = runner.invoke(
        cli, ["applications", "attach-resume", "1", "--variant", "nope", "--resume-repo", str(resume_repo)]
    )
    assert result.exit_code == 1
    assert "Unknown variant" in result.output


def test_applications_import_autoapply(runner, resume_repo):
    db_dir = resume_repo / "output" / "autoapply"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "state.db")
    conn.executescript(
        """
        CREATE TABLE jobs (id INTEGER PRIMARY KEY, company TEXT, title TEXT, url TEXT,
                           description TEXT, status TEXT, variant TEXT);
        CREATE TABLE applications (id INTEGER PRIMARY KEY, job_id INTEGER, status TEXT,
                                   resume_path TEXT, cover_path TEXT, submitted_at TEXT);
        INSERT INTO jobs (company, title, url, description, status, variant)
        VALUES ('Acme', 'ML Engineer', 'https://x/1', 'desc', 'submitted', 'ai-engineer');
        """
    )
    conn.commit()
    conn.close()
    result = runner.invoke(cli, ["applications", "import-autoapply", "--resume-repo", str(resume_repo)])
    assert result.exit_code == 0, result.output
    assert "Imported 1 application" in result.output
    # Second run dedupes
    result = runner.invoke(cli, ["applications", "import-autoapply", "--resume-repo", str(resume_repo)])
    assert "Imported 0 application" in result.output
    assert "1 already tracked" in result.output


def test_easy_apply_hands_a_question_step_to_the_human_when_headful(runner, fake_session, monkeypatch):
    """A required question the automation cannot answer is not a failure when a
    person is watching the browser. Closing the window on `needs_manual_input`
    threw away a half-completed application every time a wizard asked
    anything -- which is most of them."""
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "SE", "-u", "https://x/1"])
    fake_session.results["easy_apply"] = ActionResult(
        "skipped", "needs_manual_input", {"status": "needs_manual_input", "detail": "Form has required fields that need manual answers"}
    )
    # Person finishes the form in the window, then confirms they submitted.
    # (`click.pause` is a no-op without a TTY, so only the confirm reads input.)
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--submit"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "finish" in result.output.lower()
    assert fake_session.budget.used["easy_apply"] == 1  # their word records it
    view = runner.invoke(cli, ["applications", "view", "1"])
    assert "applied" in view.output


def test_easy_apply_question_step_not_submitted_stays_saved(runner, fake_session, monkeypatch):
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "SE", "-u", "https://x/1"])
    fake_session.results["easy_apply"] = ActionResult("skipped", "needs_manual_input", {"status": "needs_manual_input", "detail": "required fields"})
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--submit"], input="n\n")
    assert result.exit_code == 0, result.output
    view = runner.invoke(cli, ["applications", "view", "1"])
    assert "applied" not in view.output


def test_easy_apply_question_step_headless_is_still_a_failure(runner, fake_session, monkeypatch):
    """With nobody watching there is no one to hand the form to."""
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "SE", "-u", "https://x/1"])
    fake_session.results["easy_apply"] = ActionResult("skipped", "needs_manual_input", {"status": "needs_manual_input", "detail": "required fields"})
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--submit", "--headless"])
    assert result.exit_code == 1
