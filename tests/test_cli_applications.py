"""CLI integration tests for applications, interview, conversations, and calendar commands."""

import pytest
from click.testing import CliRunner

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


def _setup_profile_no_resume(runner):
    """Set up a named profile without resume text."""
    runner.invoke(
        cli,
        ["profile", "setup"],
        input="Test User\nML Engineer\nML Engineer\nPython, ML\nexp\nunique\nTech\nSF\nn\n",
    )


def _setup_profile_with_resume(runner, resume="5 years Python experience"):
    """Set up a profile with resume text (two blank lines terminate the paste)."""
    runner.invoke(
        cli,
        ["profile", "setup"],
        input=f"Test User\nML Engineer\nML Engineer\nPython, ML\nexp\nunique\nTech\nSF\ny\n{resume}\n\n\n",
    )


# --- applications ---

def test_applications_add(runner):
    result = runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_applications_list_empty(runner):
    result = runner.invoke(cli, ["applications", "list"])
    assert result.exit_code == 0


def test_applications_add_and_list(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "list"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_applications_advance(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "advance", "1", "--status", "applied"])
    assert result.exit_code == 0
    assert "applied" in result.output.lower()


def test_applications_stats(runner):
    result = runner.invoke(cli, ["applications", "stats"])
    assert result.exit_code == 0


def test_applications_view_not_found(runner):
    result = runner.invoke(cli, ["applications", "view", "999"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


def test_applications_view(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "view", "1"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_applications_delete(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "delete", "1", "--yes"])
    assert result.exit_code == 0


# --- interview ---

def test_interview_view_no_prep(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["interview", "view", "1"])
    assert result.exit_code == 0
    assert "No prep saved" in result.output or result.exit_code == 0


def test_interview_prep_not_found(runner):
    result = runner.invoke(cli, ["interview", "prep", "999"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


def test_interview_prep_and_view(runner, monkeypatch):
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=800: "Q1: Tell me about yourself.",
    )
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    prep_result = runner.invoke(cli, ["interview", "prep", "1"])
    assert prep_result.exit_code == 0
    view_result = runner.invoke(cli, ["interview", "view", "1"])
    assert view_result.exit_code == 0


# --- conversations ---

def test_conversations_log_and_view(runner):
    runner.invoke(
        cli,
        ["contacts", "add"],
        input="Alice\nPM\nBeta\nhttps://linkedin.com/in/alice\n\n",
    )
    result = runner.invoke(cli, ["conversations", "log", "1", "--from", "me", "--text", "Hey Alice!"])
    assert result.exit_code == 0
    view = runner.invoke(cli, ["conversations", "view", "1"])
    assert "Hey Alice" in view.output


def test_conversations_view_empty(runner):
    runner.invoke(
        cli,
        ["contacts", "add"],
        input="Bob\nEng\nCorp\nhttps://linkedin.com/in/bob\n\n",
    )
    result = runner.invoke(cli, ["conversations", "view", "1"])
    assert result.exit_code == 0


# --- calendar ---

def test_calendar_add_and_list(runner):
    runner.invoke(cli, ["calendar", "add", "--title", "Post 1", "--date", "2026-03-01"])
    result = runner.invoke(cli, ["calendar", "list"])
    assert result.exit_code == 0
    assert "Post 1" in result.output


def test_calendar_mark_posted(runner):
    runner.invoke(cli, ["calendar", "add", "--title", "Post 1", "--date", "2026-03-01"])
    result = runner.invoke(cli, ["calendar", "mark-posted", "1"])
    assert result.exit_code == 0


def test_calendar_stats(runner):
    result = runner.invoke(cli, ["calendar", "stats"])
    assert result.exit_code == 0


# --- applications AI commands ---


def test_applications_tailor_resume_no_profile(runner):
    """tailor-resume without a profile (no resume_text) should error."""
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "tailor-resume", "1"])
    assert result.exit_code != 0


def test_applications_tailor_resume_with_ai(runner, monkeypatch):
    """tailor-resume with profile resume_text and mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=800: "• Led ML pipeline optimization",
    )
    _setup_profile_with_resume(runner)
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "tailor-resume", "1"])
    assert result.exit_code == 0
    assert "ML pipeline" in result.output


def test_applications_tailor_resume_file_not_found(runner):
    """tailor-resume with a nonexistent --resume-file should error."""
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(
        cli, ["applications", "tailor-resume", "1", "--resume-file", "/nonexistent/resume.txt"]
    )
    assert result.exit_code != 0


def test_applications_cover_letter_no_profile(runner):
    """cover-letter without a profile should error."""
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "cover-letter", "1"])
    assert result.exit_code != 0


def test_applications_cover_letter_with_ai(runner, monkeypatch):
    """cover-letter with profile and mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=800: "Dear Hiring Manager, I am thrilled to apply.",
    )
    _setup_profile_no_resume(runner)
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "cover-letter", "1"])
    assert result.exit_code == 0
    assert "Hiring Manager" in result.output


def test_applications_skills_gap_no_jd(runner):
    """skills-gap without a job description should error."""
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "skills-gap", "1"])
    assert result.exit_code != 0


def test_applications_skills_gap_with_ai(runner, monkeypatch):
    """skills-gap with JD and mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=600: "## Skills You Have\n- Python",
    )
    runner.invoke(
        cli,
        ["applications", "add", "--company", "Acme", "--title", "ML Engineer", "--jd", "Must know Python and ML"],
    )
    result = runner.invoke(cli, ["applications", "skills-gap", "1"])
    assert result.exit_code == 0


# --- applications validation ---


def test_applications_advance_invalid_status(runner):
    """advance with an invalid status string should error."""
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "advance", "1", "--status", "flying"])
    assert result.exit_code != 0
    assert "invalid" in result.output.lower() or "valid" in result.output.lower()


# --- interview AI commands ---


def test_interview_research_with_ai(runner, monkeypatch):
    """interview research with mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=800: "## Company Overview\nAcme builds ML tools.",
    )
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["interview", "research", "1"])
    assert result.exit_code == 0


def test_interview_star_with_ai(runner, monkeypatch):
    """interview star with mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=1000: "**Question:** Tell me about a challenge\n**Situation:** [FILL IN]",
    )
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["interview", "star", "1"])
    assert result.exit_code == 0


def test_interview_questions_with_ai(runner, monkeypatch):
    """interview questions with mocked AI should succeed."""
    monkeypatch.setattr(
        "linkedin.ai.client.generate_with_ai",
        lambda prompt, max_tokens=400: "1. What does success look like in 90 days?",
    )
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["interview", "questions", "1"])
    assert result.exit_code == 0


# --- conversations export ---


def test_conversations_export(runner):
    """conversations export should print logged messages as plain text."""
    runner.invoke(
        cli,
        ["contacts", "add"],
        input="Alice\nPM\nBeta\nhttps://linkedin.com/in/alice\n\n",
    )
    runner.invoke(cli, ["conversations", "log", "1", "--from", "me", "--text", "Hey Alice!"])
    result = runner.invoke(cli, ["conversations", "export", "1"])
    assert result.exit_code == 0
    assert "Hey Alice" in result.output


# --- calendar validation ---


def test_calendar_mark_posted_not_found(runner):
    """mark-posted with a nonexistent post ID should error."""
    result = runner.invoke(cli, ["calendar", "mark-posted", "999"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_calendar_list_week_filter(runner):
    """calendar list --week should not show posts scheduled beyond 7 days."""
    runner.invoke(cli, ["calendar", "add", "--title", "Far Future Post", "--date", "2026-04-30"])
    result = runner.invoke(cli, ["calendar", "list", "--week"])
    assert "Far Future Post" not in result.output
