"""Tests for JSON repository helpers."""


def test_contact_next_id_uses_max_existing_id(json_repos):
    contact_repo, *_ = json_repos

    contact_repo.add({"id": 1, "name": "Alice"})
    contact_repo.add({"id": 3, "name": "Bob"})

    assert contact_repo.next_id() == 4


def test_company_next_id_uses_max_existing_id(json_repos):
    _, company_repo, *_ = json_repos

    company_repo.add({"id": 2, "name": "Acme"})
    company_repo.add({"id": 5, "name": "Globex"})

    assert company_repo.next_id() == 6


def test_draft_next_id_uses_max_existing_id(json_repos):
    *_, draft_repo, _ = json_repos

    draft_repo.add({"id": 4, "type": "connection", "content": "Hi"})
    draft_repo.add({"id": 7, "type": "message", "content": "Hello"})

    assert draft_repo.next_id() == 8
