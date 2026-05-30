from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import Settings

logger = logging.getLogger("daily_nexus_update.notifier")


def send_failure_email(settings: Settings, job_id: str, message: str, error: str) -> None:
    if not settings.failure_email_enabled:
        return

    required = [settings.failure_email_to, settings.failure_email_from, settings.smtp_host]
    if not all(value.strip() for value in required):
        logger.warning(
            "Failure email enabled but required SMTP/email fields are missing (FAILURE_EMAIL_TO, FAILURE_EMAIL_FROM, SMTP_HOST)."
        )
        return

    email = EmailMessage()
    email["From"] = settings.failure_email_from
    email["To"] = settings.failure_email_to
    email["Subject"] = f"{settings.failure_email_subject_prefix} Job failed ({job_id})"
    email.set_content(
        "Daily Nexus Update job failed after retries.\n\n"
        f"Job ID: {job_id}\n"
        f"Message: {message}\n"
        f"Error: {error}\n"
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(email)
