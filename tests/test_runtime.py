from launchd_audit import runtime
from launchd_audit.model import Job


def job(**kw) -> Job:
    d = dict(id="com.test.job", source="launchd-user", path="/x.plist")
    d.update(kw)
    return Job(**d)


LIST_OUTPUT = "PID\tStatus\tLabel\n-\t0\tcom.test.idle\n4242\t0\tcom.test.running\n-\t78\tcom.test.failed\n-\t-15\tcom.test.killed\n"


class TestLaunchctlList:
    def test_parses_table(self, monkeypatch):
        import subprocess

        class R:
            stdout = LIST_OUTPUT

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
        table = runtime.launchctl_list()
        assert table == {
            "com.test.idle": (None, 0),
            "com.test.running": (4242, 0),
            "com.test.failed": (None, 78),
            "com.test.killed": (None, -15),
        }

    def test_no_launchctl_is_empty(self, monkeypatch):
        import subprocess

        def boom(*a, **k):
            raise FileNotFoundError("launchctl")

        monkeypatch.setattr(subprocess, "run", boom)
        assert runtime.launchctl_list() == {}


class TestMergeRuntime:
    def test_running_pid(self):
        j = job()
        runtime.merge_runtime(j, loaded={"com.test.job": (4242, 0)})
        assert j.state == "running" and j.running_pid == 4242 and j.last_exit == 0

    def test_idle_with_nonzero_exit(self):
        j = job()
        runtime.merge_runtime(j, loaded={"com.test.job": (None, 1)})
        assert j.state == "idle" and j.last_exit == 1

    def test_not_loaded(self):
        j = job()
        runtime.merge_runtime(j, loaded={})
        assert j.state == "not-loaded" and j.last_exit is None

    def test_disabled_override_wins(self):
        j = job()
        runtime.merge_runtime(j, {"com.test.job": True}, loaded={"com.test.job": (None, 0)})
        assert j.disabled and j.state == "disabled"

    def test_table_is_fetched_once_per_call_not_per_job(self, monkeypatch):
        calls = []
        monkeypatch.setattr(runtime, "launchctl_list", lambda: calls.append(1) or {})
        table = runtime.launchctl_list()
        for _ in range(5):
            runtime.merge_runtime(job(), loaded=table)
        assert len(calls) == 1

    def test_cron_has_no_live_state(self, monkeypatch):
        def boom():
            raise AssertionError("must not call launchctl")

        monkeypatch.setattr(runtime, "launchctl_list", boom)
        j = job(source="cron")
        runtime.merge_runtime(j)
        assert j.state == "scheduled"


class TestMergePrintDetails:
    def test_runs_and_never_exited(self):
        j = job(last_exit=0)
        runtime.merge_print_details(j, {"runs": "12", "last exit code": "(never exited)"})
        assert j.runs == 12 and j.last_exit is None

    def test_precise_exit(self):
        j = job()
        runtime.merge_print_details(j, {"last exit code": "78"})
        assert j.last_exit == 78
