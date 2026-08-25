"""CLI tests for the `automate` group and the resume-repo applications commands.

Browser-touching commands are tested by patching `_require_automation` and
`_open_linkedin_session` in linkedin.cli, so no Playwright install is needed.
"""

import sqlite3
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import linkedin.cli as cli_mod
import linkedin.data.json_store as js
from linkedin.cli import cli


@pytest.fixture(autouse=True)
def patch_json_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    monkeypatch.setattr(js, "DRAFTS_FILE", tmp_path / "drafts.json")
    monkeypatch.setattr(js, "RESEARCH_FILE", tmp_path / "research.json")
    monkeypatch.setattr(js, "TEMPLATES_FILE", tmp_path / "templates.json")
    monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")


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


class FakeActions:
    """Stands in for the lazily-imported automation namespace."""

    def __init__(self):
        from linkedin.automation.rate_limiter import RateLimiter
        from linkedin.automation.safety import SafetyLimits

        self.page = MagicMock()
        self.browser = MagicMock()
        self.namespace = {
            "RateLimiter": RateLimiter,
            "SafetyLimits": SafetyLimits,
            "PersistentSafetyLimits": SafetyLimits,
            "connect": MagicMock(),
            "easy_apply": MagicMock(),
            "engage": MagicMock(),
            "login": MagicMock(),
            "message": MagicMock(),
            "post": MagicMock(),
            "profile_sync": MagicMock(),
            "scrape": MagicMock(),
        }


@pytest.fixture
def fake_automation(monkeypatch):
    fake = FakeActions()
    monkeypatch.setattr(cli_mod, "_require_automation", lambda: fake.namespace)
    monkeypatch.setattr(cli_mod, "_open_linkedin_session", lambda auto, headless: (fake.browser, fake.page))
    return fake


def _add_contact(runner, name="Alice", url="https://linkedin.com/in/alice"):
    result = runner.invoke(
        cli,
        ["contacts", "add"],
        input=f"{name}\nEngineer\nAcme\n{url}\nnotes\n",
    )
    assert result.exit_code == 0, result.output


def test_automate_connect_sends_and_advances_status(runner, fake_automation):
    _add_contact(runner)
    fake_automation.namespace["connect"].send_connection.return_value = True
    result = runner.invoke(cli, ["automate", "connect", "1", "--note", "Hi!"])
    assert result.exit_code == 0, result.output
    assert "connection_sent" in result.output
    fake_automation.browser.close.assert_called_once()
    contacts = js.load_json(js.CONTACTS_FILE)
    assert contacts[0]["status"] == "connection_sent"


def test_automate_connect_requires_linkedin_url(runner, fake_automation):
    js.save_json(js.CONTACTS_FILE, [{"id": 1, "name": "NoUrl", "status": "not_contacted", "activities": []}])
    result = runner.invoke(cli, ["automate", "connect", "1"])
    assert result.exit_code == 1
    assert "no linkedin_url" in result.output


def test_automate_connect_missing_contact(runner, fake_automation):
    result = runner.invoke(cli, ["automate", "connect", "99"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_automate_connect_dry_run_keeps_status(runner, fake_automation):
    _add_contact(runner)
    fake_automation.namespace["connect"].send_connection.return_value = True
    result = runner.invoke(cli, ["automate", "connect", "1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    contacts = js.load_json(js.CONTACTS_FILE)
    assert contacts[0]["status"] == "not_contacted"


def test_automate_message_uses_draft(runner, fake_automation, tmp_path):
    _add_contact(runner)
    js.save_json(js.DRAFTS_FILE, [{"id": 1, "content": "Hello from draft", "type": "message"}])
    fake_automation.namespace["message"].send_message.return_value = True
    result = runner.invoke(cli, ["automate", "message", "1", "--draft-id", "1"])
    assert result.exit_code == 0, result.output
    args, kwargs = fake_automation.namespace["message"].send_message.call_args
    assert args[2] == "Hello from draft"


def test_automate_message_requires_text(runner, fake_automation):
    _add_contact(runner)
    result = runner.invoke(cli, ["automate", "message", "1"])
    assert result.exit_code == 1
    assert "Nothing to send" in result.output


def test_automate_post_from_calendar_marks_posted(runner, fake_automation):
    js.save_json(js.DRAFTS_FILE, [{"id": 1, "content": "My scheduled post", "type": "post"}])
    result = runner.invoke(cli, ["calendar", "add", "--title", "Post", "--date", "2026-03-01", "--draft-id", "1"])
    assert result.exit_code == 0, result.output
    fake_automation.namespace["post"].publish_post.return_value = (True, "posted")
    result = runner.invoke(cli, ["automate", "post", "--calendar-id", "1"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "published" in result.output
    listing = runner.invoke(cli, ["calendar", "list"])
    assert "posted" in listing.output


def test_automate_post_requires_content(runner, fake_automation):
    result = runner.invoke(cli, ["automate", "post"])
    assert result.exit_code == 1
    assert "Nothing to post" in result.output


def test_automate_post_declined_confirmation(runner, fake_automation):
    result = runner.invoke(cli, ["automate", "post", "--text", "hello"], input="n\n")
    assert result.exit_code == 0
    fake_automation.namespace["post"].publish_post.assert_not_called()


def test_automate_engage_contacts_and_feed(runner, fake_automation):
    _add_contact(runner)
    fake_automation.namespace["engage"].like_contact_posts.return_value = 2
    fake_automation.namespace["engage"].like_feed_posts.return_value = 3
    result = runner.invoke(cli, ["automate", "engage", "--contact-id", "1", "--feed", "--likes", "2"])
    assert result.exit_code == 0, result.output
    assert "5 post(s) total" in result.output


def test_automate_engage_requires_target(runner, fake_automation):
    result = runner.invoke(cli, ["automate", "engage"])
    assert result.exit_code == 1


def test_automate_sync_profile(runner, fake_automation):
    fake_automation.namespace["profile_sync"].sync_profile.return_value = {"headline": "updated", "about": "skipped"}
    result = runner.invoke(cli, ["automate", "sync-profile", "--headline", "Builder of things"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "updated" in result.output


def test_automate_sync_profile_failure_exits_nonzero(runner, fake_automation):
    fake_automation.namespace["profile_sync"].sync_profile.return_value = {"headline": "failed", "about": "skipped"}
    result = runner.invoke(cli, ["automate", "sync-profile", "--headline", "X"], input="y\n")
    assert result.exit_code == 1


def test_automate_easy_apply_submits_and_advances(runner, fake_automation, resume_repo, monkeypatch):
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
    fake_automation.namespace["easy_apply"].apply_to_job.return_value = {"status": "submitted", "detail": "ok"}
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--submit", "--headless"])
    assert result.exit_code == 0, result.output
    assert "applied" in result.output
    # The matched variant's PDF was passed through
    _, kwargs = fake_automation.namespace["easy_apply"].apply_to_job.call_args
    assert kwargs["resume_path"].endswith("ai-engineer-resume.pdf")
    view = runner.invoke(cli, ["applications", "view", "1"])
    assert "applied" in view.output


def test_automate_easy_apply_dry_run_skips_browser(runner, fake_automation, monkeypatch):
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev", "-u", "https://x/1"])
    result = runner.invoke(cli, ["automate", "easy-apply", "1", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    fake_automation.namespace["easy_apply"].apply_to_job.assert_not_called()


def test_automate_easy_apply_requires_url(runner, fake_automation):
    runner.invoke(cli, ["applications", "add", "-c", "Acme", "-t", "Dev"])
    result = runner.invoke(cli, ["automate", "easy-apply", "1"])
    assert result.exit_code == 1
    assert "no job URL" in result.output


def test_automate_limits_table(runner, tmp_path, monkeypatch):
    import linkedin.automation.safety as safety_mod

    monkeypatch.setattr(safety_mod, "USAGE_FILE", tmp_path / "usage.json")
    result = runner.invoke(cli, ["automate", "limits"])
    assert result.exit_code == 0, result.output
    assert "Connections" in result.output and "Easy Applies" in result.output


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
    apps = js.load_json(js.APPLICATIONS_FILE)
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
