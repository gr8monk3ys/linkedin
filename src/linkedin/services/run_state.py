"""Durable state for `run-daily`: run log, lock file, idempotency, notifications.

Extracted from cli.py. Everything here is about whether a run may start and what
it leaves behind, independent of how the run is rendered.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import linkedin.data.json_store as json_store


def load_run_state() -> dict:
    raw = json_store.load_json(
        json_store.RUN_DAILY_STATE_FILE,
        {"completed_idempotency_keys": [], "alerts": {}},
    )
    if not isinstance(raw, dict):
        return {"completed_idempotency_keys": [], "alerts": {}}

    completed_raw = raw.get("completed_idempotency_keys", [])
    if not isinstance(completed_raw, list):
        completed_raw = []

    completed: list[dict] = []
    for item in completed_raw:
        if isinstance(item, str):
            completed.append({"key": item, "completed_at": ""})
            continue
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            completed.append({
                "key": key,
                "completed_at": str(item.get("completed_at", "")),
                "run_id": str(item.get("run_id", "")),
            })

    alerts_raw = raw.get("alerts", {})
    if not isinstance(alerts_raw, dict):
        alerts_raw = {}

    last_failure_streak_notified = alerts_raw.get("last_failure_streak_notified", 0)
    try:
        last_failure_streak_notified = int(last_failure_streak_notified)
    except (TypeError, ValueError):
        last_failure_streak_notified = 0

    return {
        "completed_idempotency_keys": completed[-1000:],
        "alerts": {
            "last_failure_streak_notified": max(0, last_failure_streak_notified),
        },
    }


def save_run_state(state: dict) -> None:
    json_store.save_json(json_store.RUN_DAILY_STATE_FILE, state)


def failure_streak(entries: list[dict]) -> int:
    streak = 0
    for entry in reversed(entries):
        status = str(entry.get("status", ""))
        if status == "failed":
            streak += 1
            continue
        if status == "success":
            break
    return streak


def get_last_failure_streak_notified() -> int:
    state = load_run_state()
    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict):
        return 0
    try:
        return max(0, int(alerts.get("last_failure_streak_notified", 0)))
    except (TypeError, ValueError):
        return 0


def set_last_failure_streak_notified(streak: int) -> None:
    streak = max(0, int(streak))
    state = load_run_state()
    alerts = state.get("alerts", {})
    if not isinstance(alerts, dict):
        alerts = {}
    if alerts.get("last_failure_streak_notified") == streak:
        # Every successful run clears this, and it is already 0 on almost all of
        # them. Skipping the no-op saves a full rewrite + fsync of the state file.
        return
    alerts["last_failure_streak_notified"] = streak
    state["alerts"] = alerts
    save_run_state(state)


def idempotency_key_seen(key: str) -> bool:
    if not key:
        return False
    state = load_run_state()
    completed = state.get("completed_idempotency_keys", [])
    return any(item.get("key") == key for item in completed if isinstance(item, dict))


def record_idempotency_key(key: str, run_id: str) -> None:
    if not key:
        return
    state = load_run_state()
    completed = state.get("completed_idempotency_keys", [])
    if not isinstance(completed, list):
        completed = []
    completed.append({
        "key": key,
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id,
    })
    state["completed_idempotency_keys"] = completed[-1000:]
    save_run_state(state)


def append_run_log(entry: dict) -> None:
    json_store.ensure_dirs()
    path = json_store.RUN_DAILY_LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str) + "\n")


def load_run_history_entries() -> list[dict]:
    path = json_store.RUN_DAILY_LOG_FILE
    if not path.exists():
        return []

    entries: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            entries.append(raw)
    return entries


def entry_timestamp(entry: dict) -> datetime | None:
    return parse_iso_datetime(str(entry.get("finished_at") or entry.get("started_at") or ""))


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def health_lock_check(lock_ttl_minutes: int) -> dict:
    lock_path = json_store.RUN_DAILY_LOCK_FILE
    if not lock_path.exists():
        return {"status": "ok", "detail": "No active run lock."}

    now = datetime.now()
    max_age = timedelta(minutes=max(1, lock_ttl_minutes))
    pid = ""
    created_at = ""
    try:
        payload = json.loads(lock_path.read_text())
        if isinstance(payload, dict):
            pid = str(payload.get("pid", ""))
            created_at = str(payload.get("created_at", ""))
    except Exception:
        pass

    created = parse_iso_datetime(created_at)
    if created is None:
        created = datetime.fromtimestamp(lock_path.stat().st_mtime)

    age_seconds = max(0, int((now - created).total_seconds()))
    if now - created > max_age:
        return {
            "status": "warn",
            "detail": f"Stale lock detected (age={age_seconds}s).",
        }

    pid_part = f"pid={pid}, " if pid else ""
    return {
        "status": "warn",
        "detail": f"Active lock ({pid_part}age={age_seconds}s).",
    }


def acquire_run_lock(lock_ttl_minutes: int = 180) -> tuple[bool, str]:
    json_store.ensure_dirs()
    lock_path = json_store.RUN_DAILY_LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    max_age = timedelta(minutes=max(1, lock_ttl_minutes))

    if lock_path.exists():
        stale = False
        holder_info = "unknown process"
        try:
            payload = json.loads(lock_path.read_text())
            if isinstance(payload, dict):
                pid = payload.get("pid")
                created_at = parse_iso_datetime(str(payload.get("created_at", "")))
                if pid:
                    holder_info = f"pid={pid}"
                if created_at:
                    age = now - created_at
                    if age > max_age:
                        stale = True
                    else:
                        holder_info = f"{holder_info}, age={int(age.total_seconds())}s"
        except Exception:
            pass

        if not stale:
            try:
                age = now - datetime.fromtimestamp(lock_path.stat().st_mtime)
                if age > max_age:
                    stale = True
            except OSError:
                pass

        if stale:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                return False, "Failed to clear stale lock file."
        else:
            return False, f"Another run is in progress ({holder_info})."

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, "Another run is already in progress."

    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "pid": os.getpid(),
            "created_at": now.isoformat(timespec="seconds"),
        }))
    return True, ""


def release_run_lock() -> None:
    try:
        json_store.RUN_DAILY_LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def effective_idempotency_key(
    key: str,
    watch_mode: bool,
    schedule_time: str,
    run_at: datetime,
) -> str:
    trimmed = key.strip()
    day_key = run_at.date().isoformat()
    if trimmed:
        if watch_mode:
            return f"{trimmed}:{day_key}"
        return trimmed
    if watch_mode:
        return f"schedule:{schedule_time}:{day_key}"
    return ""


def send_run_notification(webhook_url: str, payload: dict) -> str | None:
    if not webhook_url:
        return None

    body = {
        "text": (
            f"linkedin-cli run-daily {payload.get('status', 'unknown')} "
            f"(run_id={payload.get('run_id', '-')}, trigger={payload.get('trigger', '-')})"
        ),
        "payload": payload,
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.URLError as exc:
        return str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return str(exc)
    return None
