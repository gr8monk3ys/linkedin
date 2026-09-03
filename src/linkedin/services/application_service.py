"""Job application lifecycle service."""

from datetime import datetime

from linkedin.ai.client import AIClientError, generate_with_ai
from linkedin.data.repository import ApplicationRepo, ContactRepo, ProfileRepo
from linkedin.services.contact_service import parse_iso_date
from linkedin.types import ApplicationDict, ApplicationEventDict

APPLICATION_STATUSES = [
    "saved",
    "applied",
    "phone_screen",
    "technical",
    "onsite",
    "offer_received",
    "accepted",
    "rejected",
    "ghosted",
]

# Statuses that end the lifecycle; they generate no actions.
TERMINAL_APPLICATION_STATUSES = frozenset({"accepted", "rejected", "ghosted"})

# What the planner knows about an application status: how long to leave it
# alone, and what to do once that wait has elapsed. Built the way
# `contact_service.STATUS_RULES` is, and checked against `APPLICATION_STATUSES`
# for the same reason — a status with no rule is invisible to the planner
# forever, which is the hole that made twenty applications unplannable.
APPLICATION_STATUS_RULES: dict[str, dict] = {
    "saved": {
        "after_days": 0,
        "priority": 60,
        "action": "apply_to_saved",
        "reason": "Saved {age} day(s) ago and never applied",
    },
    "applied": {
        "after_days": 10,
        "priority": 70,
        "action": "chase_application",
        "reason": "Applied {age} day(s) ago with no response; follow up or mark ghosted",
    },
    "phone_screen": {
        "after_days": 5,
        "priority": 85,
        "action": "chase_interview",
        "reason": "Phone screen {age} day(s) ago with no next step",
    },
    "technical": {
        "after_days": 5,
        "priority": 88,
        "action": "chase_interview",
        "reason": "Technical round {age} day(s) ago with no next step",
    },
    "onsite": {
        "after_days": 5,
        "priority": 90,
        "action": "chase_interview",
        "reason": "Onsite {age} day(s) ago with no decision",
    },
    "offer_received": {
        "after_days": 2,
        "priority": 95,
        "action": "respond_to_offer",
        "reason": "Offer received {age} day(s) ago; respond",
    },
}


def _check_application_status_coverage() -> None:
    """Fail loudly if an application status is neither terminal nor planned for."""
    covered = set(APPLICATION_STATUS_RULES) | set(TERMINAL_APPLICATION_STATUSES)
    declared = set(APPLICATION_STATUSES)
    if covered != declared:
        raise RuntimeError(
            "Application status tables disagree with APPLICATION_STATUSES — a status "
            f"with no rule is invisible to the planner. Missing a rule: {sorted(declared - covered)}; "
            f"rule for an unknown status: {sorted(covered - declared)}"
        )


_check_application_status_coverage()


class ApplicationService:
    def __init__(
        self,
        application_repo: ApplicationRepo,
        profile_repo: ProfileRepo,
        contact_repo: ContactRepo,
    ):
        self.applications = application_repo
        self.profiles = profile_repo
        self.contacts = contact_repo

    def add_application(
        self,
        company: str,
        title: str,
        url: str = "",
        jd_text: str = "",
        notes: str = "",
        contact_id: int | None = None,
    ) -> ApplicationDict:
        app_id = self.applications.next_id()
        app: ApplicationDict = {
            "id": app_id,
            "company": company,
            "title": title,
            "url": url,
            "jd_text": jd_text,
            "status": "saved",
            "applied_date": None,
            "contact_id": contact_id,
            "notes": notes,
            "created_at": datetime.now().isoformat(),
            "history": [],
        }
        return self.applications.add(app)

    def get_application(self, application_id: int) -> ApplicationDict | None:
        return self.applications.get(application_id)

    def list_applications(
        self, status: str = "all", company: str = ""
    ) -> list[ApplicationDict]:
        apps = self.applications.list_all()
        if status != "all":
            apps = [a for a in apps if a.get("status") == status]
        if company:
            apps = [a for a in apps if company.lower() in a.get("company", "").lower()]
        return apps

    def advance(
        self, application_id: int, new_status: str, notes: str = ""
    ) -> tuple[str | None, ApplicationDict | None]:
        """Advance application status. Returns (error, updated_application)."""
        if new_status not in APPLICATION_STATUSES:
            return f"Invalid status '{new_status}'. Valid: {', '.join(APPLICATION_STATUSES)}", None

        app = self.applications.get(application_id)
        if not app:
            return f"Application #{application_id} not found.", None

        event: ApplicationEventDict = {
            "status": new_status,
            "date": datetime.now().isoformat(),
            "notes": notes,
        }
        history = list(app.get("history") or [])
        history.append(event)
        app["history"] = history
        app["status"] = new_status
        if new_status == "applied" and not app.get("applied_date"):
            app["applied_date"] = datetime.now().isoformat()

        self.applications.update(app)
        return None, app

    def get_application_actions(self, limit: int = 10) -> list[dict]:
        """Return prioritized next actions across the application lifecycle.

        Deliberately separate from `contact_service.get_next_actions`: the two
        walk different id spaces, and `cli._daily_run_status` classifies a run by
        whether the *contact* planner produced anything. Merging these in would
        let a due application mask a broken contact planner — the exact failure
        that guard was added to catch.
        """
        today = datetime.now().date()
        actions: list[dict] = []

        for app in self.applications.list_all():
            status = app.get("status", "")
            if status in TERMINAL_APPLICATION_STATUSES:
                continue

            rule = APPLICATION_STATUS_RULES.get(status)
            if rule is None:
                continue

            age_days = self._days_since_reference(app, today)
            if age_days is None:
                # No usable timestamp at all. Surface it rather than skipping,
                # the way a contact with no dates yields `repair_contact`.
                actions.append(self._application_action(
                    app, 50, "repair_application",
                    "No applied_date/created_at; re-import or set a date",
                ))
                continue

            if age_days >= rule["after_days"]:
                actions.append(self._application_action(
                    app, rule["priority"] + min(age_days, 30), rule["action"],
                    rule["reason"].format(age=age_days),
                ))

        actions.sort(key=lambda a: a["priority"], reverse=True)
        return actions[:limit]

    def _days_since_reference(self, app: ApplicationDict, today) -> int | None:
        """Days since the last thing that happened *to the application*.

        Precedence, not max. `created_at` is bookkeeping — an import stamps it
        with the import time — and taking the max let that outrank a real
        applied date, making an application sent weeks ago look brand new. It
        stays only as a last resort for a record with no other date at all.
        """
        history = app.get("history") or []
        for candidate in (
            history[-1].get("date") if history else None,
            app.get("applied_date"),
            app.get("created_at"),
        ):
            parsed = parse_iso_date(candidate)
            if parsed is not None:
                return (today - parsed).days
        return None

    @staticmethod
    def _application_action(app: ApplicationDict, priority: int, action: str, reason: str) -> dict:
        return {
            "application_id": app.get("id"),
            "company": app.get("company", "Unknown"),
            "title": app.get("title", ""),
            "status": app.get("status", ""),
            "priority": priority,
            "action": action,
            "reason": reason,
        }

    def attach_resume(
        self,
        application_id: int,
        variant: str,
        resume_path: str = "",
        cover_letter_path: str = "",
    ) -> tuple[str | None, ApplicationDict | None]:
        """Record which resume variant/PDF backs this application."""
        app = self.applications.get(application_id)
        if not app:
            return f"Application #{application_id} not found.", None
        app["resume_variant"] = variant
        if resume_path:
            app["resume_path"] = resume_path
        if cover_letter_path:
            app["cover_letter_path"] = cover_letter_path
        self.applications.update(app)
        return None, app

    def delete(self, application_id: int) -> bool:
        return self.applications.delete(application_id)

    def get_stats(self) -> dict:
        apps = self.applications.list_all()
        by_status: dict[str, int] = {}
        for a in apps:
            s = a.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {"total": len(apps), "by_status": by_status}

    def tailor_resume(
        self, application_id: int, resume_override: str = ""
    ) -> tuple[str | None, str]:
        """AI-tailor resume bullets to a job description."""
        app = self.applications.get(application_id)
        if not app:
            return f"Application #{application_id} not found.", ""

        profile = self.profiles.get()
        resume_text = resume_override or (profile.get("resume_text", "") if profile else "")
        if not resume_text:
            return (
                "No resume found. Run `linkedin-cli profile setup` and paste your resume, "
                "or use --resume-file to provide one.",
                "",
            )

        jd = app.get("jd_text", "")
        prompt = f"""You are a professional resume writer. Rewrite the candidate's resume bullet points to better match this job description.

JOB: {app.get('title')} at {app.get('company')}
JOB DESCRIPTION:
{jd or 'Not provided.'}

CANDIDATE RESUME:
{resume_text}

Instructions:
- Rewrite only the experience bullet points (not summary/skills/education headers)
- Use keywords from the job description naturally
- Keep achievements quantified where they already exist
- Output ONLY the rewritten bullets, one per line starting with •
- Do not add fake achievements
- Maximum 8 bullets"""

        try:
            result = generate_with_ai(prompt, max_tokens=800)
        except AIClientError as exc:
            return str(exc), ""
        return None, result

    def cover_letter(self, application_id: int) -> tuple[str | None, str]:
        """AI-generate a cover letter for this application."""
        app = self.applications.get(application_id)
        if not app:
            return f"Application #{application_id} not found.", ""

        profile = self.profiles.get()
        if not profile or not profile.get("name"):
            return "Set up your profile first: linkedin-cli profile setup", ""

        prompt = f"""Write a concise, compelling cover letter for this job application.

APPLICANT: {profile.get('name')}
HEADLINE: {profile.get('headline', '')}
SKILLS: {profile.get('skills', '')}
EXPERIENCE: {profile.get('experience_summary', '')}
UNIQUE VALUE: {profile.get('unique_value', '')}
RESUME: {profile.get('resume_text', 'Not provided')}

JOB: {app.get('title')} at {app.get('company')}
JOB DESCRIPTION:
{app.get('jd_text') or 'Not provided.'}

Requirements:
- 3 paragraphs: hook/why-them, why-me/evidence, call to action
- Under 300 words
- Specific to this company and role — no generic phrases
- First person, confident but not arrogant
- Do not start with "I am writing to apply"
Output only the letter text."""

        try:
            result = generate_with_ai(prompt, max_tokens=800)
        except AIClientError as exc:
            return str(exc), ""
        return None, result

    def skills_gap(self, application_id: int) -> tuple[str | None, str]:
        """AI-generate a structured skills gap analysis vs the job description."""
        app = self.applications.get(application_id)
        if not app:
            return f"Application #{application_id} not found.", ""

        profile = self.profiles.get()
        my_skills = profile.get("skills", "") if profile else ""
        resume = profile.get("resume_text", "") if profile else ""

        if not app.get("jd_text"):
            return (
                "No job description saved. Add one with --jd flag when creating the application.",
                "",
            )

        prompt = f"""Analyze the skills gap between this candidate and job description.

CANDIDATE SKILLS: {my_skills or 'Not listed'}
CANDIDATE RESUME SUMMARY: {resume[:500] if resume else 'Not provided'}

JOB: {app.get('title')} at {app.get('company')}
JOB DESCRIPTION:
{app.get('jd_text')}

Output a structured analysis:

## Skills You Have ✓
- List matching skills

## Skills to Highlight More
- Skills you likely have but aren't emphasized

## Missing Skills ✗
- Skills in JD you don't appear to have

## Overall Fit
- 1-2 sentence assessment and recommendation

Be specific and actionable. Do not hallucinate skills the candidate hasn't mentioned."""

        try:
            result = generate_with_ai(prompt, max_tokens=600)
        except AIClientError as exc:
            return str(exc), ""
        return None, result
