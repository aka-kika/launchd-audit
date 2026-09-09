import os

from launchd_audit import actions
from launchd_audit.model import Job


def user_job(**kw) -> Job:
    defaults = dict(
        id="com.test.job",
        source="launchd-user",
        path="/Users/x/Library/LaunchAgents/com.test.job.plist",
        program="/usr/bin/true",
        output_paths=[],
        raw={},
    )
    defaults.update(kw)
    return Job(**defaults)


class TestGuards:
    def test_system_daemon_refused(self):
        job = user_job(source="launchd-system")
        plan = actions.plan_action(job, "disable")
        assert "error" in plan
        assert "read-only" in plan["error"]

    def test_unknown_action_refused(self):
        plan = actions.plan_action(user_job(), "reinstall")
        assert "unknown action" in plan["error"]

    def test_cron_only_supports_remove(self):
        job = user_job(source="cron", path="crontab line 3", raw={"spec": "0 3 * * *", "command": "x"})
        assert "error" in actions.plan_action(job, "disable")
        assert "error" not in actions.plan_action(job, "remove")


class TestPlans:
    def test_disable_plan_is_dry_run(self):
        plan = actions.plan_action(user_job(), "disable")
        assert plan["dry_run"] is True
        assert any("launchctl disable" in c for c in plan["commands"])
        assert plan["undo"]

    def test_remove_plan_moves_to_trash(self):
        plan = actions.plan_action(user_job(), "remove")
        assert any("bootout" in c for c in plan["commands"])
        assert any("Trash" in w for w in plan["warnings"])
        assert plan["undo"]

    def test_truncate_needs_logs(self):
        plan = actions.plan_action(user_job(), "truncate_logs")
        assert "error" in plan  # no output paths declared

    def test_planning_never_mutates(self, tmp_path, monkeypatch):
        """Plan for an action whose apply would touch the FS — plan must not."""
        import subprocess

        def boom(*a, **k):
            raise AssertionError("plan_action must never run subprocesses")

        monkeypatch.setattr(subprocess, "run", boom)
        actions.plan_action(user_job(), "remove")  # raises if planning executes anything


class TestGuardsAgainstSystemPaths:
    def test_brew_daemon_in_launchdaemons_refused(self):
        """A `sudo brew services` plist lives in /Library/LaunchDaemons. Whatever its
        source label, it is a system daemon and must be read-only."""
        job = user_job(
            id="homebrew.mxcl.postgresql",
            source="brew-service",
            path="/Library/LaunchDaemons/homebrew.mxcl.postgresql.plist",
        )
        plan = actions.plan_action(job, "remove")
        assert "error" in plan
        assert "read-only" in plan["error"]

    def test_remove_refused_when_plist_dir_not_writable(self, tmp_path):
        agents = tmp_path / "LaunchAgents"
        agents.mkdir()
        plist = agents / "com.test.job.plist"
        plist.write_text("x")
        agents.chmod(0o555)
        try:
            plan = actions.plan_action(user_job(path=str(plist)), "remove")
        finally:
            agents.chmod(0o755)
        if os.access(str(agents), os.W_OK):  # root ignores mode bits; nothing to assert
            return
        assert "error" in plan
        assert "not writable" in plan["error"]


class TestRemovePlist:
    def test_plan_and_apply_agree_on_trash_path(self, tmp_path, monkeypatch):
        import subprocess

        agents = tmp_path / "LaunchAgents"
        agents.mkdir()
        plist = agents / "com.test.job.plist"
        plist.write_text("x")
        monkeypatch.setattr(actions, "expand", lambda p: str(tmp_path / "Trash") if "Trash" in p else p)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
        monkeypatch.setattr(actions, "_log_action", lambda outcome: None)

        job = user_job(path=str(plist))
        plan = actions.plan_action(job, "remove")
        result = actions.apply_action(job, plan)

        assert result["all_ok"]
        assert not plist.exists()
        assert os.path.exists(plan["trash_path"])
        assert plan["trash_path"] in result["undo"][0]


class TestRemoveCronLine:
    def _fake_crontab(self, monkeypatch, content: str) -> dict:
        import subprocess

        written: dict = {}

        class R:
            def __init__(self, rc=0, out="", err=""):
                self.returncode, self.stdout, self.stderr = rc, out, err

        def run(cmd, **kw):
            if cmd == ["crontab", "-l"]:
                return R(out=content)
            if cmd == ["crontab", "-"]:
                written["text"] = kw["input"]
                return R()
            raise AssertionError(cmd)

        monkeypatch.setattr(subprocess, "run", run)
        return written

    def test_removes_line_despite_extra_whitespace(self, monkeypatch):
        content = "# keep me\n0  3 * * *   /usr/local/bin/backup.sh\n*/5 * * * * /bin/ping\n"
        written = self._fake_crontab(monkeypatch, content)
        job = user_job(source="cron", path="crontab line 2",
                       raw={"spec": "0 3 * * *", "command": "/usr/local/bin/backup.sh"})
        res = actions._remove_cron_line(job)
        assert res["ok"], res
        assert written["text"] == "# keep me\n*/5 * * * * /bin/ping\n"

    def test_no_match_is_reported_and_crontab_untouched(self, monkeypatch):
        written = self._fake_crontab(monkeypatch, "*/5 * * * * /bin/ping\n")
        job = user_job(source="cron", path="crontab line 9",
                       raw={"spec": "0 3 * * *", "command": "/gone"})
        res = actions._remove_cron_line(job)
        assert res["ok"] is False
        assert "text" not in written, "crontab must not be rewritten when nothing matched"
