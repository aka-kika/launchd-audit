import os
import time

from launchd_audit import health
from launchd_audit.model import Job


def make_job(tmp_path, **kw) -> Job:
    defaults = dict(
        id="com.test.job",
        source="launchd-user",
        path=str(tmp_path / "com.test.job.plist"),
        program="/usr/bin/true",
        schedule_human="daily at 03:00",
        cadence_seconds=86400,
        state="idle",
        output_paths=[],
        raw={},
    )
    defaults.update(kw)
    return Job(**defaults)


class TestStale:
    def test_old_logs_flagged_stale(self, tmp_path):
        log = tmp_path / "out.log"
        log.write_text("hi")
        old = time.time() - 10 * 86400
        os.utime(log, (old, old))
        job = make_job(tmp_path, output_paths=[str(log)])
        result = health.audit([job])
        assert len(result["stale"]) == 1
        assert result["stale"][0]["days_since_last_evidence"] >= 9

    def test_fresh_logs_not_stale(self, tmp_path):
        log = tmp_path / "out.log"
        log.write_text("hi")
        job = make_job(tmp_path, output_paths=[str(log)])
        result = health.audit([job])
        assert result["stale"] == []

    def test_fresh_sibling_log_prevents_false_positive(self, tmp_path):
        """The recall.watcher case: stderr declared in plist is ancient (silent
        successes write nothing), but the script's own watcher.log is fresh.
        Must NOT be flagged stale."""
        stderr = tmp_path / "watcher.stderr.log"
        stderr.write_text("old")
        old = time.time() - 40 * 86400
        os.utime(stderr, (old, old))
        sibling = tmp_path / "watcher.log"  # script's own log, fresh
        sibling.write_text("fresh")
        job = make_job(tmp_path, id="com.kikalab.recall.watcher", output_paths=[str(stderr)])
        result = health.audit([job])
        assert result["stale"] == [], "fresh sibling log must rescue the job"

    def test_all_evidence_stale_still_flagged(self, tmp_path):
        stderr = tmp_path / "job.stderr.log"
        stderr.write_text("old")
        sibling = tmp_path / "job.log"
        sibling.write_text("also old")
        old = time.time() - 40 * 86400
        os.utime(stderr, (old, old))
        os.utime(sibling, (old, old))
        job = make_job(tmp_path, output_paths=[str(stderr)])
        result = health.audit([job])
        assert len(result["stale"]) == 1
        assert result["stale"][0]["log_dir_evidence"], "flagged entries must carry evidence"

    def test_dailyreport_report_log_case(self, tmp_path):
        """Job 'com.kikalab.recall.dailyreport' writes to shared 'report.log'."""
        stderr = tmp_path / "dailyreport.stderr.log"
        stderr.write_text("old")
        old = time.time() - 40 * 86400
        os.utime(stderr, (old, old))
        shared = tmp_path / "report.log"  # job stem ENDS WITH 'report'
        shared.write_text("fresh")
        job = make_job(tmp_path, id="com.kikalab.recall.dailyreport", output_paths=[str(stderr)])
        result = health.audit([job])
        assert result["stale"] == []


class TestFailing:
    def test_nonzero_exit_flagged(self, tmp_path):
        job = make_job(tmp_path, last_exit=78, state="idle")
        result = health.audit([job])
        assert len(result["failing"]) == 1
        assert result["failing"][0]["last_exit"] == 78

    def test_zero_exit_ok(self, tmp_path):
        job = make_job(tmp_path, last_exit=0)
        assert health.audit([job])["failing"] == []

    def test_keepalive_not_loaded_flagged(self, tmp_path):
        job = make_job(tmp_path, state="not-loaded", raw={"KeepAlive": True})
        result = health.audit([job])
        assert len(result["failing"]) == 1


class TestLogPressure:
    def test_big_log_flagged(self, tmp_path, monkeypatch):
        log = tmp_path / "huge.log"
        log.write_bytes(b"x" * 2048)
        monkeypatch.setattr(health, "LOG_PRESSURE_BYTES", 1024)
        job = make_job(tmp_path, output_paths=[str(log)])
        result = health.audit([job])
        assert len(result["log_pressure"]) == 1
        assert result["log_pressure"][0]["bytes"] == 2048


class TestNotes:
    def test_duplicate_programs_noted(self, tmp_path):
        jobs = [
            make_job(tmp_path, id="a"),
            make_job(tmp_path, id="b"),
        ]
        result = health.audit(jobs)
        assert any("share the same program" in n for n in result["notes"])
