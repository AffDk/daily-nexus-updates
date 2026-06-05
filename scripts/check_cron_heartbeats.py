from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.services.notifier import send_failure_email

HEARTBEAT_DIR = Path("/var/lib/daily_nexus_update/heartbeats")
ALERTS_SENT_DIR = HEARTBEAT_DIR / "alerts_sent"


def _last_date(path: Path) -> datetime.date | None:
    if not path.exists():
        return None
    local_now = datetime.now().astimezone()
    return datetime.fromtimestamp(path.stat().st_mtime, tz=local_now.tzinfo).date()


def _send_once(settings, now: datetime, key: str, message: str, error: str) -> None:
    ALERTS_SENT_DIR.mkdir(parents=True, exist_ok=True)
    marker = ALERTS_SENT_DIR / f"{key}.sent"
    if marker.exists():
        return

    send_failure_email(
        settings=settings,
        job_id=key,
        message=message,
        error=error,
    )
    marker.touch()


def main() -> None:
    settings = get_settings()
    now = datetime.now().astimezone()
    today = now.date()

    pipeline_start = _last_date(HEARTBEAT_DIR / "pipeline.last_start")
    pipeline_success = _last_date(HEARTBEAT_DIR / "pipeline.last_success")
    cleanup_start = _last_date(HEARTBEAT_DIR / "cleanup.last_start")
    cleanup_success = _last_date(HEARTBEAT_DIR / "cleanup.last_success")

    is_mwf = now.weekday() in {0, 2, 4}
    is_sunday = now.weekday() == 6

    if is_mwf and now.hour >= 10 and pipeline_start != today:
        _send_once(
            settings,
            now,
            key=f"pipeline-missed-start-{today.isoformat()}",
            message="Scheduled pipeline run did not start",
            error="No pipeline.last_start heartbeat found for today",
        )

    if is_mwf and now.hour >= 12 and pipeline_success != today:
        _send_once(
            settings,
            now,
            key=f"pipeline-missed-success-{today.isoformat()}",
            message="Scheduled pipeline did not complete successfully",
            error="No pipeline.last_success heartbeat found for today",
        )

    if is_sunday and now.hour >= 5 and cleanup_start != today:
        _send_once(
            settings,
            now,
            key=f"cleanup-missed-start-{today.isoformat()}",
            message="Scheduled cleanup run did not start",
            error="No cleanup.last_start heartbeat found for today",
        )

    if is_sunday and now.hour >= 7 and cleanup_success != today:
        _send_once(
            settings,
            now,
            key=f"cleanup-missed-success-{today.isoformat()}",
            message="Scheduled cleanup did not complete successfully",
            error="No cleanup.last_success heartbeat found for today",
        )


if __name__ == "__main__":
    main()
