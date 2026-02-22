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
    monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")


@pytest.fixture
def runner():
    return CliRunner()


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
