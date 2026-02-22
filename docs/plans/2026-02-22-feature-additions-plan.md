# Feature Additions v2.1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add job application lifecycle, interview prep, resume/cover-letter/skills-gap AI, conversation history, content calendar, and LinkedIn Playwright scraping to the CLI.

**Architecture:** Follow existing pattern exactly — abstract repo → JSON impl → service → CLI Click group → pytest tests. Agent 1 lays the shared foundation (types, repos, JSON store, factory, conftest); Agents 2–7 build independently on top of it.

**Tech Stack:** Python 3.10+, Click, Rich, Anthropic API (via existing `generate_with_ai`), Playwright (existing `LinkedInPage`), pytest with monkeypatching, uv.

---

## WAVE 1 — Foundation (must complete before Wave 2)

### Task 1: Types + Repos + JSON Store + Factory + conftest

**Files:**
- Modify: `src/linkedin/types.py`
- Modify: `src/linkedin/data/repository.py`
- Modify: `src/linkedin/data/json_store.py`
- Modify: `src/linkedin/data/factory.py`
- Modify: `tests/conftest.py`

**Step 1: Add new TypedDicts to `src/linkedin/types.py`**

Append after `ResearchDict`:

```python
class ApplicationEventDict(TypedDict, total=False):
    status: str
    date: str
    notes: str


class ApplicationDict(TypedDict, total=False):
    id: int
    company: str
    title: str
    url: str
    jd_text: str
    status: str          # saved|applied|phone_screen|technical|onsite|offer_received|accepted|rejected|ghosted
    applied_date: str | None
    contact_id: int | None
    notes: str
    created_at: str
    history: list[ApplicationEventDict]


class MessageDict(TypedDict, total=False):
    sender: str          # "me" or "them"
    text: str
    timestamp: str


class ConversationDict(TypedDict, total=False):
    contact_id: int
    messages: list[MessageDict]
    updated_at: str


class ContentPostDict(TypedDict, total=False):
    id: int
    title: str
    scheduled_date: str
    status: str          # scheduled|posted|skipped
    platform: str        # "linkedin"
    draft_id: int | None
    actual_posted_date: str | None
    created_at: str


class InterviewPrepDict(TypedDict, total=False):
    application_id: int
    questions: list[str]
    star_answers: list[str]
    company_research: str
    questions_to_ask: list[str]
    updated_at: str
```

**Step 2: Add abstract repos to `src/linkedin/data/repository.py`**

Add these imports at the top (merge into existing import):
```python
from linkedin.types import ApplicationDict, CompanyDict, ContactDict, ContentPostDict, ConversationDict, DraftDict, InterviewPrepDict, ProfileDict, ResearchDict
```

Append after `ResearchRepo`:

```python
class ApplicationRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[ApplicationDict]: ...

    @abstractmethod
    def get(self, application_id: int) -> ApplicationDict | None: ...

    @abstractmethod
    def add(self, application: ApplicationDict) -> ApplicationDict: ...

    @abstractmethod
    def update(self, application: ApplicationDict) -> None: ...

    @abstractmethod
    def delete(self, application_id: int) -> bool: ...

    @abstractmethod
    def next_id(self) -> int: ...


class ConversationRepo(ABC):
    @abstractmethod
    def get_by_contact(self, contact_id: int) -> ConversationDict | None: ...

    @abstractmethod
    def upsert(self, conversation: ConversationDict) -> None: ...

    @abstractmethod
    def list_all(self) -> list[ConversationDict]: ...


class CalendarRepo(ABC):
    @abstractmethod
    def list_all(self) -> list[ContentPostDict]: ...

    @abstractmethod
    def get(self, post_id: int) -> ContentPostDict | None: ...

    @abstractmethod
    def add(self, post: ContentPostDict) -> ContentPostDict: ...

    @abstractmethod
    def update(self, post: ContentPostDict) -> None: ...

    @abstractmethod
    def delete(self, post_id: int) -> bool: ...

    @abstractmethod
    def next_id(self) -> int: ...


class InterviewPrepRepo(ABC):
    @abstractmethod
    def get_by_application(self, application_id: int) -> InterviewPrepDict | None: ...

    @abstractmethod
    def upsert(self, prep: InterviewPrepDict) -> None: ...
```

**Step 3: Add JSON implementations to `src/linkedin/data/json_store.py`**

Add file path constants after `BACKUPS_DIR`:
```python
APPLICATIONS_FILE = DATA_DIR / "applications.json"
CONVERSATIONS_FILE = DATA_DIR / "conversations.json"
CALENDAR_FILE = DATA_DIR / "content_calendar.json"
INTERVIEW_PREP_FILE = DATA_DIR / "interview_prep.json"
```

Add imports at top of json_store.py (merge into existing):
```python
from linkedin.data.repository import ApplicationRepo, CalendarRepo, CompanyRepo, ContactRepo, ConversationRepo, DraftRepo, InterviewPrepRepo, ProfileRepo, ResearchRepo
from linkedin.types import ApplicationDict, CompanyDict, ContactDict, ContentPostDict, ConversationDict, DraftDict, InterviewPrepDict, ProfileDict, ResearchDict
```

Append JSON implementations after `JsonResearchRepo`:

```python
class JsonApplicationRepo(ApplicationRepo):
    def list_all(self) -> list[ApplicationDict]:
        return load_json(APPLICATIONS_FILE)

    def get(self, application_id: int) -> ApplicationDict | None:
        return next((a for a in self.list_all() if a["id"] == application_id), None)

    def add(self, application: ApplicationDict) -> ApplicationDict:
        apps = self.list_all()
        apps.append(application)
        save_json(APPLICATIONS_FILE, apps)
        return application

    def update(self, application: ApplicationDict) -> None:
        apps = self.list_all()
        for i, a in enumerate(apps):
            if a["id"] == application["id"]:
                apps[i] = application
                break
        save_json(APPLICATIONS_FILE, apps)

    def delete(self, application_id: int) -> bool:
        apps = self.list_all()
        new_apps = [a for a in apps if a["id"] != application_id]
        if len(new_apps) == len(apps):
            return False
        save_json(APPLICATIONS_FILE, new_apps)
        return True

    def next_id(self) -> int:
        return _next_id(self.list_all())


class JsonConversationRepo(ConversationRepo):
    def list_all(self) -> list[ConversationDict]:
        return load_json(CONVERSATIONS_FILE)

    def get_by_contact(self, contact_id: int) -> ConversationDict | None:
        return next((c for c in self.list_all() if c["contact_id"] == contact_id), None)

    def upsert(self, conversation: ConversationDict) -> None:
        convs = self.list_all()
        for i, c in enumerate(convs):
            if c["contact_id"] == conversation["contact_id"]:
                convs[i] = conversation
                save_json(CONVERSATIONS_FILE, convs)
                return
        convs.append(conversation)
        save_json(CONVERSATIONS_FILE, convs)


class JsonCalendarRepo(CalendarRepo):
    def list_all(self) -> list[ContentPostDict]:
        return load_json(CALENDAR_FILE)

    def get(self, post_id: int) -> ContentPostDict | None:
        return next((p for p in self.list_all() if p["id"] == post_id), None)

    def add(self, post: ContentPostDict) -> ContentPostDict:
        posts = self.list_all()
        posts.append(post)
        save_json(CALENDAR_FILE, posts)
        return post

    def update(self, post: ContentPostDict) -> None:
        posts = self.list_all()
        for i, p in enumerate(posts):
            if p["id"] == post["id"]:
                posts[i] = post
                break
        save_json(CALENDAR_FILE, posts)

    def delete(self, post_id: int) -> bool:
        posts = self.list_all()
        new_posts = [p for p in posts if p["id"] != post_id]
        if len(new_posts) == len(posts):
            return False
        save_json(CALENDAR_FILE, new_posts)
        return True

    def next_id(self) -> int:
        return _next_id(self.list_all())


class JsonInterviewPrepRepo(InterviewPrepRepo):
    def get_by_application(self, application_id: int) -> InterviewPrepDict | None:
        all_prep = load_json(INTERVIEW_PREP_FILE)
        return next((p for p in all_prep if p["application_id"] == application_id), None)

    def upsert(self, prep: InterviewPrepDict) -> None:
        all_prep = load_json(INTERVIEW_PREP_FILE)
        for i, p in enumerate(all_prep):
            if p["application_id"] == prep["application_id"]:
                all_prep[i] = prep
                save_json(INTERVIEW_PREP_FILE, all_prep)
                return
        all_prep.append(prep)
        save_json(INTERVIEW_PREP_FILE, all_prep)
```

**Step 4: Update `src/linkedin/data/factory.py`**

Replace entire file contents:

```python
"""Factory for selecting data backend (JSON or Database)."""

import os

from linkedin.data.repository import (
    ApplicationRepo,
    CalendarRepo,
    CompanyRepo,
    ContactRepo,
    ConversationRepo,
    DraftRepo,
    InterviewPrepRepo,
    ProfileRepo,
    ResearchRepo,
)


def get_backend() -> str:
    return os.environ.get("LINKEDIN_BACKEND", "json").lower()


def create_repos() -> tuple[
    ContactRepo,
    CompanyRepo,
    ProfileRepo,
    DraftRepo,
    ResearchRepo,
    ApplicationRepo,
    ConversationRepo,
    CalendarRepo,
    InterviewPrepRepo,
]:
    backend = get_backend()

    if backend == "db":
        from linkedin.data.db_store import (
            DbCompanyRepo,
            DbContactRepo,
            DbDraftRepo,
            DbProfileRepo,
            DbResearchRepo,
        )
        from linkedin.models.base import create_tables

        create_tables()
        # DB store stubs for new repos — fall back to JSON for now
        from linkedin.data.json_store import (
            JsonApplicationRepo,
            JsonCalendarRepo,
            JsonConversationRepo,
            JsonInterviewPrepRepo,
        )
        return (
            DbContactRepo(),
            DbCompanyRepo(),
            DbProfileRepo(),
            DbDraftRepo(),
            DbResearchRepo(),
            JsonApplicationRepo(),
            JsonConversationRepo(),
            JsonCalendarRepo(),
            JsonInterviewPrepRepo(),
        )

    from linkedin.data.json_store import (
        JsonApplicationRepo,
        JsonCalendarRepo,
        JsonCompanyRepo,
        JsonContactRepo,
        JsonConversationRepo,
        JsonDraftRepo,
        JsonInterviewPrepRepo,
        JsonProfileRepo,
        JsonResearchRepo,
    )

    return (
        JsonContactRepo(),
        JsonCompanyRepo(),
        JsonProfileRepo(),
        JsonDraftRepo(),
        JsonResearchRepo(),
        JsonApplicationRepo(),
        JsonConversationRepo(),
        JsonCalendarRepo(),
        JsonInterviewPrepRepo(),
    )
```

**Step 5: Update `tests/conftest.py`** — add monkeypatching for new file paths and new fixtures

Add to the existing `json_repos` fixture monkeypatches:
```python
monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")
monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")
```

Change the `json_repos` return tuple to include new repos:
```python
from linkedin.data.json_store import (
    JsonApplicationRepo,
    JsonCalendarRepo,
    JsonConversationRepo,
    JsonInterviewPrepRepo,
    ...existing...
)

return (
    JsonContactRepo(),
    JsonCompanyRepo(),
    JsonProfileRepo(),
    JsonDraftRepo(),
    JsonResearchRepo(),
    JsonApplicationRepo(),
    JsonConversationRepo(),
    JsonCalendarRepo(),
    JsonInterviewPrepRepo(),
)
```

Add factory helpers:
```python
def sample_application(**overrides):
    defaults = {
        "company": "Acme Corp",
        "title": "ML Engineer",
        "url": "https://acme.com/jobs/123",
        "jd_text": "We need Python, ML, and 3+ years experience.",
        "status": "saved",
        "notes": "",
        "history": [],
    }
    defaults.update(overrides)
    return defaults


def sample_content_post(**overrides):
    defaults = {
        "title": "Why I love Python",
        "scheduled_date": "2026-03-01",
        "status": "scheduled",
        "platform": "linkedin",
    }
    defaults.update(overrides)
    return defaults
```

**Step 6: Update `src/linkedin/cli.py`** — unpack new repos from create_repos()

Find the line:
```python
_contact_repo, _company_repo, _profile_repo, _draft_repo, _research_repo = create_repos()
```
Replace with:
```python
(
    _contact_repo,
    _company_repo,
    _profile_repo,
    _draft_repo,
    _research_repo,
    _application_repo,
    _conversation_repo,
    _calendar_repo,
    _interview_prep_repo,
) = create_repos()
```

**Step 7: Run existing tests to make sure nothing broke**

```bash
uv run pytest tests/ -x -q
```
Expected: all existing tests pass.

**Step 8: Commit**

```bash
git add src/linkedin/types.py src/linkedin/data/repository.py src/linkedin/data/json_store.py src/linkedin/data/factory.py src/linkedin/cli.py tests/conftest.py
git commit -m "feat: add types, repos, JSON store, factory for applications/conversations/calendar/interview-prep"
```

---

## WAVE 2 — Services + CLI + Tests (parallel, all depend on Wave 1)

### Task 2: ApplicationService

**Files:**
- Create: `src/linkedin/services/application_service.py`
- Create: `tests/test_applications.py`

**Step 1: Write failing tests first — `tests/test_applications.py`**

```python
"""Tests for ApplicationService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import (
    JsonApplicationRepo, JsonProfileRepo, JsonContactRepo, JsonCompanyRepo,
)
from linkedin.services.application_service import ApplicationService
from tests.conftest import sample_application, sample_profile


@pytest.fixture
def app_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    return JsonApplicationRepo(), JsonProfileRepo(), JsonContactRepo()


@pytest.fixture
def svc(app_repos):
    app_repo, profile_repo, contact_repo = app_repos
    return ApplicationService(app_repo, profile_repo, contact_repo)


def test_add_and_list(svc):
    svc.add_application("Acme", "ML Engineer", url="https://acme.com", jd_text="Python required")
    apps = svc.list_applications()
    assert len(apps) == 1
    assert apps[0]["company"] == "Acme"
    assert apps[0]["status"] == "saved"
    assert apps[0]["id"] is not None


def test_advance_status(svc):
    svc.add_application("Acme", "ML Engineer")
    apps = svc.list_applications()
    app_id = apps[0]["id"]
    svc.advance(app_id, "applied", notes="Submitted via website")
    app = svc.get_application(app_id)
    assert app["status"] == "applied"
    assert len(app["history"]) == 1
    assert app["history"][0]["status"] == "applied"
    assert app["history"][0]["notes"] == "Submitted via website"


def test_advance_invalid_status(svc):
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    error, _ = svc.advance(app_id, "hired")  # not valid
    assert error is not None


def test_delete(svc):
    svc.add_application("Acme", "ML Engineer")
    app_id = svc.list_applications()[0]["id"]
    assert svc.delete(app_id) is True
    assert svc.get_application(app_id) is None


def test_filter_by_status(svc):
    svc.add_application("Acme", "ML Engineer")
    svc.advance(svc.list_applications()[0]["id"], "applied")
    svc.add_application("Beta", "Data Engineer")
    applied = svc.list_applications(status="applied")
    assert len(applied) == 1
    assert applied[0]["company"] == "Acme"


def test_stats_empty(svc):
    stats = svc.get_stats()
    assert stats["total"] == 0
    assert stats["by_status"] == {}


def test_stats_counts(svc):
    svc.add_application("A", "E1")
    svc.add_application("B", "E2")
    svc.advance(svc.list_applications()[0]["id"], "applied")
    stats = svc.get_stats()
    assert stats["total"] == 2
    assert stats["by_status"].get("applied") == 1
    assert stats["by_status"].get("saved") == 1


def test_tailor_resume_no_profile(svc):
    svc.add_application("Acme", "ML Engineer", jd_text="Python, ML")
    app_id = svc.list_applications()[0]["id"]
    error, _ = svc.tailor_resume(app_id)
    assert error is not None  # no profile set


def test_tailor_resume_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(resume_text="I built ML models for 3 years."))
    svc.add_application("Acme", "ML Engineer", jd_text="Need Python, MLOps")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=800: "• Built ML pipelines\n• Deployed models with MLOps",
    )
    error, result = svc.tailor_resume(app_id)
    assert error is None
    assert "ML" in result


def test_cover_letter_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(resume_text="5 years Python."))
    svc.add_application("Acme", "ML Engineer", jd_text="Python ML engineer")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=800: "Dear Hiring Manager, I am excited...",
    )
    error, result = svc.cover_letter(app_id)
    assert error is None
    assert "Hiring Manager" in result


def test_skills_gap_with_ai(svc, app_repos, monkeypatch):
    _, profile_repo, _ = app_repos
    profile_repo.save(sample_profile(skills="Python, ML", resume_text="5 years Python."))
    svc.add_application("Acme", "ML Engineer", jd_text="Python, Kubernetes, MLOps")
    app_id = svc.list_applications()[0]["id"]
    monkeypatch.setattr(
        "linkedin.services.application_service.generate_with_ai",
        lambda prompt, max_tokens=600: "You have: Python, ML\nMissing: Kubernetes, MLOps",
    )
    error, result = svc.skills_gap(app_id)
    assert error is None
    assert "Missing" in result
```

**Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_applications.py -x -q
```
Expected: `ModuleNotFoundError: No module named 'linkedin.services.application_service'`

**Step 3: Create `src/linkedin/services/application_service.py`**

```python
"""Job application lifecycle service."""

from datetime import datetime

from linkedin.ai.client import AIClientError, generate_with_ai
from linkedin.data.repository import ApplicationRepo, ContactRepo, ProfileRepo
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
        resume_text = resume_override or profile.get("resume_text", "")
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
                "No job description saved. Run `linkedin-cli applications view` and add one with "
                "`applications advance` or re-add with --jd flag.",
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
```

**Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_applications.py -v
```
Expected: all 12 tests pass.

**Step 5: Commit**

```bash
git add src/linkedin/services/application_service.py tests/test_applications.py
git commit -m "feat: add ApplicationService with CRUD, pipeline advance, AI resume/cover-letter/skills-gap"
```

---

### Task 3: InterviewService

**Files:**
- Create: `src/linkedin/services/interview_service.py`
- Create: `tests/test_interview.py`

**Step 1: Write failing tests — `tests/test_interview.py`**

```python
"""Tests for InterviewService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import (
    JsonApplicationRepo, JsonInterviewPrepRepo, JsonProfileRepo,
)
from linkedin.services.interview_service import InterviewService
from tests.conftest import sample_application, sample_profile


@pytest.fixture
def interview_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    return JsonApplicationRepo(), JsonInterviewPrepRepo(), JsonProfileRepo()


@pytest.fixture
def svc(interview_repos):
    app_repo, prep_repo, profile_repo = interview_repos
    return InterviewService(app_repo, prep_repo, profile_repo)


@pytest.fixture
def app_with_jd(interview_repos):
    app_repo, _, _ = interview_repos
    app = {
        "id": 1,
        "company": "Acme",
        "title": "ML Engineer",
        "jd_text": "We need Python, ML, Kubernetes. Strong communication required.",
        "status": "phone_screen",
        "history": [],
    }
    app_repo.add(app)
    return app


def test_prep_no_application(svc):
    error, _ = svc.prep(999)
    assert error is not None
    assert "not found" in error.lower()


def test_prep_generates_questions(svc, app_with_jd, interview_repos, monkeypatch):
    _, _, profile_repo = interview_repos
    profile_repo.save(sample_profile())
    monkeypatch.setattr(
        "linkedin.services.interview_service.generate_with_ai",
        lambda prompt, max_tokens=1200: "1. Tell me about your ML experience.\n2. How do you handle ambiguity?\n3. Describe a difficult technical challenge.",
    )
    error, result = svc.prep(1)
    assert error is None
    assert "ML" in result or "experience" in result.lower()
    # Verify it was saved
    prep = svc.get_prep(1)
    assert prep is not None


def test_research_generates_briefing(svc, app_with_jd, monkeypatch):
    monkeypatch.setattr(
        "linkedin.services.interview_service.generate_with_ai",
        lambda prompt, max_tokens=800: "Acme Corp: Founded 2015, Series B, 200 employees. Known for ML infra.",
    )
    error, result = svc.research(1)
    assert error is None
    assert "Acme" in result


def test_star_generates_answers(svc, app_with_jd, interview_repos, monkeypatch):
    _, _, profile_repo = interview_repos
    profile_repo.save(sample_profile())
    monkeypatch.setattr(
        "linkedin.services.interview_service.generate_with_ai",
        lambda prompt, max_tokens=1000: "STAR Answer 1:\nSituation: ...\nTask: ...\nAction: ...\nResult: ...",
    )
    error, result = svc.star(1)
    assert error is None
    assert "Situation" in result or "STAR" in result


def test_questions_to_ask(svc, app_with_jd, monkeypatch):
    monkeypatch.setattr(
        "linkedin.services.interview_service.generate_with_ai",
        lambda prompt, max_tokens=400: "1. What does the ML infrastructure look like?\n2. How do you measure success?",
    )
    error, result = svc.questions_to_ask(1)
    assert error is None
    assert "?" in result or "infrastructure" in result.lower()


def test_get_prep_none_when_missing(svc, app_with_jd):
    prep = svc.get_prep(1)
    assert prep is None
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_interview.py -x -q
```

**Step 3: Create `src/linkedin/services/interview_service.py`**

```python
"""Interview preparation service."""

from datetime import datetime

from linkedin.ai.client import AIClientError, generate_with_ai
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
        self.prep = prep_repo
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

ROLE: {app.get('title')} at {app.get('company')}
JOB DESCRIPTION: {app.get('jd_text') or 'Not provided'}
CANDIDATE SKILLS: {profile.get('skills', 'Not specified') if profile else 'Not specified'}
CANDIDATE EXPERIENCE: {profile.get('experience_summary', '') if profile else ''}

Generate:
## Likely Interview Questions (10 questions, mix of behavioral and technical)
Number each question.

## Model Answers (STAR format for top 3 behavioral questions)
For each: Situation → Task → Action → Result

Keep answers concise and specific to this role."""

        try:
            result = generate_with_ai(prompt, max_tokens=1200)
        except AIClientError as exc:
            return str(exc), ""

        existing = self.prep.get_by_application(application_id) or {}
        prep: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "questions": [result],  # store raw AI output
            "updated_at": datetime.now().isoformat(),
        }
        self.prep.upsert(prep)
        return None, result

    def research(self, application_id: int) -> tuple[str | None, str]:
        """Generate company research briefing for the interview."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        prompt = f"""Generate a concise pre-interview company research briefing for:

COMPANY: {app.get('company')}
ROLE: {app.get('title')}
JD CONTEXT: {app.get('jd_text') or 'Not provided'}

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

Keep under 400 words. Be factual — note if information is likely rather than confirmed."""

        try:
            result = generate_with_ai(prompt, max_tokens=800)
        except AIClientError as exc:
            return str(exc), ""

        existing = self.prep.get_by_application(application_id) or {}
        prep: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "company_research": result,
            "updated_at": datetime.now().isoformat(),
        }
        self.prep.upsert(prep)
        return None, result

    def star(self, application_id: int) -> tuple[str | None, str]:
        """Generate STAR method answer scaffolds for behavioral questions."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        profile = self.profiles.get()
        prompt = f"""Create STAR method answer scaffolds for a {app.get('title')} interview at {app.get('company')}.

CANDIDATE EXPERIENCE: {profile.get('experience_summary', 'Not provided') if profile else 'Not provided'}
CANDIDATE SKILLS: {profile.get('skills', '') if profile else ''}

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

        try:
            result = generate_with_ai(prompt, max_tokens=1000)
        except AIClientError as exc:
            return str(exc), ""

        existing = self.prep.get_by_application(application_id) or {}
        prep: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "star_answers": [result],
            "updated_at": datetime.now().isoformat(),
        }
        self.prep.upsert(prep)
        return None, result

    def questions_to_ask(self, application_id: int) -> tuple[str | None, str]:
        """Generate a list of smart questions to ask the interviewer."""
        app, err = self._get_app_or_error(application_id)
        if err:
            return err, ""

        prompt = f"""Generate 10 smart questions to ask during a {app.get('title')} interview at {app.get('company')}.

JD CONTEXT: {app.get('jd_text') or 'Not provided'}

Include a mix of:
- Role clarity questions (expectations, success metrics, day-to-day)
- Team and culture questions
- Company direction questions
- Technical environment questions

Format: numbered list. Each question should be specific and show genuine curiosity.
Avoid generic questions like "What does success look like?" unless made specific.
Under 300 words."""

        try:
            result = generate_with_ai(prompt, max_tokens=400)
        except AIClientError as exc:
            return str(exc), ""

        existing = self.prep.get_by_application(application_id) or {}
        prep: InterviewPrepDict = {
            **existing,
            "application_id": application_id,
            "questions_to_ask": [result],
            "updated_at": datetime.now().isoformat(),
        }
        self.prep.upsert(prep)
        return None, result

    def get_prep(self, application_id: int) -> InterviewPrepDict | None:
        return self.prep.get_by_application(application_id)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_interview.py -v
```
Expected: all 6 tests pass.

**Step 5: Commit**

```bash
git add src/linkedin/services/interview_service.py tests/test_interview.py
git commit -m "feat: add InterviewService with AI-powered prep, research, STAR, questions-to-ask"
```

---

### Task 4: ConversationService + ContentCalendarService

**Files:**
- Create: `src/linkedin/services/conversation_service.py`
- Create: `src/linkedin/services/calendar_service.py`
- Create: `tests/test_conversations.py`
- Create: `tests/test_calendar.py`

**Step 1: Write failing tests — `tests/test_conversations.py`**

```python
"""Tests for ConversationService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import JsonConversationRepo, JsonContactRepo, JsonCompanyRepo
from linkedin.services.conversation_service import ConversationService
from tests.conftest import sample_contact


@pytest.fixture
def conv_repos(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    contact_repo = JsonContactRepo()
    contact_repo.add({**sample_contact(), "id": 1})
    return JsonConversationRepo(), contact_repo


@pytest.fixture
def svc(conv_repos):
    conv_repo, contact_repo = conv_repos
    return ConversationService(conv_repo, contact_repo)


def test_log_first_message(svc):
    svc.log(1, sender="me", text="Hi there!")
    thread = svc.get_thread(1)
    assert thread is not None
    assert len(thread["messages"]) == 1
    assert thread["messages"][0]["text"] == "Hi there!"
    assert thread["messages"][0]["sender"] == "me"


def test_log_multiple_messages_ordered(svc):
    svc.log(1, sender="me", text="First message")
    svc.log(1, sender="them", text="Their reply")
    svc.log(1, sender="me", text="My follow-up")
    thread = svc.get_thread(1)
    assert len(thread["messages"]) == 3
    assert thread["messages"][0]["text"] == "First message"
    assert thread["messages"][1]["sender"] == "them"
    assert thread["messages"][2]["text"] == "My follow-up"


def test_log_invalid_sender(svc):
    with pytest.raises(ValueError, match="sender"):
        svc.log(1, sender="robot", text="Hello")


def test_get_thread_none_when_empty(svc):
    thread = svc.get_thread(1)
    assert thread is None


def test_export_plain_text(svc):
    svc.log(1, sender="me", text="Hey!")
    svc.log(1, sender="them", text="Hello back")
    export = svc.export(1)
    assert "Hey!" in export
    assert "Hello back" in export
    assert "me" in export.lower() or "them" in export.lower()


def test_contact_not_found(svc):
    with pytest.raises(ValueError, match="not found"):
        svc.log(999, sender="me", text="Hello")
```

**Step 2: Write `tests/test_calendar.py`**

```python
"""Tests for ContentCalendarService."""

import pytest
import linkedin.data.json_store as js
from linkedin.data.json_store import JsonCalendarRepo
from linkedin.services.calendar_service import ContentCalendarService
from tests.conftest import sample_content_post


@pytest.fixture
def cal_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")
    return JsonCalendarRepo()


@pytest.fixture
def svc(cal_repo):
    return ContentCalendarService(cal_repo)


def test_add_and_list(svc):
    svc.add(title="Why Python rocks", scheduled_date="2026-03-01")
    posts = svc.list_all()
    assert len(posts) == 1
    assert posts[0]["title"] == "Why Python rocks"
    assert posts[0]["status"] == "scheduled"


def test_mark_posted(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id)
    post = svc.get(post_id)
    assert post["status"] == "posted"
    assert post["actual_posted_date"] is not None


def test_mark_posted_with_date(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.mark_posted(post_id, posted_date="2026-03-02")
    assert svc.get(post_id)["actual_posted_date"] == "2026-03-02"


def test_delete(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    post_id = svc.list_all()[0]["id"]
    svc.delete(post_id)
    assert svc.get(post_id) is None


def test_list_upcoming(svc):
    svc.add(title="Future", scheduled_date="2030-01-01")
    svc.add(title="Past", scheduled_date="2020-01-01")
    upcoming = svc.list_upcoming(days=3650)
    assert any(p["title"] == "Future" for p in upcoming)


def test_stats_empty(svc):
    stats = svc.get_stats()
    assert stats["total"] == 0
    assert stats["scheduled"] == 0
    assert stats["posted"] == 0


def test_stats_counts(svc):
    svc.add(title="Post 1", scheduled_date="2026-03-01")
    svc.add(title="Post 2", scheduled_date="2026-03-08")
    svc.mark_posted(svc.list_all()[0]["id"])
    stats = svc.get_stats()
    assert stats["total"] == 2
    assert stats["posted"] == 1
    assert stats["scheduled"] == 1
```

**Step 3: Run both to confirm failure**

```bash
uv run pytest tests/test_conversations.py tests/test_calendar.py -x -q
```

**Step 4: Create `src/linkedin/services/conversation_service.py`**

```python
"""Conversation history service — log and view LinkedIn message threads."""

from datetime import datetime

from linkedin.data.repository import ContactRepo, ConversationRepo
from linkedin.types import ConversationDict, MessageDict

VALID_SENDERS = {"me", "them"}


class ConversationService:
    def __init__(self, conversation_repo: ConversationRepo, contact_repo: ContactRepo):
        self.conversations = conversation_repo
        self.contacts = contact_repo

    def log(
        self,
        contact_id: int,
        sender: str,
        text: str,
        timestamp: str = "",
    ) -> ConversationDict:
        if sender not in VALID_SENDERS:
            raise ValueError(f"Invalid sender '{sender}'. Must be 'me' or 'them'.")

        contact = self.contacts.get(contact_id)
        if not contact:
            raise ValueError(f"Contact #{contact_id} not found.")

        message: MessageDict = {
            "sender": sender,
            "text": text,
            "timestamp": timestamp or datetime.now().isoformat(),
        }

        existing = self.conversations.get_by_contact(contact_id)
        if existing:
            messages = list(existing.get("messages") or [])
            messages.append(message)
            conv: ConversationDict = {
                **existing,
                "messages": messages,
                "updated_at": datetime.now().isoformat(),
            }
        else:
            conv = {
                "contact_id": contact_id,
                "messages": [message],
                "updated_at": datetime.now().isoformat(),
            }

        self.conversations.upsert(conv)
        return conv

    def get_thread(self, contact_id: int) -> ConversationDict | None:
        return self.conversations.get_by_contact(contact_id)

    def export(self, contact_id: int) -> str:
        thread = self.get_thread(contact_id)
        if not thread:
            return ""
        lines = []
        for msg in thread.get("messages") or []:
            prefix = "[Me]" if msg["sender"] == "me" else "[Them]"
            ts = msg.get("timestamp", "")[:16]
            lines.append(f"{prefix} ({ts}): {msg['text']}")
        return "\n".join(lines)
```

**Step 5: Create `src/linkedin/services/calendar_service.py`**

```python
"""Content calendar service — schedule and track LinkedIn posts."""

from datetime import datetime, timedelta

from linkedin.data.repository import CalendarRepo
from linkedin.types import ContentPostDict


class ContentCalendarService:
    def __init__(self, calendar_repo: CalendarRepo):
        self.calendar = calendar_repo

    def add(
        self,
        title: str,
        scheduled_date: str,
        draft_id: int | None = None,
        platform: str = "linkedin",
    ) -> ContentPostDict:
        post: ContentPostDict = {
            "id": self.calendar.next_id(),
            "title": title,
            "scheduled_date": scheduled_date,
            "status": "scheduled",
            "platform": platform,
            "draft_id": draft_id,
            "actual_posted_date": None,
            "created_at": datetime.now().isoformat(),
        }
        return self.calendar.add(post)

    def get(self, post_id: int) -> ContentPostDict | None:
        return self.calendar.get(post_id)

    def list_all(self) -> list[ContentPostDict]:
        return sorted(self.calendar.list_all(), key=lambda p: p.get("scheduled_date", ""))

    def list_upcoming(self, days: int = 14) -> list[ContentPostDict]:
        cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        today = datetime.now().strftime("%Y-%m-%d")
        return [
            p for p in self.list_all()
            if p.get("status") == "scheduled"
            and today <= p.get("scheduled_date", "") <= cutoff
        ]

    def mark_posted(self, post_id: int, posted_date: str = "") -> ContentPostDict | None:
        post = self.calendar.get(post_id)
        if not post:
            return None
        post["status"] = "posted"
        post["actual_posted_date"] = posted_date or datetime.now().strftime("%Y-%m-%d")
        self.calendar.update(post)
        return post

    def delete(self, post_id: int) -> bool:
        return self.calendar.delete(post_id)

    def get_stats(self) -> dict:
        posts = self.calendar.list_all()
        by_status: dict[str, int] = {}
        for p in posts:
            s = p.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": len(posts),
            "scheduled": by_status.get("scheduled", 0),
            "posted": by_status.get("posted", 0),
            "skipped": by_status.get("skipped", 0),
        }
```

**Step 6: Run tests**

```bash
uv run pytest tests/test_conversations.py tests/test_calendar.py -v
```
Expected: all 14 tests pass.

**Step 7: Commit**

```bash
git add src/linkedin/services/conversation_service.py src/linkedin/services/calendar_service.py tests/test_conversations.py tests/test_calendar.py
git commit -m "feat: add ConversationService and ContentCalendarService with full test coverage"
```

---

### Task 5: CLI Command Groups

**Files:**
- Modify: `src/linkedin/cli.py`
- Create: `tests/test_cli_applications.py`
- Create: `tests/test_cli_interview.py`

**Step 1: Write failing CLI tests — `tests/test_cli_applications.py`**

```python
"""CLI integration tests for applications and interview commands."""

import pytest
import linkedin.data.json_store as js
from click.testing import CliRunner
from linkedin.cli import cli


@pytest.fixture(autouse=True)
def patch_json_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "APPLICATIONS_FILE", tmp_path / "applications.json")
    monkeypatch.setattr(js, "PROFILE_FILE", tmp_path / "profile.json")
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    monkeypatch.setattr(js, "INTERVIEW_PREP_FILE", tmp_path / "interview_prep.json")
    monkeypatch.setattr(js, "CONVERSATIONS_FILE", tmp_path / "conversations.json")
    monkeypatch.setattr(js, "CALENDAR_FILE", tmp_path / "content_calendar.json")


@pytest.fixture
def runner():
    return CliRunner()


def test_applications_add(runner):
    result = runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_applications_list_empty(runner):
    result = runner.invoke(cli, ["applications", "list"])
    assert result.exit_code == 0


def test_applications_add_and_list(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "list"])
    assert result.exit_code == 0
    assert "Acme" in result.output


def test_applications_advance(runner):
    runner.invoke(cli, ["applications", "add", "--company", "Acme", "--title", "ML Engineer"])
    result = runner.invoke(cli, ["applications", "advance", "1", "--status", "applied"])
    assert result.exit_code == 0
    assert "applied" in result.output.lower() or result.exit_code == 0


def test_applications_stats(runner):
    result = runner.invoke(cli, ["applications", "stats"])
    assert result.exit_code == 0


def test_applications_view_not_found(runner):
    result = runner.invoke(cli, ["applications", "view", "999"])
    assert result.exit_code != 0 or "not found" in result.output.lower()


def test_conversations_log_and_view(runner):
    # Need a contact first
    runner.invoke(cli, ["contacts", "add", "--name", "Alice", "--title", "PM", "--company", "Beta"])
    result = runner.invoke(cli, ["conversations", "log", "1", "--from", "me", "--text", "Hey Alice!"])
    assert result.exit_code == 0
    view = runner.invoke(cli, ["conversations", "view", "1"])
    assert "Hey Alice" in view.output


def test_calendar_add_and_list(runner):
    runner.invoke(cli, ["calendar", "add", "--title", "Post 1", "--date", "2026-03-01"])
    result = runner.invoke(cli, ["calendar", "list"])
    assert result.exit_code == 0
    assert "Post 1" in result.output


def test_calendar_mark_posted(runner):
    runner.invoke(cli, ["calendar", "add", "--title", "Post 1", "--date", "2026-03-01"])
    result = runner.invoke(cli, ["calendar", "mark-posted", "1"])
    assert result.exit_code == 0
```

**Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_cli_applications.py -x -q
```
Expected: errors about missing command groups.

**Step 3: Add new command groups to `src/linkedin/cli.py`**

At the bottom of cli.py, after existing command groups, add these new groups. Also add service instantiation near the top where other services are created:

**Add service instantiation** (after existing service lines):
```python
from linkedin.services.application_service import ApplicationService
from linkedin.services.calendar_service import ContentCalendarService
from linkedin.services.conversation_service import ConversationService
from linkedin.services.interview_service import InterviewService

_application_svc = ApplicationService(_application_repo, _profile_repo, _contact_repo)
_interview_svc = InterviewService(_application_repo, _interview_prep_repo, _profile_repo)
_conversation_svc = ConversationService(_conversation_repo, _contact_repo)
_calendar_svc = ContentCalendarService(_calendar_repo)
```

**Add `applications` group:**
```python
@cli.group()
def applications():
    """Track job applications through their lifecycle."""


@applications.command("add")
@click.option("--company", "-c", required=True, help="Company name")
@click.option("--title", "-t", required=True, help="Job title")
@click.option("--url", "-u", default="", help="Job posting URL")
@click.option("--jd", default="", help="Job description text")
@click.option("--notes", "-n", default="", help="Notes")
def applications_add(company, title, url, jd, notes):
    """Add a new job application."""
    app = _application_svc.add_application(company, title, url=url, jd_text=jd, notes=notes)
    console.print(f"[green]Added application #{app['id']}:[/green] {title} at {company}")


@applications.command("list")
@click.option("--status", default="all", help="Filter by status")
@click.option("--company", default="", help="Filter by company name")
def applications_list(status, company):
    """List applications."""
    apps = _application_svc.list_applications(status=status, company=company)
    if not apps:
        console.print("[dim]No applications found.[/dim]")
        return
    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Company", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Applied", style="dim")
    for a in apps:
        table.add_row(
            str(a["id"]),
            a.get("company", ""),
            a.get("title", ""),
            a.get("status", ""),
            (a.get("applied_date") or "—")[:10],
        )
    console.print(table)


@applications.command("view")
@click.argument("application_id", type=int)
def applications_view(application_id):
    """View application details."""
    app = _application_svc.get_application(application_id)
    if not app:
        console.print(f"[red]Application #{application_id} not found.[/red]")
        raise SystemExit(1)
    console.print(Panel(
        f"[bold]{app.get('title')}[/bold] at [cyan]{app.get('company')}[/cyan]\n"
        f"Status: [yellow]{app.get('status')}[/yellow]  |  Applied: {(app.get('applied_date') or 'Not yet')[:10]}\n"
        f"URL: {app.get('url') or '—'}\n"
        f"Notes: {app.get('notes') or '—'}\n"
        f"JD: {(app.get('jd_text') or '—')[:200]}{'...' if len(app.get('jd_text') or '') > 200 else ''}",
        title=f"Application #{application_id}",
    ))
    history = app.get("history") or []
    if history:
        console.print("\n[bold]History:[/bold]")
        for event in history:
            console.print(f"  {event.get('date', '')[:10]}  {event.get('status')}  {event.get('notes') or ''}")


@applications.command("advance")
@click.argument("application_id", type=int)
@click.option("--status", "-s", required=True, help="New status")
@click.option("--notes", "-n", default="", help="Notes for this stage")
def applications_advance(application_id, status, notes):
    """Advance application to next status."""
    error, app = _application_svc.advance(application_id, status, notes=notes)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Advanced #{application_id} to:[/green] {status}")


@applications.command("tailor-resume")
@click.argument("application_id", type=int)
@click.option("--resume-file", "-r", default="", help="Path to resume .txt file to override profile resume")
@click.option("--save", is_flag=True, help="Save result as a draft")
def applications_tailor_resume(application_id, resume_file, save):
    """AI-tailor resume bullets to this job's description."""
    resume_text = ""
    if resume_file:
        try:
            resume_text = open(resume_file).read()
        except OSError as e:
            console.print(f"[red]Cannot read file: {e}[/red]")
            raise SystemExit(1)
    error, result = _application_svc.tailor_resume(application_id, resume_override=resume_text)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Panel(result, title="Tailored Resume Bullets"))


@applications.command("cover-letter")
@click.argument("application_id", type=int)
def applications_cover_letter(application_id):
    """AI-generate a cover letter for this application."""
    error, result = _application_svc.cover_letter(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Panel(result, title="Cover Letter"))


@applications.command("skills-gap")
@click.argument("application_id", type=int)
def applications_skills_gap(application_id):
    """AI skills gap analysis vs job description."""
    error, result = _application_svc.skills_gap(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@applications.command("stats")
def applications_stats():
    """Application funnel statistics."""
    stats = _application_svc.get_stats()
    console.print(f"\n[bold]Application Stats[/bold]  (total: {stats['total']})\n")
    for status, count in sorted(stats["by_status"].items()):
        console.print(f"  {status:<20} {count}")


# ─── interview ────────────────────────────────────────────────────────────────

@cli.group()
def interview():
    """Interview preparation tools."""


@interview.command("prep")
@click.argument("application_id", type=int)
def interview_prep(application_id):
    """Generate interview questions and model STAR answers."""
    error, result = _interview_svc.prep(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("research")
@click.argument("application_id", type=int)
def interview_research(application_id):
    """Generate company research briefing."""
    error, result = _interview_svc.research(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("star")
@click.argument("application_id", type=int)
def interview_star(application_id):
    """Generate STAR method answer scaffolds."""
    error, result = _interview_svc.star(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("questions")
@click.argument("application_id", type=int)
def interview_questions(application_id):
    """Generate smart questions to ask the interviewer."""
    error, result = _interview_svc.questions_to_ask(application_id)
    if error:
        console.print(f"[red]{error}[/red]")
        raise SystemExit(1)
    console.print(Markdown(result))


@interview.command("view")
@click.argument("application_id", type=int)
def interview_view(application_id):
    """Show all saved prep for an application."""
    prep = _interview_svc.get_prep(application_id)
    if not prep:
        console.print("[dim]No prep saved yet. Run `interview prep <id>` first.[/dim]")
        return
    if prep.get("questions"):
        console.print(Panel("\n".join(prep["questions"]), title="Questions & Answers"))
    if prep.get("star_answers"):
        console.print(Panel("\n".join(prep["star_answers"]), title="STAR Answers"))
    if prep.get("company_research"):
        console.print(Panel(prep["company_research"], title="Company Research"))
    if prep.get("questions_to_ask"):
        console.print(Panel("\n".join(prep["questions_to_ask"]), title="Questions to Ask"))


# ─── conversations ────────────────────────────────────────────────────────────

@cli.group()
def conversations():
    """Log and view LinkedIn message threads with contacts."""


@conversations.command("log")
@click.argument("contact_id", type=int)
@click.option("--from", "sender", required=True, type=click.Choice(["me", "them"]), help="Who sent this message")
@click.option("--text", "-t", required=True, help="Message text")
@click.option("--at", "timestamp", default="", help="Timestamp (ISO format, defaults to now)")
def conversations_log(contact_id, sender, text, timestamp):
    """Log a message in a contact's conversation thread."""
    try:
        _conversation_svc.log(contact_id, sender=sender, text=text, timestamp=timestamp)
        console.print(f"[green]Logged message from {sender}.[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


@conversations.command("view")
@click.argument("contact_id", type=int)
def conversations_view(contact_id):
    """View conversation thread with a contact."""
    thread = _conversation_svc.get_thread(contact_id)
    if not thread:
        console.print("[dim]No messages logged yet.[/dim]")
        return
    console.print(f"\n[bold]Conversation thread — Contact #{contact_id}[/bold]\n")
    for msg in thread.get("messages") or []:
        prefix = "[bold cyan][Me][/bold cyan]" if msg["sender"] == "me" else "[bold yellow][Them][/bold yellow]"
        ts = (msg.get("timestamp") or "")[:16]
        console.print(f"  {prefix}  ({ts})  {msg['text']}")


@conversations.command("export")
@click.argument("contact_id", type=int)
def conversations_export(contact_id):
    """Export conversation thread as plain text."""
    text = _conversation_svc.export(contact_id)
    if not text:
        console.print("[dim]No messages logged.[/dim]")
        return
    console.print(text)


# ─── calendar ─────────────────────────────────────────────────────────────────

@cli.group()
def calendar():
    """Content calendar — schedule and track LinkedIn posts."""


@calendar.command("add")
@click.option("--title", "-t", required=True, help="Post title or topic")
@click.option("--date", "-d", required=True, help="Scheduled date (YYYY-MM-DD)")
@click.option("--draft-id", type=int, default=None, help="Link to a saved draft ID")
@click.option("--platform", default="linkedin", help="Platform (default: linkedin)")
def calendar_add(title, date, draft_id, platform):
    """Add a post to the content calendar."""
    post = _calendar_svc.add(title=title, scheduled_date=date, draft_id=draft_id, platform=platform)
    console.print(f"[green]Scheduled post #{post['id']}:[/green] {title} on {date}")


@calendar.command("list")
@click.option("--week", is_flag=True, help="Show upcoming 7 days only")
@click.option("--month", is_flag=True, help="Show upcoming 30 days only")
def calendar_list(week, month):
    """List content calendar."""
    if week:
        posts = _calendar_svc.list_upcoming(days=7)
    elif month:
        posts = _calendar_svc.list_upcoming(days=30)
    else:
        posts = _calendar_svc.list_all()
    if not posts:
        console.print("[dim]No posts scheduled.[/dim]")
        return
    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Date", style="cyan")
    table.add_column("Title", style="white")
    table.add_column("Status", style="yellow")
    table.add_column("Draft", style="dim")
    for p in posts:
        table.add_row(
            str(p["id"]),
            p.get("scheduled_date", ""),
            p.get("title", ""),
            p.get("status", ""),
            str(p.get("draft_id") or "—"),
        )
    console.print(table)


@calendar.command("mark-posted")
@click.argument("post_id", type=int)
@click.option("--date", default="", help="Actual posted date (YYYY-MM-DD, defaults to today)")
def calendar_mark_posted(post_id, date):
    """Mark a scheduled post as posted."""
    post = _calendar_svc.mark_posted(post_id, posted_date=date)
    if not post:
        console.print(f"[red]Post #{post_id} not found.[/red]")
        raise SystemExit(1)
    console.print(f"[green]Marked #{post_id} as posted.[/green]")


@calendar.command("stats")
def calendar_stats():
    """Content calendar statistics."""
    stats = _calendar_svc.get_stats()
    console.print(f"\n[bold]Content Calendar Stats[/bold]")
    console.print(f"  Total:     {stats['total']}")
    console.print(f"  Scheduled: {stats['scheduled']}")
    console.print(f"  Posted:    {stats['posted']}")
    console.print(f"  Skipped:   {stats['skipped']}")
```

**Step 4: Run CLI tests**

```bash
uv run pytest tests/test_cli_applications.py -v
```
Expected: all 9 tests pass.

**Step 5: Run full suite to catch regressions**

```bash
uv run pytest tests/ -q
```
Expected: all tests pass.

**Step 6: Commit**

```bash
git add src/linkedin/cli.py tests/test_cli_applications.py
git commit -m "feat: add applications, interview, conversations, calendar CLI command groups"
```

---

### Task 6: LinkedIn Playwright Scraping

**Files:**
- Create: `src/linkedin/automation/actions/scrape.py`
- Modify: `src/linkedin/automation/linkedin_page.py`
- Create: `tests/test_automation_scrape.py`

**Step 1: Extend `src/linkedin/automation/linkedin_page.py`**

Add these methods to `LinkedInPage` (after `get_search_results` or at end of class):

```python
def get_search_results(self) -> list[dict[str, str]]:
    """Parse people search result cards. Returns list of {name, headline, url}."""
    results = []
    try:
        cards = self.page.locator("li.reusable-search__result-container").all()
        for card in cards:
            name_el = card.locator("span.entity-result__title-text a span[aria-hidden='true']")
            headline_el = card.locator(".entity-result__primary-subtitle")
            link_el = card.locator("a.app-aware-link").first
            name = name_el.inner_text().strip() if name_el.count() else ""
            headline = headline_el.inner_text().strip() if headline_el.count() else ""
            url = link_el.get_attribute("href") or "" if link_el.count() else ""
            # Clean up tracking params
            if url and "?" in url:
                url = url.split("?")[0]
            if name:
                results.append({"name": name, "headline": headline, "linkedin_url": url})
    except Exception:
        pass
    return results

def scrape_profile(self) -> dict[str, str]:
    """Scrape basic profile info from the current profile page.

    Call goto_profile(url) first.
    Returns dict with name, headline, location, about.
    """
    data: dict[str, str] = {}
    try:
        name_el = self.page.locator("h1.text-heading-xlarge")
        if name_el.count():
            data["name"] = name_el.inner_text().strip()

        headline_el = self.page.locator(".text-body-medium.break-words")
        if headline_el.count():
            data["headline"] = headline_el.first.inner_text().strip()

        location_el = self.page.locator(".text-body-small.inline.t-black--light.break-words")
        if location_el.count():
            data["location"] = location_el.first.inner_text().strip()

        about_el = self.page.locator("#about ~ div .visually-hidden")
        if about_el.count():
            data["about"] = about_el.inner_text().strip()
    except Exception:
        pass
    return data
```

**Step 2: Create `src/linkedin/automation/actions/scrape.py`**

```python
"""Scraping actions — import contacts from LinkedIn search results."""

from linkedin.automation.linkedin_page import LinkedInPage
from linkedin.automation.rate_limiter import RateLimiter
from linkedin.automation.safety import SafetyLimits
from linkedin.data.repository import ContactRepo
from linkedin.types import ContactDict


def search_and_collect(
    linkedin: LinkedInPage,
    query: str,
    limit: int = 20,
    rate_limiter: RateLimiter | None = None,
    safety: SafetyLimits | None = None,
) -> list[dict[str, str]]:
    """Run a LinkedIn people search and return raw result dicts.

    Returns list of {name, headline, linkedin_url}.
    Does NOT write to any repo — call import_search_results to persist.
    """
    if safety and not safety.can_search():
        return []

    if rate_limiter:
        rate_limiter.wait()

    linkedin.goto_search(query)

    if safety:
        safety.record_search()

    results = linkedin.get_search_results()
    return results[:limit]


def import_search_results(
    results: list[dict[str, str]],
    contact_repo: ContactRepo,
    skip_existing_urls: bool = True,
) -> tuple[list[ContactDict], list[str]]:
    """Persist search results into the contact repo.

    Returns (added_contacts, skipped_urls).
    Skips contacts whose linkedin_url already exists in repo if skip_existing_urls=True.
    """
    from datetime import datetime

    existing_urls = set()
    if skip_existing_urls:
        existing_urls = {c.get("linkedin_url", "") for c in contact_repo.list_all()}

    added: list[ContactDict] = []
    skipped: list[str] = []

    for result in results:
        url = result.get("linkedin_url", "")
        if skip_existing_urls and url and url in existing_urls:
            skipped.append(url)
            continue

        # Parse title and company from headline "Title at Company"
        headline = result.get("headline", "")
        title, company = _parse_headline(headline)

        contact: ContactDict = {
            "id": contact_repo.next_id(),
            "name": result.get("name", "Unknown"),
            "title": title,
            "company": company,
            "linkedin_url": url,
            "notes": f"Imported from search. Headline: {headline}",
            "status": "not_contacted",
            "source": "linkedin_search",
            "created_at": datetime.now().isoformat(),
            "activities": [],
        }
        contact_repo.add(contact)
        added.append(contact)

    return added, skipped


def scrape_and_import_profile(
    linkedin: LinkedInPage,
    url: str,
    contact_repo: ContactRepo,
    rate_limiter: RateLimiter | None = None,
) -> ContactDict | None:
    """Scrape a single LinkedIn profile and add/update in contact repo.

    Returns the created/updated ContactDict, or None on failure.
    """
    from datetime import datetime

    if rate_limiter:
        rate_limiter.wait()

    try:
        linkedin.goto_profile(url)
        data = linkedin.scrape_profile()
    except Exception:
        return None

    if not data.get("name"):
        return None

    # Check if already exists
    existing = next(
        (c for c in contact_repo.list_all() if c.get("linkedin_url") == url),
        None,
    )

    title, company = _parse_headline(data.get("headline", ""))

    if existing:
        existing["title"] = title or existing.get("title", "")
        existing["company"] = company or existing.get("company", "")
        contact_repo.update(existing)
        return existing

    contact: ContactDict = {
        "id": contact_repo.next_id(),
        "name": data["name"],
        "title": title,
        "company": company,
        "linkedin_url": url,
        "notes": data.get("about", ""),
        "status": "not_contacted",
        "source": "linkedin_scrape",
        "created_at": datetime.now().isoformat(),
        "activities": [],
    }
    contact_repo.add(contact)
    return contact


def _parse_headline(headline: str) -> tuple[str, str]:
    """Parse 'Title at Company' into (title, company). Best-effort."""
    if " at " in headline:
        parts = headline.split(" at ", 1)
        return parts[0].strip(), parts[1].strip()
    if " @ " in headline:
        parts = headline.split(" @ ", 1)
        return parts[0].strip(), parts[1].strip()
    return headline.strip(), ""
```

**Step 3: Write `tests/test_automation_scrape.py`**

```python
"""Tests for LinkedIn scraping actions."""

import pytest
from unittest.mock import MagicMock, patch
import linkedin.data.json_store as js
from linkedin.data.json_store import JsonContactRepo, JsonCompanyRepo
from linkedin.automation.actions.scrape import (
    import_search_results,
    scrape_and_import_profile,
    search_and_collect,
    _parse_headline,
)


@pytest.fixture
def contact_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(js, "DATA_DIR", tmp_path)
    monkeypatch.setattr(js, "CONTACTS_FILE", tmp_path / "contacts.json")
    monkeypatch.setattr(js, "COMPANIES_FILE", tmp_path / "companies.json")
    return JsonContactRepo()


def test_parse_headline_at():
    title, company = _parse_headline("ML Engineer at Stripe")
    assert title == "ML Engineer"
    assert company == "Stripe"


def test_parse_headline_at_symbol():
    title, company = _parse_headline("Data Scientist @ Google")
    assert title == "Data Scientist"
    assert company == "Google"


def test_parse_headline_no_separator():
    title, company = _parse_headline("Freelance Developer")
    assert title == "Freelance Developer"
    assert company == ""


def test_import_search_results(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob Jones", "headline": "Data Engineer at Google", "linkedin_url": "https://linkedin.com/in/bob"},
    ]
    added, skipped = import_search_results(results, contact_repo)
    assert len(added) == 2
    assert len(skipped) == 0
    contacts = contact_repo.list_all()
    assert len(contacts) == 2
    assert contacts[0]["name"] == "Alice Smith"
    assert contacts[0]["company"] == "Stripe"
    assert contacts[0]["source"] == "linkedin_search"


def test_import_search_results_skips_duplicates(contact_repo):
    results = [
        {"name": "Alice Smith", "headline": "ML Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
    ]
    import_search_results(results, contact_repo)
    added, skipped = import_search_results(results, contact_repo)
    assert len(added) == 0
    assert len(skipped) == 1
    assert len(contact_repo.list_all()) == 1  # No duplicates


def test_import_search_results_no_skip(contact_repo):
    results = [{"name": "Alice", "headline": "Engineer at Acme", "linkedin_url": "https://linkedin.com/in/alice"}]
    import_search_results(results, contact_repo)
    # Import again without skip
    added, skipped = import_search_results(results, contact_repo, skip_existing_urls=False)
    assert len(added) == 1
    assert len(contact_repo.list_all()) == 2


def test_search_and_collect_calls_linkedin_page():
    mock_page = MagicMock()
    mock_page.get_search_results.return_value = [
        {"name": "Alice", "headline": "Engineer at Stripe", "linkedin_url": "https://linkedin.com/in/alice"},
        {"name": "Bob", "headline": "PM at Meta", "linkedin_url": "https://linkedin.com/in/bob"},
    ]
    results = search_and_collect(mock_page, "ML Engineer", limit=1)
    assert len(results) == 1
    mock_page.goto_search.assert_called_once_with("ML Engineer")


def test_scrape_and_import_profile_creates_contact(contact_repo):
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {
        "name": "Jane Doe",
        "headline": "Senior ML Engineer at OpenAI",
        "location": "San Francisco, CA",
        "about": "Building AI systems.",
    }
    url = "https://linkedin.com/in/janedoe"
    contact = scrape_and_import_profile(mock_page, url, contact_repo)
    assert contact is not None
    assert contact["name"] == "Jane Doe"
    assert contact["title"] == "Senior ML Engineer"
    assert contact["company"] == "OpenAI"
    assert contact["source"] == "linkedin_scrape"


def test_scrape_and_import_profile_updates_existing(contact_repo):
    # Pre-add the contact
    contact_repo.add({
        "id": 1,
        "name": "Jane Doe",
        "title": "ML Engineer",
        "company": "Old Co",
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "status": "connected",
        "activities": [],
    })
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {
        "name": "Jane Doe",
        "headline": "Senior ML Engineer at OpenAI",
    }
    contact = scrape_and_import_profile(mock_page, "https://linkedin.com/in/janedoe", contact_repo)
    assert contact is not None
    assert contact["company"] == "OpenAI"
    assert len(contact_repo.list_all()) == 1  # Not duplicated


def test_scrape_returns_none_on_empty_name(contact_repo):
    mock_page = MagicMock()
    mock_page.scrape_profile.return_value = {}  # No name
    contact = scrape_and_import_profile(mock_page, "https://linkedin.com/in/nobody", contact_repo)
    assert contact is None
```

**Step 4: Run scraping tests**

```bash
uv run pytest tests/test_automation_scrape.py -v
```
Expected: all 9 tests pass.

**Step 5: Add `automate` CLI sub-commands to cli.py**

Find the existing `automate` group in cli.py (it likely has `status`, `schedule`, `env`, `doctor`, `unschedule`). Add these sub-commands to it:

```python
@automate.command("search")
@click.option("--query", "-q", required=True, help="LinkedIn people search query")
@click.option("--limit", default=20, help="Max results (default: 20)")
def automate_search(query, limit):
    """Search LinkedIn and print results table (no import)."""
    try:
        from linkedin.automation.browser import BrowserManager
        from linkedin.automation.linkedin_page import LinkedInPage
        from linkedin.automation.actions.scrape import search_and_collect
    except ImportError:
        console.print("[red]Playwright not installed. Run: uv sync --extra automation[/red]")
        raise SystemExit(1)

    with BrowserManager() as browser:
        page = LinkedInPage(browser.page)
        if not page.is_logged_in():
            console.print("[yellow]Not logged in. Run: linkedin-cli automate login[/yellow]")
            raise SystemExit(1)
        results = search_and_collect(page, query, limit=limit)

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(title=f"Search: {query}")
    table.add_column("Name", style="cyan")
    table.add_column("Headline", style="white")
    table.add_column("URL", style="dim")
    for r in results:
        table.add_row(r.get("name", ""), r.get("headline", "")[:60], r.get("linkedin_url", "")[:50])
    console.print(table)


@automate.command("import-search")
@click.option("--query", "-q", required=True, help="LinkedIn people search query")
@click.option("--limit", default=20, help="Max results to import (default: 20)")
def automate_import_search(query, limit):
    """Search LinkedIn and import results into contacts CRM."""
    try:
        from linkedin.automation.browser import BrowserManager
        from linkedin.automation.linkedin_page import LinkedInPage
        from linkedin.automation.actions.scrape import import_search_results, search_and_collect
    except ImportError:
        console.print("[red]Playwright not installed. Run: uv sync --extra automation[/red]")
        raise SystemExit(1)

    with BrowserManager() as browser:
        page = LinkedInPage(browser.page)
        if not page.is_logged_in():
            console.print("[yellow]Not logged in. Run: linkedin-cli automate login[/yellow]")
            raise SystemExit(1)
        results = search_and_collect(page, query, limit=limit)

    added, skipped = import_search_results(results, _contact_repo)
    console.print(f"[green]Imported {len(added)} new contacts.[/green] Skipped {len(skipped)} duplicates.")
    for c in added:
        console.print(f"  #{c['id']} {c['name']} — {c.get('title', '')} at {c.get('company', '')}")


@automate.command("profile")
@click.argument("linkedin_url")
def automate_profile(linkedin_url):
    """Scrape a LinkedIn profile and add/update in CRM."""
    try:
        from linkedin.automation.browser import BrowserManager
        from linkedin.automation.linkedin_page import LinkedInPage
        from linkedin.automation.actions.scrape import scrape_and_import_profile
    except ImportError:
        console.print("[red]Playwright not installed. Run: uv sync --extra automation[/red]")
        raise SystemExit(1)

    with BrowserManager() as browser:
        page = LinkedInPage(browser.page)
        if not page.is_logged_in():
            console.print("[yellow]Not logged in. Run: linkedin-cli automate login[/yellow]")
            raise SystemExit(1)
        contact = scrape_and_import_profile(page, linkedin_url, _contact_repo)

    if not contact:
        console.print("[red]Could not scrape profile. Check URL and login status.[/red]")
        raise SystemExit(1)
    console.print(f"[green]{'Updated' if contact.get('status') else 'Added'}:[/green] {contact['name']} — {contact.get('title', '')} at {contact.get('company', '')}")
```

**Step 6: Run full test suite**

```bash
uv run pytest tests/ -q
```
Expected: all tests pass.

**Step 7: Commit**

```bash
git add src/linkedin/automation/actions/scrape.py src/linkedin/automation/linkedin_page.py src/linkedin/cli.py tests/test_automation_scrape.py
git commit -m "feat: add LinkedIn Playwright scraping — search-and-import, single profile scrape"
```

---

### Task 7: Profile Resume Extension + README Update

**Files:**
- Modify: `src/linkedin/types.py`
- Modify: `src/linkedin/cli.py` (profile setup command)
- Modify: `README.md`

**Step 1: Add `resume_text` to ProfileDict in `types.py`**

In the `ProfileDict` class, add:
```python
resume_text: str
```

**Step 2: Extend `profile setup` CLI command**

Find the `profile_setup` command in cli.py. It uses `click.prompt` for each field. Add a `resume_text` prompt at the end, and a `--resume-file` option:

```python
@profile.command("setup")
@click.option("--resume-file", "-r", default="", help="Load resume text from a file")
def profile_setup(resume_file):
    """Set up your profile for AI personalization."""
    existing = _profile_svc.get_profile() or {}

    # ... existing prompts for name, headline, etc. ...

    # Resume — at the end of prompts
    current_resume = existing.get("resume_text", "")
    if resume_file:
        try:
            resume_text = open(resume_file).read()
            console.print(f"[green]Loaded resume from {resume_file}[/green]")
        except OSError as e:
            console.print(f"[yellow]Warning: could not read {resume_file}: {e}[/yellow]")
            resume_text = current_resume
    else:
        has_resume = bool(current_resume)
        update_resume = click.confirm(
            f"{'Update' if has_resume else 'Add'} resume text? "
            f"{'(currently set, press N to keep)' if has_resume else '(used for AI resume tailoring)'}",
            default=not has_resume,
        )
        if update_resume:
            console.print("[dim]Paste your resume text (or a summary). Press Enter twice when done.[/dim]")
            lines = []
            while True:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            resume_text = "\n".join(lines[:-1])  # drop trailing blank
        else:
            resume_text = current_resume

    profile["resume_text"] = resume_text
    _profile_svc.save_profile(profile)
```

Note: The exact implementation depends on how profile_setup currently collects prompts. Read the current profile_setup implementation and add resume_text as a new field using the same `click.prompt` style as other fields.

**Step 3: Update README.md**

Add sections for new commands after existing command sections:

```markdown
### Job Applications
\`\`\`bash
linkedin-cli applications add --company "Acme" --title "ML Engineer" --url "https://..." --jd "Job description text"
linkedin-cli applications list [--status phone_screen] [--company "Acme"]
linkedin-cli applications view 1
linkedin-cli applications advance 1 --status applied --notes "Submitted via website"
linkedin-cli applications tailor-resume 1 [--resume-file resume.txt]
linkedin-cli applications cover-letter 1
linkedin-cli applications skills-gap 1
linkedin-cli applications stats
\`\`\`

### Interview Prep
\`\`\`bash
linkedin-cli interview prep 1          # Generate questions + STAR answers
linkedin-cli interview research 1      # Company briefing
linkedin-cli interview star 1          # STAR method scaffolds
linkedin-cli interview questions 1     # What to ask the interviewer
linkedin-cli interview view 1          # Show all saved prep
\`\`\`

### Conversation History
\`\`\`bash
linkedin-cli conversations log 1 --from me --text "Hi there, wanted to connect..."
linkedin-cli conversations log 1 --from them --text "Sure, happy to chat!"
linkedin-cli conversations view 1
linkedin-cli conversations export 1
\`\`\`

### Content Calendar
\`\`\`bash
linkedin-cli calendar add --title "AI post" --date 2026-03-01 [--draft-id 3]
linkedin-cli calendar list [--week] [--month]
linkedin-cli calendar mark-posted 1 [--date 2026-03-02]
linkedin-cli calendar stats
\`\`\`

### LinkedIn Auto-Import (requires `uv sync --extra automation`)
\`\`\`bash
linkedin-cli automate search --query "ML Engineer at Stripe" --limit 20     # Preview results
linkedin-cli automate import-search --query "ML Engineer at Stripe" --limit 20  # Import to CRM
linkedin-cli automate profile https://linkedin.com/in/username                   # Import single profile
\`\`\`
```

**Step 4: Run full test suite one final time**

```bash
uv run pytest tests/ -q --tb=short
```
Expected: all tests pass.

**Step 5: Final commit**

```bash
git add src/linkedin/types.py src/linkedin/cli.py README.md
git commit -m "feat: add resume_text to profile, update README with all v2.1 commands"
```

---

## Final Validation

After all waves complete, run:

```bash
# Full test suite
uv run pytest tests/ -v --tb=short

# Coverage report
uv run pytest --cov=linkedin --cov-report=term-missing

# Lint
uv run ruff check src/ tests/

# Smoke test key commands (no API key needed)
uv run linkedin applications list
uv run linkedin calendar list
uv run linkedin conversations view 1
uv run linkedin interview view 1
uv run linkedin applications stats
```

Expected: >90% coverage on new services, all linting passing, all smoke commands exit 0.
