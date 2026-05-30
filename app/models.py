from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class StoryRequest(BaseModel):
    topics: list[str] = Field(default_factory=lambda: ["tech", "finance", "crypto", "geopolitics"])
    max_stories: int = 5
    publish_to_youtube: bool = False
    title_suffix: str = "Daily News Brief"


class StoryItem(BaseModel):
    title: str
    summary: str
    topic: str
    source_name: str = ""
    source_url: HttpUrl | None = None
    reference_urls: list[HttpUrl] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)
    memory_key: str = ""
    memory_status: Literal["new", "updated", "related"] = "new"
    memory_note: str = ""
    previous_coverage_title: str | None = None
    previous_coverage_date: str | None = None
    related_coverage_notes: list[str] = Field(default_factory=list)
    target_seconds: int = 0
    importance_score: float = 0.0
    narration_script: str = ""
    audio_path: str = ""


class PipelineResult(BaseModel):
    title: str
    narration: str
    closing_line: str
    stories: list[StoryItem]
    audio_path: str
    video_path: str
    total_duration_seconds: int | None = None
    thumbnail_path: str | None = None
    youtube_video_id: str | None = None
    youtube_url: str | None = None


class JobStatus(BaseModel):
    id: str
    state: JobState
    message: str = ""
    progress: int = 0
    result: PipelineResult | None = None
    error: str | None = None


class PipelineContext(BaseModel):
    job_id: str
    output_dir: Path


class StoryMemoryEntry(BaseModel):
    story_key: str
    content_hash: str
    title: str
    summary: str
    topic: str
    source_name: str = ""
    source_url: str | None = None
    covered_at: str
    updated_at: str
    reference_urls: list[str] = Field(default_factory=list)


class StoryMemoryState(BaseModel):
    entries: list[StoryMemoryEntry] = Field(default_factory=list)
