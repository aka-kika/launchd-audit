from launchd_audit import runtime
from launchd_audit.model import Job


def job(**kw) -> Job:
    d = dict(id="com.test.job", source="launchd-user", path="/x.plist")
    d.update(kw)
    return Job(**d)


class TestMergeRuntime:
    def test_running_pid(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: {"pid": "4242", "state": "running", "runs": "7"})
        j = job()
        runtime.merge_runtime(j)
        assert j.state == "running" and j.running_pid == 4242 and j.runs == 7

    def test_waiting_with_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: {"state": "waiting", "last exit code": "1"})
        j = job()
        runtime.merge_runtime(j)
        assert j.state == "idle" and j.last_exit == 1

    def test_never_ran(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: {"state": "waiting", "last exit code": "(never exited)"})
        j = job()
        runtime.merge_runtime(j)
        assert j.last_exit is None

    def test_not_loaded(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: {})
        j = job()
        runtime.merge_runtime(j)
        assert j.state == "not-loaded"

    def test_disabled_override_wins(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: {"state": "waiting"})
        j = job()
        runtime.merge_runtime(j, {"com.test.job": True})
        assert j.disabled and j.state == "disabled"

    def test_cron_has_no_live_state(self, monkeypatch):
        monkeypatch.setattr(runtime, "launchctl_print", lambda label: (_ for _ in ()).throw(AssertionError("must not call launchctl")))
        j = job(source="cron")
        runtime.merge_runtime(j)
        assert j.state == "scheduled"
