"""The two prerequisites the growth plan names: a key that provably works, and one headline source."""

from unittest.mock import MagicMock, patch

from linkedin.ai.client import probe_api_key
from linkedin.services.profile_service import ProfileService
from linkedin.services.resume_service import linkedin_copy

DOC = """# LinkedIn copy

## Headline (220 chars max)

```
Machine Learning Engineer | Moving into solutions engineering
```

Notes here.

## About

```
Line one.

Line two.
```

## Experience
"""


def _repo(tmp_path):
    (tmp_path / "variants").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "linkedin-copy.md").write_text(DOC)
    return tmp_path


def test_linkedin_copy_reads_the_fenced_blocks(tmp_path):
    copy = linkedin_copy(str(_repo(tmp_path)))
    assert copy["headline"] == "Machine Learning Engineer | Moving into solutions engineering"
    assert copy["about"] == "Line one.\n\nLine two."


def test_linkedin_copy_is_empty_without_the_doc(tmp_path, monkeypatch):
    (tmp_path / "variants").mkdir()
    assert linkedin_copy(str(tmp_path)) == {}
    monkeypatch.setenv("LINKEDIN_RESUME_REPO", str(tmp_path / "nope"))
    assert linkedin_copy() == {}


def test_profile_overlays_the_curated_copy_and_says_so(tmp_path):
    repo = MagicMock()
    repo.get.return_value = {"name": "Me", "headline": "stale March headline", "target_role": "SE"}
    svc = ProfileService(repo, copy_loader=lambda: {"headline": "curated", "about": "About me"})
    profile = svc.get_profile()
    assert profile["headline"] == "curated" and profile["about"] == "About me"
    assert profile["copy_source"] == "resume repo"
    assert repo.get.return_value["headline"] == "stale March headline"  # the file is untouched


def test_profile_without_a_repo_keeps_the_local_copy():
    repo = MagicMock()
    repo.get.return_value = {"name": "Me", "headline": "local"}
    assert ProfileService(repo, copy_loader=lambda: {}).get_profile()["headline"] == "local"


def test_probe_reports_validity_not_presence():
    with patch("anthropic.Anthropic") as client_cls:
        assert probe_api_key("sk-good")[0] is True
        client_cls.return_value.models.list.side_effect = RuntimeError("401 invalid x-api-key")
        ok, detail = probe_api_key("sk-bad")
        assert ok is False and "401" in detail
