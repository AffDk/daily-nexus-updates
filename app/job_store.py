from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from app.config import get_settings
from app.models import JobState, JobStatus, PipelineResult
from app.services.notifier import send_failure_email

logger = logging.getLogger("daily_nexus_update.jobs")


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str) -> JobStatus:
        with self._lock:
            status = JobStatus(id=job_id, state=JobState.queued, progress=0)
            self._jobs[job_id] = status
            return status

    def get(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> JobStatus:
        with self._lock:
            current = self._jobs[job_id]
            updated = current.model_copy(update=kwargs)
            self._jobs[job_id] = updated
            return updated

    def run_background(
        self,
        job_id: str,
        runner: Callable[[Callable[[int, str], None]], PipelineResult],
    ) -> None:
        def _worker() -> None:
            self.update(job_id, state=JobState.running, message="Pipeline starting", progress=5)

            def _progress(progress: int, message: str) -> None:
                self.update(job_id, progress=progress, message=message)

            try:
                result = runner(_progress)
                self.update(job_id, state=JobState.completed, message="Pipeline finished", progress=100, result=result)
            except Exception as exc:  # noqa: BLE001 - surfaced to API
                logger.exception("Job %s failed", job_id)
                source = str(exc).split(":", 1)[0] if str(exc) else "Unknown error"
                failed = self.update(
                    job_id,
                    state=JobState.failed,
                    message=f"Pipeline failed: {source}",
                    error=str(exc),
                )
                try:
                    send_failure_email(
                        settings=get_settings(),
                        job_id=job_id,
                        message=failed.message,
                        error=failed.error or "",
                    )
                except Exception:  # noqa: BLE001 - notification failures should not crash worker
                    logger.exception("Failed to send failure notification email for job %s", job_id)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


job_store = JobStore()
