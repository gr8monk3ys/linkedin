"""Budget: one table of caps, today's usage, persisted per day."""

import json
from datetime import date

import pytest

from linkedin.automation.budget import DEFAULT_CAPS, KINDS, Budget, UnknownKind, load_caps
from linkedin.data.paths import DataDir


def test_defaults_are_the_ramp():
    """Caps an account with no automated history should start at."""
    b = Budget.in_memory()
    assert b.caps["connection"] == 0
    assert b.caps["post"] == 1
    assert b.caps["reaction"] == 5
    assert set(b.caps) == set(KINDS)


def test_spend_and_remaining():
    b = Budget.in_memory({"reaction": 3})
    assert b.can("reaction") and b.remaining("reaction") == 3
    b.spend("reaction", 2)
    assert b.remaining("reaction") == 1
    assert b.can("reaction") and not b.can("reaction", 2)
    b.spend("reaction")
    assert not b.can("reaction")
    assert b.remaining("reaction") == 0


def test_unknown_kind_is_an_error_not_a_zero_budget():
    b = Budget.in_memory()
    with pytest.raises(UnknownKind):
        b.can("likes")
    with pytest.raises(UnknownKind):
        Budget.in_memory({"likes": 5})


def test_in_memory_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("LINKEDIN_DATA_DIR", str(tmp_path))
    Budget.in_memory().spend("search")
    assert list(tmp_path.iterdir()) == []


def test_load_seeds_limits_and_persists_usage_per_day(tmp_path):
    d = DataDir(tmp_path)
    b = Budget.load(d)
    assert json.loads(d.limits.read_text()) == DEFAULT_CAPS
    b.spend("search", 2)
    assert json.loads(d.automation_usage.read_text()) == {
        date.today().isoformat(): {**{k: 0 for k in KINDS}, "search": 2}
    }
    assert Budget.load(d).used["search"] == 2


def test_other_days_are_ignored(tmp_path):
    d = DataDir(tmp_path)
    d.automation_usage.write_text(json.dumps({"2000-01-01": {"search": 99}}))
    assert Budget.load(d).used["search"] == 0


def test_legacy_counter_names_carry_over(tmp_path):
    """The previous usage file used `connections_sent` etc.; today's counts must not reset on upgrade."""
    d = DataDir(tmp_path)
    d.automation_usage.write_text(
        json.dumps({date.today().isoformat(): {"connections_sent": 3, "easy_applies": 1, "searches": 13}})
    )
    b = Budget.load(d)
    assert b.used["connection"] == 3 and b.used["easy_apply"] == 1 and b.used["search"] == 13


def test_corrupt_usage_file_is_ignored(tmp_path):
    d = DataDir(tmp_path)
    d.automation_usage.write_text("{not json")
    assert Budget.load(d).used["search"] == 0


def test_set_cap_writes_limits(tmp_path):
    d = DataDir(tmp_path)
    b = Budget.load(d)
    b.set_cap("reaction", 10)
    assert load_caps(d.limits)["reaction"] == 10
    assert Budget.load(d).caps["reaction"] == 10


def test_load_caps_ignores_junk_but_keeps_known(tmp_path):
    d = DataDir(tmp_path)
    d.limits.write_text(json.dumps({"reaction": 7, "bogus": 1, "post": -1, "search": "x"}))
    caps = load_caps(d.limits)
    assert caps["reaction"] == 7
    assert caps["post"] == DEFAULT_CAPS["post"]
    assert caps["search"] == DEFAULT_CAPS["search"]
    assert "bogus" not in caps


def test_summary_derives_from_the_table():
    b = Budget.in_memory({"post": 1})
    b.spend("post")
    assert b.summary()["post"] == {"cap": 1, "used": 1, "remaining": 0}
    assert set(b.summary()) == set(KINDS)
