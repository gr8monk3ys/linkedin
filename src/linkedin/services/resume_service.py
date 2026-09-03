"""Bridge to the resume repository (github.com/gr8monk3ys/resume).

The resume repo is the source of truth for resume artifacts: LaTeX variants
under ``variants/<slug>/`` (plus ``default/``), built PDFs under ``output/``
as ``<slug>-resume.pdf`` / ``<slug>-cover_letter.pdf``, and an ``autoapply``
pipeline whose state lives in ``output/autoapply/state.db`` (SQLite).

This service reads that checkout directly — no imports from the resume repo —
so the two projects stay independently deployable. Point it at the checkout
with the ``LINKEDIN_RESUME_REPO`` env var or an explicit ``repo_root``.
"""

from __future__ import annotations

import html
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

RESUME_REPO_ENV = "LINKEDIN_RESUME_REPO"

_SKILLROW_RE = re.compile(r"\\skillrow\{[^}]*\}\{([^}]*)\}")
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#./-]*")

# autoapply pipeline status -> local application status
AUTOAPPLY_STATUS_MAP = {
    "submitted": "applied",
    "screening": "phone_screen",
    "interview": "technical",
    "offer": "offer_received",
    "rejected": "rejected",
}


class ResumeRepoError(RuntimeError):
    """Raised when the resume repo checkout is missing or malformed."""


def resolve_repo_root(repo_root: str = "") -> Path:
    """Resolve and validate the resume repo checkout path."""
    raw = repo_root or os.environ.get(RESUME_REPO_ENV, "")
    if not raw:
        raise ResumeRepoError(
            f"Resume repo path not set. Pass --resume-repo or set {RESUME_REPO_ENV} "
            "to your local checkout of the resume repository."
        )
    root = Path(raw).expanduser()
    if not root.is_dir():
        raise ResumeRepoError(f"Resume repo path does not exist: {root}")
    if not (root / "variants").is_dir() and not (root / "default").is_dir():
        raise ResumeRepoError(f"{root} does not look like the resume repo (no variants/ or default/ directory)")
    return root


def list_variants(repo_root: str = "") -> list[str]:
    """Variant slugs available in the checkout, e.g. ['default', 'ai-engineer', ...]."""
    root = resolve_repo_root(repo_root)
    variants = []
    if (root / "default").is_dir():
        variants.append("default")
    variants_dir = root / "variants"
    if variants_dir.is_dir():
        variants.extend(sorted(d.name for d in variants_dir.iterdir() if d.is_dir()))
    return variants


def variant_skills(repo_root: str = "") -> dict[str, list[str]]:
    """``{variant_slug: [skill, ...]}`` parsed from each variant's skills.tex."""
    root = resolve_repo_root(repo_root)
    result: dict[str, list[str]] = {}
    for slug in list_variants(repo_root or str(root)):
        directory = root / ("default" if slug == "default" else f"variants/{slug}")
        skills_file = directory / "sections" / "skills.tex"
        if not skills_file.exists():
            continue
        skills: list[str] = []
        for match in _SKILLROW_RE.finditer(skills_file.read_text(encoding="utf-8")):
            for item in match.group(1).split(","):
                cleaned = item.replace("\\&", "&").strip()
                # Drop parenthetical qualifiers: "GCP (Vertex AI, BigQuery)" -> "GCP"
                cleaned = re.sub(r"\s*\([^)]*\)?", "", cleaned).strip()
                if cleaned:
                    skills.append(cleaned)
        result[slug] = skills
    return result


def match_variants(jd_text: str, repo_root: str = "", title: str = "") -> list[dict]:
    """Rank resume variants against a job description.

    Scores each variant by (a) skill overlap between its skills.tex and the
    JD text and (b) variant-slug words appearing in the job title. Returns
    a list of {variant, score, matched_skills} sorted best-first.
    """
    haystack = f" {jd_text.lower()} "
    title_lower = title.lower()
    ranked = []
    for slug, skills in variant_skills(repo_root).items():
        matched = []
        for skill in skills:
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(skill.lower()) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, haystack):
                matched.append(skill)
        score = len(matched) * 10
        if slug != "default":
            slug_words = [w for w in slug.split("-") if w not in ("full",)]
            if slug_words and all(w in title_lower for w in slug_words):
                score += 50
        ranked.append({"variant": slug, "score": score, "matched_skills": matched})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


def resolve_pdf(variant: str, kind: str = "resume", repo_root: str = "") -> Path | None:
    """Path to the built PDF for a variant (``output/<slug>-<kind>.pdf``), or None."""
    root = resolve_repo_root(repo_root)
    pdf = root / "output" / f"{variant}-{kind}.pdf"
    return pdf if pdf.exists() else None


def import_autoapply_applications(repo_root: str = "", include_queued: bool = False) -> list[dict]:
    """Read the autoapply pipeline's SQLite state into application dicts.

    Only rows in a real application state are returned unless
    ``include_queued`` is set (which adds queued jobs as status 'saved').
    Each dict carries company/title/url/status plus resume metadata.
    """
    root = resolve_repo_root(repo_root)
    db_path = root / "output" / "autoapply" / "state.db"
    if not db_path.exists():
        raise ResumeRepoError(f"No autoapply state found at {db_path} (run `./apply scan` in the resume repo first)")

    statuses = set(AUTOAPPLY_STATUS_MAP)
    if include_queued:
        statuses.add("queued")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # `discovered_at` was added to the pipeline's schema later; an older
    # checkout does not have it, and the fallback is optional, not required.
    has_discovered = any(
        row[1] == "discovered_at" for row in conn.execute("PRAGMA table_info(jobs)")
    )

    discovered = "j.discovered_at" if has_discovered else "NULL AS discovered_at"
    placeholders = ",".join("?" * len(statuses))
    query = (
        "SELECT j.company, j.title, j.url, j.description, j.status, j.variant, "
        f"{discovered}, a.resume_path, a.cover_path, a.submitted_at "
        "FROM jobs j "
        "LEFT JOIN applications a ON a.job_id = j.id "
        f"WHERE j.status IN ({placeholders}) "
        "ORDER BY j.id"
    )

    try:
        rows = conn.execute(query, sorted(statuses)).fetchall()
    finally:
        conn.close()

    imported = []
    for row in rows:
        status = AUTOAPPLY_STATUS_MAP.get(row["status"], "saved")
        imported.append(
            {
                # The pipeline scrapes job pages, so text arrives HTML-encoded.
                # "LA28 Olympic &amp; Paralympic Games" is a real row, and an
                # undecoded company name would be carried straight into a cover
                # letter addressed to them.
                "company": _decode(row["company"]),
                "title": _decode(row["title"]),
                "url": row["url"] or "",
                "jd_text": _decode(row["description"])[:5000],
                "status": status,
                # `submitted_at` is null for most rows while `discovered_at`
                # never is. Without the fallback everything imports as "applied
                # today", so the planner times the import instead of the
                # application and a weeks-old application waits ten more days.
                "applied_date": row["submitted_at"] or row["discovered_at"],
                "applied_date_is_approximate": not row["submitted_at"],
                "resume_variant": row["variant"] or "",
                "resume_path": row["resume_path"] or "",
                "cover_letter_path": row["cover_path"] or "",
                "source": "autoapply",
            }
        )
    return imported


def _decode(value) -> str:
    """Unescape scraped HTML text (`&amp;` -> `&`)."""
    return html.unescape(value or "").strip()


def merge_into_applications(entries: list[dict], application_repo) -> tuple[list[dict], int]:
    """Add imported entries to the application repo, skipping duplicates.

    Dedupes on job URL when present, else on (company, title). Returns
    (added_applications, skipped_count).
    """
    existing = application_repo.list_all()
    seen_urls = {a.get("url", "").strip() for a in existing if a.get("url")}
    seen_roles = {(a.get("company", "").lower(), a.get("title", "").lower()) for a in existing}

    added, skipped = [], 0
    for entry in entries:
        url = entry.get("url", "").strip()
        role_key = (entry.get("company", "").lower(), entry.get("title", "").lower())
        if (url and url in seen_urls) or role_key in seen_roles:
            skipped += 1
            continue
        app = dict(entry)
        app["id"] = application_repo.next_id()
        app.setdefault("created_at", datetime.now().isoformat())
        app.setdefault("notes", "")
        app.setdefault("contact_id", None)
        history = []
        if app["status"] != "saved":
            history.append(
                {
                    "status": app["status"],
                    "date": app.get("applied_date") or datetime.now().isoformat(),
                    "notes": "Imported from autoapply",
                }
            )
        app["history"] = history
        application_repo.add(app)
        seen_urls.add(url)
        seen_roles.add(role_key)
        added.append(app)
    return added, skipped
