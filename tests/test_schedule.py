from launchd_audit import schedule


class TestHumanInterval:
    def test_minutes(self):
        assert schedule.human_interval(900) == "every 15 minutes"

    def test_hours(self):
        assert schedule.human_interval(7200) == "every 2 hours"

    def test_days(self):
        assert schedule.human_interval(86400) == "every 1 day"

    def test_odd_seconds(self):
        assert schedule.human_interval(45) == "every 45 seconds"

    def test_interval_seconds_bad(self):
        assert schedule.interval_seconds("nope") is None
        assert schedule.interval_seconds(-5) is None


class TestCalendarInterval:
    def test_daily(self):
        human, cad = schedule.human_calendar_interval({"Hour": 3})
        assert human == "daily at 03:00"
        assert cad == 86400

    def test_weekly(self):
        # launchd Weekday: 0=Sunday, 1=Monday
        human, cad = schedule.human_calendar_interval({"Weekday": 1, "Hour": 9, "Minute": 30})
        assert human == "weekly on Monday at 09:30"
        assert cad == 604800

    def test_sunday_zero(self):
        human, _ = schedule.human_calendar_interval({"Weekday": 0, "Hour": 8})
        assert human == "weekly on Sunday at 08:00"

    def test_sunday_seven(self):
        human, _ = schedule.human_calendar_interval({"Weekday": 7, "Hour": 8})
        assert human == "weekly on Sunday at 08:00"

    def test_monthly(self):
        human, _ = schedule.human_calendar_interval({"Day": 1, "Hour": 0, "Minute": 15})
        assert human == "monthly on day 1 at 00:15"

    def test_hourly(self):
        human, cad = schedule.human_calendar_interval({"Minute": 5})
        assert human == "hourly at :05"
        assert cad == 3600

    def test_list_form(self):
        human, _ = schedule.human_calendar_interval([{"Hour": 3}, {"Hour": 15}])
        assert human == "daily at 03:00; daily at 15:00"


class TestCronHuman:
    def test_every_minute(self):
        assert schedule.cron_human("* * * * *")[0] == "every minute"

    def test_daily(self):
        human, cad = schedule.cron_human("0 3 * * *")
        assert human == "daily at 03:00"
        assert cad == 86400

    def test_step(self):
        human, cad = schedule.cron_human("*/5 * * * *")
        assert human == "every 5 minutes"
        assert cad == 300

    def test_weekly(self):
        human, _ = schedule.cron_human("15 2 * * 1")
        assert human == "weekly (weekday 1) at 02:15"

    def test_fallback(self):
        human, cad = schedule.cron_human("1,2 3-5 * * *")
        assert human == "1,2 3-5 * * *"  # falls back to raw spec
        assert cad is None

    def test_garbage(self):
        human, cad = schedule.cron_human("not a cron")
        assert cad is None
