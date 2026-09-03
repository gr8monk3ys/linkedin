"""Per-installation choices that are not secrets and not caps: `settings.json` in the data dir.

The one setting today is whether the tool may call the model at all. The user
chose to run without an API key and to have drafts written by hand (Claude
through the browser), so "AI disabled" is a state the doctor reports as fine,
the daily run skips drafting under, and the drafter refuses under — instead of
a missing key that every check nags about and every run fails on.
"""

from __future__ import annotations

from linkedin.data.json_store import load_json, save_json
from linkedin.data.paths import DataDir

DEFAULTS = {"ai_enabled": True}


def load_settings(data_dir: DataDir | None = None) -> dict:
    data_dir = data_dir or DataDir.from_env()
    raw = load_json(data_dir.settings, None)
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out.update({k: v for k, v in raw.items() if k in DEFAULTS})
    return out


def set_setting(key: str, value, data_dir: DataDir | None = None) -> dict:
    if key not in DEFAULTS:
        raise KeyError(key)
    data_dir = data_dir or DataDir.from_env()
    current = load_settings(data_dir)
    current[key] = value
    save_json(data_dir.settings, current)
    return current


def ai_enabled(data_dir: DataDir | None = None) -> bool:
    return bool(load_settings(data_dir)["ai_enabled"])
