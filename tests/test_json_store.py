"""Tests for JSON repository behavior."""


class TestJsonStoreIds:
    def test_contact_next_id_uses_max_after_delete(self, json_repos):
        contact_repo = json_repos[0]
        contact_repo.add({"id": 1, "name": "First"})
        contact_repo.add({"id": 2, "name": "Second"})

        assert contact_repo.delete(1) is True
        assert contact_repo.next_id() == 3

    def test_contact_next_id_handles_numeric_string_ids(self, json_repos):
        contact_repo = json_repos[0]
        contact_repo.add({"id": "7", "name": "String ID"})

        assert contact_repo.next_id() == 8
