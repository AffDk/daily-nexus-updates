from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import StoryItem, StoryMemoryEntry, StoryMemoryState


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _story_key(story: StoryItem) -> str:
    parts = [story.topic, story.source_name, story.title]
    if story.source_url:
        parts.append(str(story.source_url))
    normalized = " | ".join(_normalize_text(part) for part in parts if part)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _content_hash(story: StoryItem) -> str:
    parts = [story.title, story.summary, story.topic, story.source_name, str(story.source_url or "")]
    normalized = " | ".join(_normalize_text(part) for part in parts if part)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class StoryMemoryStore:
    def __init__(self, file_path: Path, archive_file_path: Path, retention_days: int = 90) -> None:
        self.file_path = file_path
        self.archive_file_path = archive_file_path
        self.retention_days = retention_days

    def load(self) -> StoryMemoryState:
        return self._load_state(self.file_path)

    def load_archive(self) -> StoryMemoryState:
        return self._load_state(self.archive_file_path)

    def _load_state(self, file_path: Path) -> StoryMemoryState:
        if not file_path.exists():
            return StoryMemoryState()

        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return StoryMemoryState.model_validate(payload)

    def save(self, state: StoryMemoryState) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    def save_archive(self, state: StoryMemoryState) -> None:
        self.archive_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.archive_file_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    def _timestamp(self, entry: StoryMemoryEntry) -> datetime:
        value = entry.updated_at or entry.covered_at
        return datetime.fromisoformat(value)

    def _compact_entry(self, entry: StoryMemoryEntry) -> StoryMemoryEntry:
        summary = entry.summary.strip()
        if len(summary) > 240:
            summary = summary[:240].rstrip() + "..."
        return entry.model_copy(update={"summary": summary, "reference_urls": []})

    def _upsert_compact(self, archive_state: StoryMemoryState, entry: StoryMemoryEntry) -> None:
        compact = self._compact_entry(entry)
        for index, existing in enumerate(archive_state.entries):
            if existing.story_key == compact.story_key:
                if self._timestamp(existing) <= self._timestamp(compact):
                    archive_state.entries[index] = compact
                return
        archive_state.entries.append(compact)

    def _prune_active(self, active_state: StoryMemoryState, archive_state: StoryMemoryState) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        keep_entries: list[StoryMemoryEntry] = []
        for entry in active_state.entries:
            if self._timestamp(entry) < cutoff:
                self._upsert_compact(archive_state, entry)
            else:
                keep_entries.append(entry)
        active_state.entries = keep_entries

    def recent_context(self, limit: int = 12) -> list[StoryMemoryEntry]:
        state = self.load()
        return sorted(state.entries, key=lambda entry: entry.updated_at, reverse=True)[:limit]

    def _latest_for_key(self, entries: Iterable[StoryMemoryEntry], story_key: str) -> StoryMemoryEntry | None:
        matching = [entry for entry in entries if entry.story_key == story_key]
        return max(matching, key=lambda entry: entry.updated_at, default=None)

    def _related_entries(self, entries: Iterable[StoryMemoryEntry], story: StoryItem, limit: int = 2) -> list[StoryMemoryEntry]:
        topic_entries = [entry for entry in entries if entry.topic == story.topic]
        topic_entries.sort(key=lambda entry: entry.updated_at, reverse=True)
        return topic_entries[:limit]

    def classify_story(self, story: StoryItem) -> tuple[StoryItem, bool]:
        state = self.load()
        archive_state = self.load_archive()
        all_entries = [*state.entries, *archive_state.entries]
        story_key = _story_key(story)
        current_hash = _content_hash(story)
        previous = self._latest_for_key(all_entries, story_key)
        related_entries = self._related_entries(all_entries, story)

        story.memory_key = story_key
        story.related_coverage_notes = []

        if previous and previous.content_hash == current_hash:
            story.memory_status = "related"
            story.memory_note = f"Already covered on {previous.covered_at}"
            story.previous_coverage_title = previous.title
            story.previous_coverage_date = previous.covered_at
            story.related_coverage_notes = [
                f"Previously covered: {previous.title} ({previous.covered_at})",
            ]
            return story, False

        if previous:
            story.memory_status = "updated"
            story.memory_note = f"Updated since {previous.covered_at}"
            story.previous_coverage_title = previous.title
            story.previous_coverage_date = previous.covered_at
            story.related_coverage_notes = [
                f"Earlier coverage: {previous.title} ({previous.covered_at})",
            ]
            return story, True

        story.memory_status = "new"
        if related_entries:
            story.related_coverage_notes = [
                f"Related to previous coverage: {entry.title} ({entry.covered_at})"
                for entry in related_entries
            ]
            story.memory_note = story.related_coverage_notes[0]
            story.memory_status = "related"
        return story, True

    def record(self, stories: Iterable[StoryItem]) -> None:
        state = self.load()
        archive_state = self.load_archive()
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        lookup = {entry.story_key: entry for entry in state.entries}

        for story in stories:
            story_key = story.memory_key or _story_key(story)
            current = lookup.get(story_key)
            reference_urls = [str(url) for url in story.reference_urls]
            if current:
                current.title = story.title
                current.summary = story.summary
                current.topic = story.topic
                current.source_name = story.source_name
                current.source_url = str(story.source_url) if story.source_url else None
                current.content_hash = _content_hash(story)
                current.updated_at = now
                current.reference_urls = reference_urls
                continue

            entry = StoryMemoryEntry(
                story_key=story_key,
                content_hash=_content_hash(story),
                title=story.title,
                summary=story.summary,
                topic=story.topic,
                source_name=story.source_name,
                source_url=str(story.source_url) if story.source_url else None,
                covered_at=now,
                updated_at=now,
                reference_urls=reference_urls,
            )
            state.entries.append(entry)
            lookup[story_key] = entry

        self._prune_active(state, archive_state)
        self.save(state)
        self.save_archive(archive_state)

    def memory_context_text(self, limit: int = 12) -> str:
        entries = self.recent_context(limit=limit)
        if not entries:
            return "No prior coverage stored yet."

        lines = ["Recent coverage memory:"]
        for entry in entries:
            lines.append(
                f"- [{entry.topic}] {entry.title} | covered {entry.covered_at} | source: {entry.source_name or 'unknown'}"
            )
        lines.append("Avoid repeats unless the story has a clear update. If it is related, frame it as a follow-up.")
        return "\n".join(lines)
