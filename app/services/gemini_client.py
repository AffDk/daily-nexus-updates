from __future__ import annotations

import json
import re
from typing import Any

from google import genai

from app.config import Settings
from app.models import StoryItem, StoryRequest


def _parse_json_payload(text: str) -> Any:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    return json.loads(cleaned)


def fetch_major_stories(settings: Settings, request: StoryRequest, memory_context: str) -> list[StoryItem]:
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
You are producing a daily news briefing.
Return strict JSON only.

Requirements:
- Topic buckets: {", ".join(request.topics)}
- Story count: {request.max_stories}
- Each story must include: title, summary, topic, source_name, source_url, reference_urls
- Prefer major, timely, factual items with reputable reference URLs.
- Keep URLs publicly accessible and suitable for screenshot capture.
- Do not repeat stories already covered unless there is a clear update.
- When a story is a follow-up, make it a material update and mention the relation in the summary.
- Related topics are allowed if they explain new consequences, reactions, or next steps.

{memory_context}

JSON shape:
{{
  "stories": [
    {{
      "title": "...",
      "summary": "...",
      "topic": "...",
      "source_name": "...",
      "source_url": "https://...",
      "reference_urls": ["https://...", "https://..."]
    }}
  ]
}}
""".strip()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={"temperature": 0.2, "response_mime_type": "application/json"},
    )
    payload = _parse_json_payload(response.text or "{}")
    stories: list[StoryItem] = []
    for raw_story in payload.get("stories", [])[: request.max_stories]:
        stories.append(
            StoryItem(
                title=raw_story["title"],
                summary=raw_story["summary"],
                topic=raw_story.get("topic", "general"),
                source_name=raw_story.get("source_name", ""),
                source_url=raw_story.get("source_url"),
                reference_urls=raw_story.get("reference_urls", []),
            )
        )
    return stories


def shorten_headline_for_video(
    settings: Settings,
    headline: str,
    topic: str,
    summary: str,
    max_chars: int = 95,
) -> str:
    client = genai.Client(api_key=settings.gemini_api_key)
    prompt = f"""
You rewrite news headlines for on-screen video overlays.
Return plain text only (no markdown, no quotes).

Requirements:
- Keep factual meaning unchanged.
- Keep it punchy and clear.
- No clickbait.
- Max length: {max_chars} characters.
- Topic context: {topic}

Original headline: {headline}
Story summary: {summary}
""".strip()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={"temperature": 0.1},
    )

    candidate = (response.text or "").strip().strip('"')
    if not candidate:
        return headline[:max_chars].rstrip()
    if len(candidate) > max_chars:
        return candidate[: max_chars - 1].rstrip() + "…"
    return candidate
