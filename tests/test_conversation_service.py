"""Tests for ConversationService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import JsonConversationRepo, JsonContactRepo, JsonCompanyRepo
from linkedin.services.conversation_service import ConversationService
from tests.conftest import sample_contact


@pytest.fixture
def conv_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    contact_repo = JsonContactRepo()
    contact_repo.add({**sample_contact(), "id": 1})
    return JsonConversationRepo(), contact_repo


@pytest.fixture
def svc(conv_repos):
    conv_repo, contact_repo = conv_repos
    return ConversationService(conv_repo, contact_repo)


def test_log_first_message(svc):
    svc.log(1, sender="me", text="Hi there!")
    thread = svc.get_thread(1)
    assert thread is not None
    assert len(thread["messages"]) == 1
    assert thread["messages"][0]["text"] == "Hi there!"
    assert thread["messages"][0]["sender"] == "me"


def test_log_multiple_messages_ordered(svc):
    svc.log(1, sender="me", text="First message")
    svc.log(1, sender="them", text="Their reply")
    svc.log(1, sender="me", text="My follow-up")
    thread = svc.get_thread(1)
    assert len(thread["messages"]) == 3
    assert thread["messages"][0]["text"] == "First message"
    assert thread["messages"][1]["sender"] == "them"
    assert thread["messages"][2]["text"] == "My follow-up"


def test_log_invalid_sender(svc):
    with pytest.raises(ValueError, match="sender"):
        svc.log(1, sender="robot", text="Hello")


def test_get_thread_none_when_empty(svc):
    thread = svc.get_thread(1)
    assert thread is None


def test_export_plain_text(svc):
    svc.log(1, sender="me", text="Hey!")
    svc.log(1, sender="them", text="Hello back")
    export = svc.export(1)
    assert "Hey!" in export
    assert "Hello back" in export
    assert "[Me]" in export or "[Them]" in export


def test_contact_not_found(svc):
    with pytest.raises(ValueError, match="not found"):
        svc.log(999, sender="me", text="Hello")
