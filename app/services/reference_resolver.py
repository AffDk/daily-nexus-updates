from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.models import StoryItem


def _is_safe_reference(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_reference_resources(story: StoryItem, timeout: float = 12.0) -> StoryItem:
    resolved_urls: list[str] = []
    headers = {"User-Agent": "Mozilla/5.0 (DailyNexusUpdate/1.0)"}
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        for raw_url in list(story.reference_urls)[:3]:
            candidate = str(raw_url)
            if not _is_safe_reference(candidate):
                continue
            try:
                response = client.head(candidate)
                if response.status_code >= 400:
                    response = client.get(candidate)
                if response.status_code < 400:
                    resolved_urls.append(str(response.url))
            except httpx.HTTPError:
                continue

    story.reference_urls = resolved_urls or list(story.reference_urls)
    return story
