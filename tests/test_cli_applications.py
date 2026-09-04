"""CLI integration tests for applications, interview, conversations, and calendar commands."""

import pytest
from click.testing import CliRunner

from linkedin.cli import cli


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


def test_interview_prep_not_found(runner):
    result = runner.invoke(cli, ["interview", "prep", "999"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


# --- conversations ---


# --- calendar ---


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
    result = runner.invoke(cli, ["applications", "tailor-resume", "1", "--resume-file", "/nonexistent/resume.txt"])
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


# --- conversations export ---


# --- calendar validation ---


def test_calendar_list_week_filter(runner):
    """calendar list --week should not show posts scheduled beyond 7 days."""
    runner.invoke(cli, ["calendar", "add", "--title", "Far Future Post", "--date", "2026-04-30"])
    result = runner.invoke(cli, ["calendar", "list", "--week"])
    assert "Far Future Post" not in result.output
