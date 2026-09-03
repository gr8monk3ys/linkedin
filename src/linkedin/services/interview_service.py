"""Interview preparation service."""

from datetime import datetime

from linkedin.ai.client import ai_call
from linkedin.data.repository import ApplicationRepo, InterviewPrepRepo, ProfileRepo
from linkedin.types import InterviewPrepDict


class InterviewService:
    def __init__(
        self,
        application_repo: ApplicationRepo,
        prep_repo: InterviewPrepRepo,
        profile_repo: ProfileRepo,
    ):
        self.applications = application_repo
        self.prep_repo = prep_repo
        self.profiles = profile_repo

    def _get_app_or_error(self, application_id: int):
        app = self.applications.get(application_id)
        if not app:
            return None, f"Application #{application_id} not found."
        return app, None

    def prep(self, application_id: int) -> tuple[str | None, str]:
        """Generate role-specific interview questions + model STAR answers. Saves to prep store."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        profile = self.profiles.get()
        prompt = f"""You are an expert interview coach. Generate interview preparation for this candidate.

ROLE: {app.get("title")} at {app.get("company")}
JOB DESCRIPTION: {app.get("jd_text") or "Not provided"}
CANDIDATE SKILLS: {profile.get("skills", "Not specified") if profile else "Not specified"}
CANDIDATE EXPERIENCE: {profile.get("experience_summary", "") if profile else ""}

Generate:
## Likely Interview Questions (10 questions, mix of behavioral and technical)
Number each question.

## Model Answers (STAR format for top 3 behavioral questions)
For each: Situation -> Task -> Action -> Result

Keep answers concise and specific to this role."""

        generated = ai_call(prompt, max_tokens=1200)
        if generated.error:
            return generated.error, ""
        result = generated.text

        existing = self.prep_repo.get_by_application(application_id) or {}
        prep_data: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "questions": [result],
            "updated_at": datetime.now().isoformat(),
        }
        self.prep_repo.upsert(prep_data)
        return None, result

    def research(self, application_id: int) -> tuple[str | None, str]:
        """Generate company research briefing for the interview."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        prompt = f"""Generate a concise pre-interview company research briefing for:

COMPANY: {app.get("company")}
ROLE: {app.get("title")}
JD CONTEXT: {app.get("jd_text") or "Not provided"}

Include:
## Company Overview
- What they do, approximate size/stage, key products

## Recent News & Trends
- What's happening in their space (funding, launches, challenges)

## Culture & Values
- What's known about their engineering culture and values

## Tech Stack Clues
- Technologies mentioned in JD or known about the company

## Smart Questions to Reference
- 2-3 things you can mention to show research ("I noticed you recently...")

Keep under 400 words. Be factual - note if information is likely rather than confirmed."""

        generated = ai_call(prompt, max_tokens=800)
        if generated.error:
            return generated.error, ""
        result = generated.text

        existing = self.prep_repo.get_by_application(application_id) or {}
        prep_data: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "company_research": result,
            "updated_at": datetime.now().isoformat(),
        }
        self.prep_repo.upsert(prep_data)
        return None, result

    def star(self, application_id: int) -> tuple[str | None, str]:
        """Generate STAR method answer scaffolds for behavioral questions."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        profile = self.profiles.get()
        prompt = f"""Create STAR method answer scaffolds for a {app.get("title")} interview at {app.get("company")}.

CANDIDATE EXPERIENCE: {profile.get("experience_summary", "Not provided") if profile else "Not provided"}
CANDIDATE SKILLS: {profile.get("skills", "") if profile else ""}

Generate scaffolds for these 5 behavioral questions:
1. Tell me about a time you overcame a significant technical challenge
2. Describe a situation where you had to influence without authority
3. Tell me about a project you're most proud of
4. Describe a time you failed and what you learned
5. Tell me about a time you had to work under tight deadlines

For each:
**Question:** [question]
**Situation:** [1 sentence context - fill in your specific story here]
**Task:** [1 sentence - what was your responsibility]
**Action:** [2-3 sentences - specific steps you took]
**Result:** [1 sentence with metric/outcome if possible]

Keep each scaffold to 4-5 sentences max. Leave [FILL IN] markers where candidate should personalize."""

        generated = ai_call(prompt, max_tokens=1000)
        if generated.error:
            return generated.error, ""
        result = generated.text

        existing = self.prep_repo.get_by_application(application_id) or {}
        prep_data: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "star_answers": [result],
            "updated_at": datetime.now().isoformat(),
        }
        self.prep_repo.upsert(prep_data)
        return None, result

    def questions_to_ask(self, application_id: int) -> tuple[str | None, str]:
        """Generate a list of smart questions to ask the interviewer."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        prompt = f"""Generate 10 smart questions to ask during a {app.get("title")} interview at {app.get("company")}.

JD CONTEXT: {app.get("jd_text") or "Not provided"}

Include a mix of:
- Role clarity questions (expectations, success metrics, day-to-day)
- Team and culture questions
- Company direction questions
- Technical environment questions

Format: numbered list. Each question should be specific and show genuine curiosity.
Avoid generic questions like "What does success look like?" unless made specific.
Under 300 words."""

        generated = ai_call(prompt, max_tokens=400)
        if generated.error:
            return generated.error, ""
        result = generated.text

        existing = self.prep_repo.get_by_application(application_id) or {}
        prep_data: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "questions_to_ask": [result],
            "updated_at": datetime.now().isoformat(),
        }
        self.prep_repo.upsert(prep_data)
        return None, result

    def get_prep(self, application_id: int) -> InterviewPrepDict | None:
        return self.prep_repo.get_by_application(application_id)
