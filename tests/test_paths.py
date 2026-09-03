"""DataDir: the one root, resolved once."""

from pathlib import Path

from linkedin.data.json_store import save_json
from linkedin.data.paths import DEFAULT_ROOT, DataDir


def test_from_env_honours_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path / "custom"))
    assert DataDir.from_env().root == tmp_path / "custom"


def test_from_env_default(monkeypatch):
    monkeypatch.delenv("LINKEDIN_DATA_DIR", raising=False)
    assert DataDir.from_env().root == DEFAULT_ROOT == Path.home() / ".linkedin-cli"


def test_backup_members_enumerate_the_directory(tmp_path):
    d = DataDir(tmp_path)
    save_json(d.contacts, [])
    save_json(d.job_postings, [])
    d.run_daily_log.write_text("{}\n")
    d.li_session.write_text("{}")
    d.run_daily_lock.write_text("{}")
    (tmp_path / ".contacts.json.tmp").write_text("")
    d.backups.mkdir()
    names = {p.name for p in d.backup_members()}
    assert names == {"contacts.json", "job_postings.json", "run_daily.log.jsonl"}


def test_cli_import_does_not_touch_disk(monkeypatch, tmp_path):
    """The App is built on first use, not at import: importing the CLI under
    a data dir that does not exist must neither fail nor create it."""
    import importlib

    import linkedin.cli as cli_mod

    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path / "never-created"))
    importlib.reload(cli_mod)
    assert not (tmp_path / "never-created").exists()
