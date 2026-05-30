from __future__ import annotations

from google import genai

from app.config import Settings
from app.models import StoryItem


def _closing_line(stories: list[StoryItem]) -> str:
    if not stories:
        return "The news cycle clocked out early today. Subscribe so you do not miss tomorrow's update."

    lead = stories[0].topic.lower()
    if lead == "finance":
        joke = "The market moved so fast today, even my coffee needed a limit order."
    elif lead == "crypto":
        joke = "Crypto was swinging like it had a caffeine subscription."
    elif lead == "geopolitics":
        joke = "Diplomacy moved carefully today, which is rare enough to deserve a drumroll."
    else:
        joke = "The headlines were moving so fast, even the refresh button asked for a break."

    return f"{joke} If you want the next roundup, subscribe to Daily Nexus Update."


def build_voiceover_script(stories: list[StoryItem], title: str, closing_line: str) -> str:
    lines = [
        f"Welcome to {title}.",
        "Today’s briefing moves through the stories that matter most, with space between the beats so each update lands clearly.",
    ]

    for story in stories:
        if story.memory_status == "updated" and story.previous_coverage_title:
            lines.append(
                f"Update on our earlier coverage of {story.previous_coverage_title}. {story.title}. {story.summary}"
                " ... That is the part worth watching now."
            )
        elif story.memory_status == "related" and story.related_coverage_notes:
            related_note = story.related_coverage_notes[0]
            lines.append(
                f"Related to earlier coverage: {related_note}. {story.title}. {story.summary}"
                " ... Here is the new angle."
            )
        else:
            lines.append(
                f"{story.title}. {story.summary}"
                " ... We are watching this closely, and we will keep the next update focused on what actually changes."
            )

    lines.append(closing_line)
    return "\n\n".join(lines)


def build_closing_line(stories: list[StoryItem]) -> str:
    return _closing_line(stories)


def _fallback_story_script(story: StoryItem, target_seconds: int) -> str:
    target_words = max(260, min(650, int(target_seconds * 2.15)))
    related_note = story.memory_note or ""
    parts = [
        f"{story.title}. {story.summary}",
        f"What matters most here is the direction of travel. For viewers, the key point is not just the headline, but the second-order effect that follows it.",
        f"This sits inside the broader {story.topic} picture. {related_note}".strip(),
        "The next thing to watch is whether this turns into a one-day reaction or a longer trend with real consequences.",
        f"We will keep this in the loop and move on with the rest of today's cycle, because the story is still developing and the important detail is what changes next.",
    ]
    script = "\n\n".join(part for part in parts if part)
    if len(script.split()) < target_words:
        filler = (
            f"In practical terms, that means more attention on timing, policy, market reaction, and the next official response. "
            f"If new facts change the picture, we will treat it as an update rather than a repeat, and that is exactly how this briefing is structured."
        )
        while len(script.split()) < target_words:
            script = f"{script}\n\n{filler}"
    return script


def build_story_narration_script(settings: Settings, story: StoryItem, memory_context: str, target_seconds: int) -> str:
    if not settings.gemini_api_key:
        return _fallback_story_script(story, target_seconds)

    client = genai.Client(api_key=settings.gemini_api_key)
    target_words = max(260, min(650, int(target_seconds * 2.15)))
    prompt = f"""
Write a spoken news segment for a daily news video.

Constraints:
- Length: about {target_words} words.
- Tone: natural, confident, emotionally aware, not robotic.
- Use short pauses with ellipses when a beat should land.
- Use only the supplied facts and context.
- If this is an update, explicitly say what changed.
- If this is related to prior coverage, refer back to it as a follow-up.
- End with a bridge into the next story.

Story title: {story.title}
Topic: {story.topic}
Source: {story.source_name or 'unknown'}
Summary: {story.summary}
Memory note: {story.memory_note or 'none'}
Related coverage notes: {"; ".join(story.related_coverage_notes) or 'none'}

{memory_context}
""".strip()

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={"temperature": 0.45},
    )
    script = (response.text or "").strip()
    if not script:
        return _fallback_story_script(story, target_seconds)
    if len(script.split()) < target_words:
        script = f"{script}\n\n{_fallback_story_script(story, target_seconds)}"
    return script
