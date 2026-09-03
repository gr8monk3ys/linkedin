"""The daily run: one interface over the plan, the drafts, and the run lifecycle.

`DailyRun(app, config).execute(trigger, run_at)` is the whole thing — lock
handling excepted, which is the caller's because it brackets watch mode too.
Inside: idempotency, retry with backoff, the failure-streak escalation and its
recovery, the run log, and the classification that decides whether a run was
`success`, `no_actions`, or `failed`. That policy used to be a thousand lines
of private CLI functions with a twenty-argument call repeated four times, and
the only seam tests had was patching those privates.

`DailyPlan` is an ordered list of sections. Two renderers (the terminal's Rich
tables and the Markdown recap) iterate it, so adding a section is one entry
here rather than three functions edited in lockstep.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from linkedin.data.json_store import load_json
from linkedin.services.planner import command_for, label_for
from linkedin.services.run_state import (
    append_run_log,
    effective_idempotency_key,
    failure_streak,
    get_last_failure_streak_notified,
    idempotency_key_seen,
    load_run_history_entries,
    record_idempotency_key,
    send_run_notification,
    set_last_failure_streak_notified,
)

if TYPE_CHECKING:
    from linkedin.app import App


@dataclass(frozen=True)
class RunConfig:
    actions_limit: int = 8
    postings_limit: int = 5
    min_posting_score: int = 40
    save_recap: bool = False
    recap_dir: str = ""
    generate_drafts: bool = False
    save_drafts: bool = False
    schedule_time: str = "09:00"
    idempotency_key: str = ""
    allow_duplicate: bool = False
    notify_webhook: str = ""
    notify_on_success: bool = False
    failure_streak_threshold: int = 3
    notify_on_recovery: bool = True
    retry_attempts: int = 1
    retry_backoff_seconds: float = 5.0


@dataclass
class Section:
    """One block of the plan. `rows` are already strings; renderers only lay them out."""

    key: str
    title: str
    columns: list[str]
    rows: list[list[str]]
    empty: str
    hint: str = ""
    #: An optional section is skipped by the terminal when empty (the recap
    #: always writes it, so a reader can see it was checked).
    optional: bool = False


@dataclass
class DailyPlan:
    generated_at: str
    focus: str
    sections: list[Section]

    def to_markdown(self) -> str:
        lines = ["# Daily Plan", f"- Generated: {self.generated_at}", "", "## Focus", self.focus]
        for section in self.sections:
            lines.extend(["", f"## {section.title}"])
            if not section.rows:
                lines.append(f"- {section.empty}")
                continue
            for row in section.rows:
                lines.append("- " + " | ".join(row))
            if section.hint:
                lines.append(f"- {section.hint}")
        return "\n".join(lines) + "\n"


def build_plan(data: dict) -> DailyPlan:
    """Shape the plan data (the JSON output) into ordered sections."""
    profile = data.get("profile") or {}
    focus = (
        f"- Name: {profile.get('name', 'Not set')}\n- Target Role: {profile.get('target_role', 'Not set')}"
        if profile
        else "- Name: Not set\n- Target Role: Not set"
    )
    sections = [
        Section(
            "actions",
            "Priority Actions",
            ["Priority", "Contact", "Action", "Command"],
            [
                [str(a["priority"]), f"{a.get('name', 'Unknown')} ({a.get('company', '')})".strip(), label_for(a["action"]), command_for(a["action"], a["contact_id"])]
                for a in data.get("actions") or []
            ],
            "No urgent contact actions today.",
        ),
        Section(
            "inbound",
            "Inbound (needs your confirmation)",
            ["Contact", "Transition", "Evidence"],
            [
                [p.get("name", "Unknown"), f"{p.get('from_status', '')} -> {p.get('to_status', '')}" + (" [low confidence]" if p.get("confidence") == "low" else ""), p.get("evidence", "")]
                for p in data.get("inbox_proposals") or []
            ],
            "Nothing new. Run `linkedin-cli inbox sync` to check.",
            hint="Review with: `linkedin-cli inbox review`",
            optional=True,
        ),
        Section(
            "applications",
            "Applications",
            ["Priority", "Role", "Action", "Command"],
            [
                [str(a["priority"]), f"{a.get('title', 'Unknown')} @ {a.get('company', '')}", label_for(a["action"]), command_for(a["action"], a["application_id"])]
                for a in data.get("application_actions") or []
            ],
            "No applications need attention today.",
            optional=True,
        ),
        Section(
            "postings",
            "Best-Match Opportunities",
            ["Score", "Role", "Company", "Why"],
            [
                [str(p.get("match_score", 0)), p.get("title", "Unknown"), p.get("company", "Unknown"), (p.get("match_reasons") or ["-"])[0]]
                for p in data.get("postings") or []
            ],
            "No postings above threshold.",
        ),
        Section(
            "templates",
            "Best Templates",
            ["Type", "Template", "Variant", "Rate", "Uses"],
            [
                [t["type"], f"#{t.get('id')} {t.get('name', '')}", t.get("variant", "A"), t.get("response_rate", "0%"), str(t.get("usage_count", 0))]
                for t in data.get("templates") or []
            ],
            "No template performance data yet.",
        ),
    ]
    return DailyPlan(generated_at=data.get("generated_at", ""), focus=focus, sections=sections)


class DailyRun:
    """Plan, draft, record, classify, retry, notify — behind `execute`."""

    def __init__(
        self,
        app: App,
        config: RunConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
        on_draft: Callable[[dict], None] | None = None,
        on_draft_failure: Callable[[int, str], None] | None = None,
        on_retry: Callable[[int, int, float], None] | None = None,
    ):
        self.app = app
        self.config = config
        self.sleep = sleep
        self.on_draft = on_draft
        self.on_draft_failure = on_draft_failure
        self.on_retry = on_retry

    # -- the plan ---------------------------------------------------------------

    def plan_data(self) -> dict:
        """The plan as data: what `--json` prints and what the sections are built from."""
        app, cfg = self.app, self.config
        recommendations: list[dict] = []
        for template_type in ("connection", "message", "follow_up"):
            best = app.template_svc.suggest_best(template_type)
            if best:
                recommendations.append({"type": template_type, **best})
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "profile": app.profile_svc.get_profile(),
            "actions": app.contact_svc.get_next_actions(limit=cfg.actions_limit, scores=app.ranking_svc.scores()),
            "application_actions": app.application_svc.get_application_actions(limit=cfg.actions_limit),
            "inbox_proposals": load_json(app.data_dir.inbox_proposals, []),
            "postings": app.market_svc.list_postings(limit=cfg.postings_limit, min_score=cfg.min_posting_score),
            "templates": recommendations,
        }

    def draft_for_actions(self, actions: list[dict], *, save: bool) -> dict:
        """Draft for each planned action through the planner's rows.

        A template counts as a failure here, not a draft: this path runs
        unattended, and nobody is at the keyboard to edit a template before it
        is sent. Failing the run is what makes an invalid API key visible.
        """
        generated = saved = failed = templates = 0
        drafts: list[dict] = []
        for action in actions:
            drafted = self.app.draft_svc.generate_for_action(action)
            if drafted is None:
                continue
            draft_type, result = drafted
            if not result.ok:
                failed += 1
                templates += int(result.was_fallback)
                if self.on_draft_failure:
                    what = "only an offline template" if result.was_fallback else "no draft"
                    self.on_draft_failure(action["contact_id"], f"{what} ({result.error or 'no text'})")
                continue
            generated += 1
            entry = {
                "contact_id": action["contact_id"],
                "name": action.get("name", ""),
                "generated_from": action["action"],
                "draft_type": draft_type,
                "content": result.text,
            }
            drafts.append(entry)
            if self.on_draft:
                self.on_draft(entry)
            if save:
                self.app.draft_svc.save_draft(action["contact_id"], draft_type, result.text, source=result.source, generated_from=action["action"])
                saved += 1
        return {"generated": generated, "saved": saved, "failed": failed, "templates": templates, "drafts": drafts}

    def cycle(self) -> dict:
        """One plan, with drafts and recap as configured. No lifecycle."""
        cfg = self.config
        data = self.plan_data()
        if cfg.generate_drafts or cfg.save_drafts:
            data["drafts"] = self.draft_for_actions(data["actions"], save=cfg.save_drafts)
        else:
            data["drafts"] = {"generated": 0, "saved": 0, "failed": 0, "templates": 0, "drafts": []}
        if cfg.save_recap:
            out_dir = Path(cfg.recap_dir) if cfg.recap_dir else self.app.data_dir.recaps
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"daily_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            path.write_text(build_plan(data).to_markdown())
            data["recap_path"] = str(path)
        return data

    # -- classification ---------------------------------------------------------

    def classify(self, data: dict) -> tuple[str, list[dict]]:
        """(status, stalled_contacts) for a completed cycle.

        Planning nothing is only a success when every active contact is
        scheduled for a future date. If a contact is due, overdue, or has no
        follow-up date and the planner still produced nothing, the planner is
        broken: that is how this job logged 136 consecutive green runs while
        generating zero drafts. A run whose drafts came back as templates has
        produced nothing usable either — AI was asked for and was not there.
        """
        if data.get("drafts", {}).get("templates"):
            return "failed", []
        if data.get("actions"):
            return "success", []
        stalled = self.app.contact_svc.stalled_contacts()
        return ("no_actions" if stalled else "success"), stalled

    # -- lifecycle --------------------------------------------------------------

    def execute(self, trigger: str, run_at: datetime, *, watch_mode: bool = False) -> dict:
        """Run with retries. The result carries `attempts` and, on recovery, `recovered_after_retries`."""
        cfg = self.config
        max_attempts = max(1, cfg.retry_attempts + 1)
        result: dict = {}
        for attempt in range(max_attempts):
            last = attempt == max_attempts - 1
            result = self._attempt(trigger, run_at, watch_mode=watch_mode, notify_on_failure=last)
            result["attempts"] = attempt + 1
            if result.get("status") != "failed":
                if attempt > 0:
                    result["recovered_after_retries"] = attempt
                return result
            if last:
                return result
            backoff = max(0.0, cfg.retry_backoff_seconds) * (2**attempt)
            if self.on_retry:
                self.on_retry(attempt + 1, max_attempts, backoff)
            if backoff > 0:
                self.sleep(backoff)
        return result

    def _attempt(self, trigger: str, run_at: datetime, *, watch_mode: bool, notify_on_failure: bool) -> dict:
        """One attempt: idempotency, the cycle, classification, log, streak, notify."""
        cfg, data_dir = self.config, self.app.data_dir
        run_id = uuid.uuid4().hex
        started_at = datetime.now()
        key = effective_idempotency_key(cfg.idempotency_key, watch_mode, cfg.schedule_time, run_at)
        stamp = lambda: datetime.now().isoformat(timespec="seconds")  # noqa: E731

        if key and not cfg.allow_duplicate and idempotency_key_seen(data_dir, key):
            result = {
                "status": "skipped_duplicate", "run_id": run_id, "trigger": trigger, "idempotency_key": key,
                "started_at": started_at.isoformat(timespec="seconds"), "finished_at": stamp(),
                "reason": "Idempotency key already completed.",
            }
            append_run_log(data_dir, result)
            return result

        threshold = max(1, int(cfg.failure_streak_threshold))
        try:
            data = self.cycle()
        except Exception as exc:
            return self._record_failure(run_id, trigger, key, started_at, str(exc), threshold, notify_on_failure)

        prior_streak = failure_streak(load_run_history_entries(data_dir))
        data["status"], stalled = self.classify(data)
        data.update({
            "run_id": run_id, "trigger": trigger, "idempotency_key": key,
            "started_at": started_at.isoformat(timespec="seconds"), "finished_at": stamp(),
        })
        if data["status"] == "no_actions":
            data["stalled_contact_ids"] = [c["id"] for c in stalled]
            data["reason"] = f"{len(stalled)} contact(s) are due or have no follow-up date, but the planner produced no actions."
        elif data["status"] == "failed":
            n = data["drafts"]["templates"]
            data["reason"] = f"AI unavailable: {n} draft(s) came back as offline templates and were not saved."

        log_entry = {
            "status": data["status"], "run_id": run_id, "trigger": trigger, "idempotency_key": key,
            "started_at": data["started_at"], "finished_at": data["finished_at"],
            "actions_count": len(data.get("actions", [])),
            "postings_count": len(data.get("postings", [])),
            "templates_count": len(data.get("templates", [])),
            "drafts_generated": int(data["drafts"].get("generated", 0)),
            "drafts_saved": int(data["drafts"].get("saved", 0)),
            "recap_path": data.get("recap_path", ""),
        }
        append_run_log(data_dir, log_entry)
        if key:
            record_idempotency_key(data_dir, key, run_id)
        if prior_streak > 0:
            data["recovered_from_failure_streak"] = prior_streak
        set_last_failure_streak_notified(data_dir, 0)

        error = None
        if cfg.notify_webhook and threshold > 1 and prior_streak >= threshold and cfg.notify_on_recovery:
            payload = {**log_entry, "status": "recovered_after_failure_streak", "prior_failure_streak": prior_streak, "failure_streak_threshold": threshold}
            error = send_run_notification(cfg.notify_webhook, payload)
        elif cfg.notify_webhook and cfg.notify_on_success:
            error = send_run_notification(cfg.notify_webhook, log_entry)
        if error:
            data["notification_error"] = error
        return data

    def _record_failure(self, run_id, trigger, key, started_at, error, threshold, notify_on_failure) -> dict:
        cfg, data_dir = self.config, self.app.data_dir
        failed = {
            "status": "failed", "run_id": run_id, "trigger": trigger, "idempotency_key": key,
            "started_at": started_at.isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"), "error": error,
        }
        append_run_log(data_dir, failed)
        streak = failure_streak(load_run_history_entries(data_dir))
        failed["failure_streak"] = streak

        notification_error = None
        streak_mode = threshold > 1 and streak >= threshold
        if cfg.notify_webhook and notify_on_failure and streak_mode:
            if streak > get_last_failure_streak_notified(data_dir):
                payload = {**failed, "status": "failed_streak", "failure_streak_threshold": threshold}
                notification_error = send_run_notification(cfg.notify_webhook, payload)
                if not notification_error:
                    set_last_failure_streak_notified(data_dir, streak)
        if not streak_mode and notification_error is None and cfg.notify_webhook and notify_on_failure:
            notification_error = send_run_notification(cfg.notify_webhook, failed)
        if notification_error:
            failed["notification_error"] = notification_error
        return failed
