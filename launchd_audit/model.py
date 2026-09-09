from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    """One scheduled thing on the machine: launchd job, cron entry, or brew service."""

    id: str
    source: str  # launchd-user | launchd-system | cron | brew-service
    path: str | None  # plist path, or "(crontab) line N"
    program: str | None = None
    schedule_human: str | None = None
    cadence_seconds: float | None = None
    state: str = "unknown"  # running | idle | disabled | not-loaded | scheduled | unknown
    running_pid: int | None = None
    last_exit: int | None = None
    runs: int | None = None
    disabled: bool = False
    output_paths: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)  # plist contents, EnvironmentVariables masked

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "path": self.path,
            "program": self.program,
            "schedule_human": self.schedule_human,
            "state": self.state,
            "disabled": self.disabled,
            "running_pid": self.running_pid,
            "last_exit": self.last_exit,
            "runs": self.runs,
            "output_paths": self.output_paths,
        }
