"""Tests for the resume repo bridge service."""

import sqlite3

import pytest

import linkedin.data.json_store as js
from linkedin.data.json_store import JsonApplicationRepo
from linkedin.services.resume_service import (
    ResumeRepoError,
    import_autoapply_applications,
    list_variants,
    match_variants,
    merge_into_applications,
    resolve_pdf,
    resolve_repo_root,
    variant_skills,
)


@pytest.fixture
def resume_repo(tmp_path):
    """A minimal fake resume repo checkout."""
    root = tmp_path / "resume"
    (root / "default" / "sections").mkdir(parents=True)
    (root / "default" / "sections" / "skills.tex").write_text(
        "\\skillrow{Languages}{Python, SQL (PostgreSQL), TypeScript}\n\\skillrow{Tools}{Docker, Git}\n"
    )
    (root / "variants" / "ai-engineer" / "sections").mkdir(parents=True)
    (root / "variants" / "ai-engineer" / "sections" / "skills.tex").write_text(
        "\\skillrow{LLM/GenAI}{RAG, LangChain, PyTorch}\n\\skillrow{ML}{scikit-learn, Weights \\& Biases}\n"
    )
    (root / "variants" / "backend-engineer" / "sections").mkdir(parents=True)
    (root / "variants" / "backend-engineer" / "sections" / "skills.tex").write_text(
        "\\skillrow{Backend}{FastAPI, PostgreSQL, Kubernetes}\n"
    )
    output = root / "output"
    output.mkdir()
    (output / "ai-engineer-resume.pdf").write_bytes(b"%PDF-fake")
    (output / "ai-engineer-cover_letter.pdf").write_bytes(b"%PDF-fake")
    return root


@pytest.fixture
def application_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    return JsonApplicationRepo()


def _seed_autoapply_db(root, rows):
    db_dir = root / "output" / "autoapply"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_dir / "state.db")
    conn.executescript(
        """
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY, company TEXT, title TEXT, url TEXT,
            description TEXT, status TEXT, variant TEXT
        );
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY, job_id INTEGER, status TEXT,
            resume_path TEXT, cover_path TEXT, submitted_at TEXT
        );
        """
    )
    for row in rows:
        cur = conn.execute(
            "INSERT INTO jobs (company, title, url, description, status, variant) VALUES (?, ?, ?, ?, ?, ?)",
            row[:6],
        )
        if len(row) > 6:
            conn.execute(
                "INSERT INTO applications (job_id, status, resume_path, submitted_at) VALUES (?, ?, ?, ?)",
                (cur.lastrowid, row[4], row[6], row[7]),
            )
    conn.commit()
    conn.close()


def test_resolve_repo_root_missing_env(monkeypatch):
    monkeypatch.delenv("LINKEDIN_RESUME_REPO", raising=False)
    with pytest.raises(ResumeRepoError, match="not set"):
        resolve_repo_root()


def test_resolve_repo_root_bad_path():
    with pytest.raises(ResumeRepoError, match="does not exist"):
        resolve_repo_root("/nonexistent/path")


def test_resolve_repo_root_not_a_resume_repo(tmp_path):
    with pytest.raises(ResumeRepoError, match="does not look like"):
        resolve_repo_root(str(tmp_path))


def test_resolve_repo_root_env(resume_repo, monkeypatch):
    monkeypatch.setenv("LINKEDIN_RESUME_REPO", str(resume_repo))
    assert resolve_repo_root() == resume_repo


def test_list_variants(resume_repo):
    assert list_variants(str(resume_repo)) == ["default", "ai-engineer", "backend-engineer"]


def test_variant_skills_parses_skillrows(resume_repo):
    skills = variant_skills(str(resume_repo))
    assert "RAG" in skills["ai-engineer"]
    assert "Weights & Biases" in skills["ai-engineer"]
    # Parenthetical qualifiers dropped
    assert "SQL" in skills["default"]


def test_match_variants_ranks_by_skill_overlap(resume_repo):
    jd = "We need someone with RAG, LangChain, and PyTorch experience for LLM apps."
    ranked = match_variants(jd, repo_root=str(resume_repo))
    assert ranked[0]["variant"] == "ai-engineer"
    assert ranked[0]["score"] >= 30
    assert "RAG" in ranked[0]["matched_skills"]


def test_match_variants_title_boost(resume_repo):
    ranked = match_variants("", repo_root=str(resume_repo), title="Senior Backend Engineer")
    assert ranked[0]["variant"] == "backend-engineer"


def test_match_variants_no_substring_false_positives(resume_repo):
    # 'Git' must not match inside 'digital'
    ranked = match_variants("digital marketing role", repo_root=str(resume_repo))
    default = next(r for r in ranked if r["variant"] == "default")
    assert "Git" not in default["matched_skills"]


def test_resolve_pdf(resume_repo):
    pdf = resolve_pdf("ai-engineer", "resume", repo_root=str(resume_repo))
    assert pdf is not None and pdf.name == "ai-engineer-resume.pdf"
    assert resolve_pdf("backend-engineer", "resume", repo_root=str(resume_repo)) is None


def test_import_autoapply_missing_db(resume_repo):
    with pytest.raises(ResumeRepoError, match="No autoapply state"):
        import_autoapply_applications(str(resume_repo))


def test_import_autoapply_maps_statuses(resume_repo):
    _seed_autoapply_db(
        resume_repo,
        [
            ("Acme", "ML Engineer", "https://x/1", "desc", "submitted", "ai-engineer", "/r.pdf", "2026-08-01"),
            ("Beta", "Backend Dev", "https://x/2", "desc", "interview", "backend-engineer", "/r2.pdf", "2026-08-02"),
            ("Gamma", "PM", "https://x/3", "desc", "queued", "", None, None),
            ("Delta", "Skipped Role", "https://x/4", "desc", "skipped", "", None, None),
        ],
    )
    entries = import_autoapply_applications(str(resume_repo))
    statuses = {e["company"]: e["status"] for e in entries}
    assert statuses == {"Acme": "applied", "Beta": "technical"}
    assert entries[0]["resume_variant"] == "ai-engineer"
    assert entries[0]["source"] == "autoapply"

    with_queued = import_autoapply_applications(str(resume_repo), include_queued=True)
    assert {e["company"] for e in with_queued} == {"Acme", "Beta", "Gamma"}
    assert next(e for e in with_queued if e["company"] == "Gamma")["status"] == "saved"


def test_merge_into_applications_dedupes(application_repo):
    application_repo.add(
        {"id": 1, "company": "Acme", "title": "ML Engineer", "url": "https://x/1", "status": "applied"}
    )
    entries = [
        {"company": "Acme", "title": "ML Engineer", "url": "https://x/1", "status": "applied"},
        {"company": "New Co", "title": "Data Engineer", "url": "https://x/9", "status": "applied"},
        {"company": "No URL Co", "title": "Engineer", "url": "", "status": "applied"},
    ]
    added, skipped = merge_into_applications(entries, application_repo)
    assert skipped == 1
    assert [a["company"] for a in added] == ["New Co", "No URL Co"]
    assert all(a["history"] for a in added)
    assert len(application_repo.list_all()) == 3
