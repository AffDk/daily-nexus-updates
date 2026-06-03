from __future__ import annotations

import logging
import time
from datetime import datetime
from collections.abc import Callable
from pathlib import Path

from app.config import Settings, get_settings
from app.models import PipelineResult, StoryItem, StoryRequest
from app.services.elevenlabs_client import generate_voiceover
from app.services.gemini_client import fetch_major_stories, shorten_headline_for_video
from app.services.narration import build_closing_line, build_story_narration_script, build_voiceover_script
from app.services.reference_resolver import resolve_reference_resources
from app.services.screenshotter import capture_screenshot
from app.services.story_memory import StoryMemoryStore
from app.services.video_builder import build_video
from app.services.youtube_uploader import upload_video

logger = logging.getLogger("daily_nexus_update.pipeline")


def _timestamped_run_dir(base_output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    candidate = base_output_dir / stamp
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        fallback = base_output_dir / f"{stamp}_{suffix:02d}"
        if not fallback.exists():
            return fallback
        suffix += 1


def _build_description(stories: list[StoryItem]) -> str:
    lines = ["Daily Nexus Update", "", "Stories covered:"]
    lines.extend(f"- {story.title}" for story in stories)
    return "\n".join(lines)


def _topic_bonus(topic: str) -> float:
    return {
        "geopolitics": 1.2,
        "finance": 1.15,
        "crypto": 1.05,
        "tech": 1.0,
    }.get(topic.lower(), 1.0)


def _status_bonus(status: str) -> float:
    return {
        "updated": 1.35,
        "new": 1.1,
        "related": 0.95,
    }.get(status, 1.0)


def _allocate_story_durations(settings: Settings, stories: list[StoryItem]) -> list[int]:
    if not stories:
        return []

    story_budget = min(
        settings.max_video_seconds - settings.intro_seconds - settings.outro_seconds,
        settings.max_stories * settings.max_story_seconds,
    )
    story_budget = max(story_budget, len(stories) * settings.min_story_seconds)

    weights = [(_status_bonus(story.memory_status) * _topic_bonus(story.topic)) for story in stories]
    weight_total = sum(weights) or float(len(stories))
    durations = []
    for index, story in enumerate(stories):
        share = story_budget * (weights[index] / weight_total)
        duration = int(round(share))
        duration = max(settings.min_story_seconds, min(settings.max_story_seconds, duration))
        durations.append(duration)

    return durations


def _needs_headline_shortening(headline: str) -> bool:
    compact = " ".join(headline.split())
    if len(compact) > 110:
        return True
    if len(compact.split()) > 16:
        return True
    return False


def _is_transient_api_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "503",
        "502",
        "429",
        "unavailable",
        "high demand",
        "too many requests",
        "temporarily",
        "timeout",
        "timed out",
        "connection reset",
        "rate limit",
    )
    return any(marker in text for marker in markers)


def run_pipeline(
    request: StoryRequest,
    output_dir: Path | None = None,
    settings: Settings | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> PipelineResult:
    def _set_progress(progress: int, message: str) -> None:
        logger.info("[pipeline] %s (%s%%)", message, progress)
        if progress_callback:
            progress_callback(progress, message)

    def _call_with_retry(
        provider: str,
        action: str,
        progress: int,
        operation: Callable[[], object],
    ):
        max_attempts = max(1, settings.retry_max_attempts)
        base_delay = max(1, settings.retry_delay_seconds)
        backoff = max(1.0, settings.retry_backoff_multiplier)

        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001 - classified for retries
                transient = _is_transient_api_error(exc)
                is_last = attempt >= max_attempts
                if is_last or not transient:
                    raise RuntimeError(f"{provider} {action} failed after {attempt} attempt(s): {exc}") from exc

                wait_seconds = int(round(base_delay * (backoff ** (attempt - 1))))
                _set_progress(
                    progress,
                    f"{provider} {action} temporary failure. Retry {attempt + 1}/{max_attempts} in {wait_seconds}s",
                )
                logger.warning(
                    "%s %s transient failure on attempt %s/%s: %s. Retrying in %ss",
                    provider,
                    action,
                    attempt,
                    max_attempts,
                    exc,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

    settings = settings or get_settings()
    base_output_dir = output_dir or settings.output_dir
    memory_store = StoryMemoryStore(settings.news_memory_file, settings.news_memory_archive_file)
    job_dir = _timestamped_run_dir(base_output_dir)
    screenshots_dir = job_dir / "screenshots"

    job_dir.mkdir(parents=True, exist_ok=True)

    _set_progress(10, "Collecting stories from Gemini")
    memory_context = memory_store.memory_context_text()
    candidate_stories = _call_with_retry(
        provider="Gemini",
        action="fetch",
        progress=10,
        operation=lambda: fetch_major_stories(settings, request, memory_context),
    )

    _set_progress(25, "Filtering repeated stories and collecting references")
    resolved_stories: list[StoryItem] = []
    for story in candidate_stories:
        classified_story, keep_story = memory_store.classify_story(story)
        if not keep_story:
            continue
        resolved = resolve_reference_resources(classified_story)
        if resolved.reference_urls:
            resolved.screenshot_paths = []
            for index, url in enumerate(resolved.reference_urls, start=1):
                try:
                    screenshot = capture_screenshot(
                        str(url),
                        screenshots_dir / resolved.topic,
                        f"{resolved.topic}_{index}_{resolved.title}",
                        query_hint=f"{resolved.title} {resolved.topic} news",
                    )
                    resolved.screenshot_paths.append(str(screenshot))
                except Exception as exc:  # noqa: BLE001 - keep story if one source fails
                    logger.warning("Snapshot failed for %s (%s)", url, exc)
        resolved_stories.append(resolved)

    if not resolved_stories:
        raise ValueError("No fresh or updated stories available after memory filtering")

    _set_progress(40, "Allocating segment durations")
    story_durations = _allocate_story_durations(settings, resolved_stories)
    for story, duration_seconds in zip(resolved_stories, story_durations, strict=True):
        story.target_seconds = duration_seconds
        story.importance_score = _status_bonus(story.memory_status) * _topic_bonus(story.topic)

    _set_progress(48, "Optimizing long headlines for on-screen cards")
    for story in resolved_stories:
        story.display_title = story.title
        if not _needs_headline_shortening(story.title):
            continue
        try:
            story.display_title = _call_with_retry(
                provider="Gemini",
                action=f"headline shorten for '{story.title[:42]}'",
                progress=48,
                operation=lambda story=story: shorten_headline_for_video(
                    settings=settings,
                    headline=story.title,
                    topic=story.topic,
                    summary=story.summary,
                    max_chars=95,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - keep pipeline running with original title
            logger.warning("Headline shortening failed for %s (%s)", story.title, exc)
            story.display_title = story.title

    memory_store.record(resolved_stories)

    title = f"Daily Nexus Update | {request.title_suffix}"
    closing_line = build_closing_line(resolved_stories)

    _set_progress(55, "Generating narration scripts")
    narration_segments: list[str] = []
    for story in resolved_stories:
        story.narration_script = _call_with_retry(
            provider="Gemini",
            action=f"narration for '{story.title}'",
            progress=55,
            operation=lambda story=story: build_story_narration_script(
                settings,
                story,
                memory_store.memory_context_text(),
                story.target_seconds,
            ),
        )
        narration_segments.append(story.narration_script)

    narration = build_voiceover_script(resolved_stories, title, closing_line)
    story_audio_dir = job_dir / "audio" / "stories"
    outro_audio_dir = job_dir / "audio" / "outro"
    intro_audio_dir = job_dir / "audio" / "intro"
    intro_audio: Path | None = None
    outro_audio: Path | None = None
    result_audio_path = ""

    if settings.enable_voiceover:
        _set_progress(68, "Generating ElevenLabs intro audio")
        topics_label = ", ".join(dict.fromkeys(s.topic for s in resolved_stories))
        intro_text = (
            f"Hello and welcome to {title}. "
            f"Today's briefing covers {len(resolved_stories)} stories across {topics_label}. "
            "Let's get into it."
        )
        try:
            intro_audio = _call_with_retry(
                provider="ElevenLabs",
                action="intro audio",
                progress=68,
                operation=lambda: generate_voiceover(
                    settings, intro_text, intro_audio_dir, intro_audio_dir / "intro.mp3"
                ),
            )
        except Exception as exc:  # noqa: BLE001 - intro greeting is required when voiceover is enabled
            raise RuntimeError(f"ElevenLabs intro greeting audio failed: {exc}") from exc

        _set_progress(70, "Generating ElevenLabs story audio")
        for index, story in enumerate(resolved_stories, start=1):
            audio_path = story_audio_dir / f"story_{index:02d}_{story.topic}.mp3"
            story.audio_path = str(
                _call_with_retry(
                    provider="ElevenLabs",
                    action=f"audio for '{story.title}'",
                    progress=70,
                    operation=lambda story=story, audio_path=audio_path: generate_voiceover(
                        settings,
                        story.narration_script,
                        story_audio_dir,
                        audio_path,
                    ),
                )
            )
            result_audio_path = story.audio_path

        outro_audio = _call_with_retry(
            provider="ElevenLabs",
            action="outro audio",
            progress=70,
            operation=lambda: generate_voiceover(settings, closing_line, outro_audio_dir, outro_audio_dir / "closing.mp3"),
        )
        result_audio_path = str(outro_audio)
    else:
        _set_progress(70, "Voiceover disabled by configuration; rendering silent cut")
        for story in resolved_stories:
            story.audio_path = ""

    total_duration_seconds = settings.intro_seconds + settings.outro_seconds + sum(story.target_seconds for story in resolved_stories)
    if total_duration_seconds > settings.max_video_seconds:
        raise ValueError(
            f"Generated cut would be {total_duration_seconds}s, above max {settings.max_video_seconds}s"
        )

    _set_progress(85, "Rendering final video")
    try:
        video_path = build_video(
            settings,
            title,
            resolved_stories,
            closing_line,
            outro_audio,
            job_dir / "video",
            intro_audio_path=intro_audio,
        )
    except Exception as exc:  # noqa: BLE001 - rewrapped with source context
        raise RuntimeError(f"Video render failed: {exc}") from exc

    youtube_video_id = None
    youtube_url = None
    if request.publish_to_youtube or settings.youtube_upload_enabled:
        _set_progress(95, "Uploading to YouTube")
        try:
            youtube_video_id = upload_video(settings, video_path, title, _build_description(resolved_stories)) or None
        except Exception as exc:  # noqa: BLE001 - rewrapped with source context
            raise RuntimeError(f"YouTube upload failed: {exc}") from exc
        if youtube_video_id:
            youtube_url = f"https://www.youtube.com/watch?v={youtube_video_id}"

    _set_progress(100, "Pipeline completed")

    return PipelineResult(
        title=title,
        narration=narration,
        closing_line=closing_line,
        stories=resolved_stories,
        audio_path=result_audio_path,
        video_path=str(video_path),
        total_duration_seconds=total_duration_seconds,
        youtube_video_id=youtube_video_id,
        youtube_url=youtube_url,
    )
