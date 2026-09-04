"""Market intelligence service — salary estimates, trends, skill demand."""

import csv
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from linkedin.data.json_store import JsonProfileRepo, load_json, save_json


class PostingService:
    """Job postings: import, dedupe, and score against the profile."""

    def __init__(self, profile_repo: JsonProfileRepo, postings_file: Path):
        self.profiles = profile_repo
        self.postings_file = postings_file
        self._postings: list[dict] = self._load_postings()
        self._insights: list[dict] = []

    def add_posting(self, posting: dict) -> dict:
        """Add a manually tracked job posting."""
        self._refresh_postings()
        normalized = self._normalize_posting(posting)
        normalized["id"] = self._next_posting_id()
        normalized["created_at"] = datetime.now().isoformat()
        self._postings.append(normalized)
        self._save_postings()
        return normalized

    def import_postings(self, file_path: str, merge: bool = False) -> tuple[int, int]:
        """Import postings from CSV/JSON. Returns (imported_count, skipped_count)."""
        path = Path(file_path)
        raw_postings = self._read_postings_file(path)

        self._refresh_postings()
        if merge:
            final = list(self._postings)
        else:
            final = []

        existing_keys = {self._posting_key(p) for p in final}
        next_id = self._next_posting_id(final)
        imported = 0
        skipped = 0

        for raw in raw_postings:
            posting = self._normalize_posting(raw)
            if not posting["title"] or not posting["company"]:
                skipped += 1
                continue

            key = self._posting_key(posting)
            if merge and key in existing_keys:
                skipped += 1
                continue

            posting["id"] = next_id
            next_id += 1
            posting["created_at"] = posting.get("created_at") or datetime.now().isoformat()
            final.append(posting)
            existing_keys.add(key)
            imported += 1

        self._postings = final
        self._save_postings()
        return imported, skipped

    def list_postings(self, limit: int = 20, min_score: int = 0) -> list[dict]:
        """List tracked postings ranked by profile match score."""
        self._refresh_postings()
        profile = self.profiles.get()
        scored = []
        for posting in self._postings:
            score, reasons = self._score_posting(posting, profile)
            if score < min_score:
                continue

            entry = dict(posting)
            entry["match_score"] = score
            entry["match_reasons"] = reasons
            scored.append(entry)

        scored.sort(
            key=lambda p: (p.get("match_score", 0), p.get("created_at", "")),
            reverse=True,
        )
        return scored[:limit]

    def _normalize_posting(self, raw: dict) -> dict:
        """Normalize posting shape and scalar types."""
        return {
            "title": str(raw.get("title", "")).strip(),
            "company": str(raw.get("company", "")).strip(),
            "location": str(raw.get("location", "")).strip(),
            "salary_min": self._to_int(raw.get("salary_min")),
            "salary_max": self._to_int(raw.get("salary_max")),
            "skills_required": self._normalize_skills(raw.get("skills_required") or raw.get("skills") or ""),
            "url": str(raw.get("url", "")).strip(),
            "source": str(raw.get("source", "manual")).strip() or "manual",
            "posted_date": str(raw.get("posted_date", "")).strip(),
            "notes": str(raw.get("notes", "")).strip(),
            "created_at": str(raw.get("created_at", "")).strip(),
        }

    def _score_posting(self, posting: dict, profile: dict) -> tuple[int, list[str]]:
        """Compute a 0-100 profile-match score for a posting."""
        if not profile:
            return 0, ["Set up your profile to enable matching."]

        score = 0.0
        reasons: list[str] = []

        target_role = str(profile.get("target_role", "")).strip().lower()
        title = str(posting.get("title", "")).strip().lower()
        if target_role and title:
            ratio = SequenceMatcher(None, target_role, title).ratio()
            if target_role in title or title in target_role:
                score += 35
                reasons.append("Role title alignment")
            elif ratio >= 0.75:
                score += 25
                reasons.append("Strong role similarity")
            elif ratio >= 0.60:
                score += 15
                reasons.append("Partial role similarity")

        profile_skills = self._token_set(profile.get("skills", ""))
        posting_skills = self._token_set(posting.get("skills_required", ""))
        if posting_skills and profile_skills:
            overlap = profile_skills.intersection(posting_skills)
            if overlap:
                skill_score = min(40.0, 40.0 * len(overlap) / max(1, len(posting_skills)))
                score += skill_score
                reasons.append(f"Skill overlap: {', '.join(sorted(overlap)[:4])}")

        profile_location = self._token_set(profile.get("location", ""))
        posting_location = self._token_set(posting.get("location", ""))
        if profile_location and posting_location and profile_location.intersection(posting_location):
            score += 15
            reasons.append("Location overlap")

        industry_tokens = self._token_set(profile.get("industries", ""))
        posting_tokens = self._token_set(f"{posting.get('title', '')} {posting.get('company', '')}")
        if industry_tokens and posting_tokens and industry_tokens.intersection(posting_tokens):
            score += 10
            reasons.append("Industry relevance")

        if "remote" in posting_location:
            score += 5
            reasons.append("Remote-friendly role")

        capped = min(100, int(round(score)))
        if not reasons:
            reasons.append("No strong profile-match signals detected yet.")
        return capped, reasons

    def _read_postings_file(self, path: Path) -> list[dict]:
        if path.suffix.lower() == ".csv":
            with path.open(newline="") as fh:
                reader = csv.DictReader(fh)
                return list(reader)

        if path.suffix.lower() == ".json":
            raw = json.loads(path.read_text())
            if isinstance(raw, list):
                return raw
            raise ValueError("JSON file must contain a list of postings.")

        raise ValueError("Unsupported file format. Use .csv or .json.")

    def _posting_key(self, posting: dict) -> tuple[str, str, str]:
        return (
            str(posting.get("title", "")).strip().lower(),
            str(posting.get("company", "")).strip().lower(),
            str(posting.get("location", "")).strip().lower(),
        )

    def _normalize_skills(self, raw: str) -> str:
        skills = [s.strip() for s in str(raw).split(",") if s.strip()]
        return ", ".join(skills)

    def _token_set(self, raw: str) -> set[str]:
        return {t for t in re.split(r"[^a-z0-9]+", str(raw).lower()) if t and len(t) > 1}

    def _to_int(self, value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(str(value).replace(",", "").strip())
        except ValueError:
            return None

    def _next_posting_id(self, postings: list[dict] | None = None) -> int:
        data = postings if postings is not None else self._postings
        max_id = 0
        for posting in data:
            raw_id = posting.get("id")
            if isinstance(raw_id, int):
                max_id = max(max_id, raw_id)
            elif isinstance(raw_id, str) and raw_id.isdigit():
                max_id = max(max_id, int(raw_id))
        return max_id + 1

    def import_job_results(self, results: list[dict]) -> tuple[list[dict], int]:
        """Persist job-search rows as scored postings. Returns (added, skipped_count).

        Deduped on URL, falling back to (company, title) for rows LinkedIn
        rendered without a link — a job search re-run daily otherwise stacks
        the same posting over and over and drowns the plan's opportunity section.
        """
        existing = self.list_postings(limit=10_000)
        seen_urls = {p.get("url", "").split("?")[0] for p in existing if p.get("url")}
        seen_roles = {(p.get("company", "").lower(), p.get("title", "").lower()) for p in existing}

        added: list[dict] = []
        skipped = 0
        for result in results:
            title = (result.get("title") or "").strip()
            company = (result.get("company") or "").strip()
            if not title:
                skipped += 1
                continue
            url = (result.get("url") or "").split("?")[0]
            role_key = (company.lower(), title.lower())
            if (url and url in seen_urls) or (not url and role_key in seen_roles):
                skipped += 1
                continue
            posting = self.add_posting(
                {
                    "title": title,
                    "company": company,
                    "location": result.get("location", ""),
                    "url": url,
                    "source": "linkedin_jobs",
                    "posted_date": result.get("posted", ""),
                    "notes": "Easy Apply" if result.get("easy_apply") else "",
                }
            )
            added.append(posting)
            if url:
                seen_urls.add(url)
            seen_roles.add(role_key)
        return added, skipped

    def _load_postings(self) -> list[dict]:
        raw = load_json(self.postings_file, [])
        return raw if isinstance(raw, list) else []

    def _refresh_postings(self) -> None:
        self._postings = self._load_postings()

    def _save_postings(self) -> None:
        save_json(self.postings_file, self._postings)
