"""The doctor knows about the launchd job that actually runs the daily plan on this machine."""

from linkedin.app import App
from linkedin.data.paths import DataDir
from linkedin.services.diagnostics import diagnostics, launchd_job

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
  <key>Label</key><string>com.example.linkedin.run_daily</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>-lc</string>
    <string>cd /x &amp;&amp; uv run linkedin-cli run-daily --save-recap --collect-metrics --retry-attempts 2</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
</dict></plist>
"""


def test_launchd_job_is_read_from_the_plist(tmp_path):
    (tmp_path / "com.example.linkedin.run_daily.plist").write_text(PLIST)
    (tmp_path / "com.example.goodreads.run_daily.plist").write_text(
        PLIST.replace("linkedin", "goodreads").replace("linkedin-cli", "goodreads-cli")
    )
    job = launchd_job(tmp_path)
    assert job["label"] == "com.example.linkedin.run_daily"
    assert job["time"] == "09:00" and job["collect_metrics"] is True


def test_no_launch_agents_dir_is_none(tmp_path):
    assert launchd_job(tmp_path / "missing") is None
    assert launchd_job(tmp_path) is None


def test_doctor_reports_the_launchd_schedule_instead_of_no_schedule(tmp_path):
    (tmp_path / "la").mkdir()
    (tmp_path / "la" / "run_daily.plist").write_text(PLIST)
    app = App(DataDir(tmp_path / "data"))
    checks, facts = diagnostics(app, cron_lines=[], cron_error=None, launch_agents_dir=tmp_path / "la")
    by = {c["name"]: c for c in checks}
    assert by["schedule"]["status"] == "ok" and "09:00" in by["schedule"]["detail"]
    assert by["crontab"]["status"] == "ok" and "launchd" in by["crontab"]["detail"]
    assert facts["launchd_job"]["collect_metrics"] is True


def test_doctor_still_warns_with_neither(tmp_path):
    app = App(DataDir(tmp_path / "data"))
    checks, facts = diagnostics(app, cron_lines=[], cron_error=None, launch_agents_dir=tmp_path / "none")
    by = {c["name"]: c for c in checks}
    assert "schedule" not in by and by["crontab"]["status"] == "warn"
