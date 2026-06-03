from __future__ import annotations

import logging
import secrets
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import get_settings
from app.job_store import job_store
from app.models import StoryRequest
from app.pipeline import run_pipeline
from app.services.tls_guard import validate_google_tls_configuration

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# Suppress per-request access logs (polling endpoints can break in-place progress bars).
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

settings = get_settings()
app = FastAPI(title=settings.app_name, debug=settings.debug)
project_root = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(project_root / "static")), name="static")
templates = Jinja2Templates(directory=str(project_root / "templates"))
logger = logging.getLogger("daily_nexus_update")
TLS_WARNINGS = validate_google_tls_configuration(settings)
for warning in TLS_WARNINGS:
    logger.warning("TLS compatibility warning: %s", warning)


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "settings": settings,
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    payload: dict[str, str] = {"status": "ok"}
    if TLS_WARNINGS:
        payload["tls"] = "warning"
    return payload


@app.post("/api/jobs")
def create_job(payload: StoryRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    job_id = secrets.token_hex(8)
    job_store.create(job_id)

    def _runner(progress_callback):
        return run_pipeline(
            request=payload,
            output_dir=settings.output_dir,
            settings=settings,
            progress_callback=progress_callback,
        )

    background_tasks.add_task(
        job_store.run_background,
        job_id,
        _runner,
    )
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    status = job_store.get(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status.model_dump(mode="json")
