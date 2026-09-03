"""Tests for JSON repository behavior."""

from unittest.mock import patch

import pytest


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


class TestAtomicSaveJson:
    """A partial write must never replace a good file with a truncated one."""

    def test_interrupted_write_leaves_original_intact(self, tmp_path):
        import json as _json

        from linkedin.data import json_store

        target = tmp_path / "contacts.json"
        json_store.save_json(target, [{"id": 1, "name": "Alice"}])

        def boom(*_args, **_kwargs):
            raise KeyboardInterrupt

        with patch("linkedin.data.json_store.json.dumps", side_effect=boom):
            with pytest.raises(KeyboardInterrupt):
                json_store.save_json(target, [{"id": 2, "name": "Bob"}])

        assert _json.loads(target.read_text()) == [{"id": 1, "name": "Alice"}]

    def test_failed_write_leaves_no_temp_files(self, tmp_path):
        from linkedin.data import json_store

        target = tmp_path / "contacts.json"
        json_store.save_json(target, [{"id": 1}])

        with patch("linkedin.data.json_store.os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                json_store.save_json(target, [{"id": 2}])

        assert [p.name for p in tmp_path.iterdir()] == ["contacts.json"]

    def test_creates_missing_parent_directory(self, tmp_path):
        from linkedin.data import json_store

        target = tmp_path / "nested" / "dir" / "contacts.json"
        json_store.save_json(target, [{"id": 1}])
        assert target.exists()

    def test_round_trips_via_load_json(self, tmp_path):
        from linkedin.data import json_store

        target = tmp_path / "contacts.json"
        rows = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        json_store.save_json(target, rows)
        assert json_store.load_json(target) == rows
