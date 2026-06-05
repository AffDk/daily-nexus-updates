from __future__ import annotations

import argparse

from app.config import get_settings
from app.services.notifier import send_failure_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Send cron failure email using app SMTP settings")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--error", default="")
    args = parser.parse_args()

    settings = get_settings()
    send_failure_email(
        settings=settings,
        job_id=args.job_id,
        message=args.message,
        error=args.error,
    )


if __name__ == "__main__":
    main()
