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
