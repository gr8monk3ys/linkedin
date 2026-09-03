"""Market intelligence service — salary estimates, trends, skill demand."""

import csv
import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import linkedin.data.json_store as json_store
from linkedin.ai.client import ai_call
from linkedin.data.repository import ProfileRepo


class MarketService:
    def __init__(self, profile_repo: ProfileRepo):
        self.profiles = profile_repo
        self._postings: list[dict] = self._load_postings()
        self._insights: list[dict] = []

    def analyze_market(self, role: str = "", industry: str = "") -> tuple[str | None, str]:
        """Get AI market analysis for a role/industry."""
        profile = self.profiles.get()
        target_role = role or profile.get("target_role", "")
        target_industry = industry or profile.get("industries", "")

        if not target_role:
            return "Set a target role in your profile or provide one.", ""

        prompt = f"""Provide a concise job market analysis for the following:

ROLE: {target_role}
INDUSTRY: {target_industry or 'General'}

Include:
1. Current demand level (high/medium/low) and trend
2. Typical salary range (US market)
3. Top 5 most-requested skills for this role
4. Key industry trends affecting this role
5. Hiring outlook for the next 6 months
6. Tips for standing out as a candidate

        Keep it actionable and under 400 words."""

        result = ai_call(prompt, max_tokens=600)
        return result.error, result.text

    def estimate_salary(self, role: str = "", location: str = "") -> tuple[str | None, str]:
        """Get AI salary estimate."""
        profile = self.profiles.get()
        target_role = role or profile.get("target_role", "")
        loc = location or profile.get("location", "US")

        if not target_role:
            return "Set a target role in your profile or provide one.", ""

        prompt = f"""Estimate the salary range for:

ROLE: {target_role}
LOCATION: {loc}
EXPERIENCE LEVEL: Mid-Senior

Provide:
1. Base salary range (low - median - high)
2. Total compensation range (including bonus/equity)
3. Factors that increase pay (certifications, skills, company size)
4. How remote vs on-site affects compensation
5. Negotiation tips for this role

        Be specific with numbers. Keep under 300 words."""

        result = ai_call(prompt, max_tokens=500)
        return result.error, result.text

    def analyze_trends(self, industry: str = "") -> tuple[str | None, str]:
        """Get AI hiring trend analysis."""
        profile = self.profiles.get()
        target_industry = industry or profile.get("industries", "")

        if not target_industry:
            return "Set target industries in your profile or provide one.", ""

        prompt = f"""Analyze current hiring trends for:

INDUSTRY: {target_industry}

Include:
1. Which roles are in highest demand
2. Emerging roles and skills
3. Industries/sectors with most growth
4. Impact of AI/automation on hiring
5. Remote work trends in this industry
6. Best job search strategies for this industry

        Keep it actionable and under 350 words."""

        result = ai_call(prompt, max_tokens=500)
        return result.error, result.text

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
            "skills_required": self._normalize_skills(
                raw.get("skills_required") or raw.get("skills") or ""
            ),
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

    def _load_postings(self) -> list[dict]:
        raw = json_store.load_json(json_store.JOB_POSTINGS_FILE, [])
        return raw if isinstance(raw, list) else []

    def _refresh_postings(self) -> None:
        self._postings = self._load_postings()

    def _save_postings(self) -> None:
        json_store.save_json(json_store.JOB_POSTINGS_FILE, self._postings)
