import plistlib

from launchd_audit import discovery


def write_plist(path, data):
    with open(path, "wb") as fh:
        plistlib.dump(data, fh)


class TestParsePlist:
    def test_masks_environment_and_humanises_schedule(self, tmp_path):
        p = tmp_path / "com.test.backup.plist"
        write_plist(p, {
            "Label": "com.test.backup",
            "ProgramArguments": ["/usr/local/bin/backup", "--full"],
            "StartCalendarInterval": {"Hour": 3, "Minute": 0},
            "EnvironmentVariables": {"API_TOKEN": "hunter2"},
            "StandardOutPath": "~/Library/Logs/backup.out",
        })
        job = discovery.parse_plist(str(p), "launchd-user", [])
        assert job.id == "com.test.backup"
        assert job.program == "/usr/local/bin/backup --full"
        assert job.schedule_human == "daily at 03:00"
        assert job.cadence_seconds == 86400
        assert job.raw["EnvironmentVariables"] == {"API_TOKEN": "***"}
        assert "hunter2" not in repr(job)
        assert job.output_paths and job.output_paths[0].endswith("Library/Logs/backup.out")

    def test_program_arguments_are_redacted(self, tmp_path):
        p = tmp_path / "com.test.sync.plist"
        write_plist(p, {
            "Label": "com.test.sync",
            "ProgramArguments": ["/usr/local/bin/sync", "--api-key", "sk-live-123", "--dest=s3://b"],
        })
        job = discovery.parse_plist(str(p), "launchd-user", [])
        assert "sk-live-123" not in repr(job)
        assert job.program == "/usr/local/bin/sync --api-key *** --dest=s3://b"
        assert job.raw["ProgramArguments"][2] == "***"

    def test_brew_user_agent_is_brew_service(self, tmp_path):
        p = tmp_path / "homebrew.mxcl.redis.plist"
        write_plist(p, {"Label": "homebrew.mxcl.redis", "KeepAlive": True})
        job = discovery.parse_plist(str(p), "launchd-user", [])
        assert job.source == "brew-service"
        assert job.schedule_human == "keep alive (respawn)"

    def test_brew_daemon_stays_system(self, tmp_path):
        """`sudo brew services` installs to /Library/LaunchDaemons; it must keep the
        launchd-system source so the read-only guard applies."""
        p = tmp_path / "homebrew.mxcl.postgresql.plist"
        write_plist(p, {"Label": "homebrew.mxcl.postgresql", "KeepAlive": True})
        job = discovery.parse_plist(str(p), "launchd-system", [])
        assert job.source == "launchd-system"

    def test_unparseable_plist_is_reported_not_raised(self, tmp_path):
        p = tmp_path / "broken.plist"
        p.write_text("not a plist")
        errors: list[dict] = []
        assert discovery.parse_plist(str(p), "launchd-user", errors) is None
        assert errors and "plist parse failed" in errors[0]["reason"]


class TestCronLine:
    def test_user_crontab_line(self):
        job = discovery._cron_line_job("0 3 * * * /usr/local/bin/backup.sh --full", "crontab", 4, False, [])
        assert job.id == "cron:crontab:4"
        assert job.raw == {"spec": "0 3 * * *", "command": "/usr/local/bin/backup.sh --full", "user": None}
        assert job.schedule_human == "daily at 03:00"

    def test_system_crontab_has_user_field(self):
        job = discovery._cron_line_job("*/5 * * * * root /bin/ping", "/etc/crontab", 1, True, [])
        assert job.raw["user"] == "root"
        assert job.program == "/bin/ping"

    def test_short_line_is_an_error(self):
        errors: list[dict] = []
        assert discovery._cron_line_job("MAILTO=x", "crontab", 1, False, errors) is None
        assert errors
