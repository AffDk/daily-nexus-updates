from __future__ import annotations

from google import genai

from app.config import Settings
from app.models import StoryItem


_FORBIDDEN_ENDING_PHRASES = (
    "now let's look at",
    "let's look at the following",
    "coming up",
    "next up",
    "in the next story",
    "we'll cover next",
    "more on that later",
    "to be continued",
)

_LEADING_GREETING_PATTERNS = (
    "good morning",
    "good afternoon",
    "good evening",
    "hello",
    "hi everyone",
    "welcome",
    "welcome back",
)


def _trim_to_word_budget(script: str, max_words: int) -> str:
    words = script.split()
    if len(words) <= max_words:
        return script.strip()

    clipped = " ".join(words[:max_words]).strip()

    # Prefer ending on sentence boundaries when possible.
    for punct in (". ", "! ", "? "):
        idx = clipped.rfind(punct)
        if idx >= max(40, int(len(clipped) * 0.55)):
            return clipped[: idx + 1].strip()

    if clipped.endswith((".", "!", "?")):
        return clipped
    return clipped.rstrip(" ,;:-") + "."


def _strip_leading_greeting(script: str) -> str:
    text = (script or "").strip()
    if not text:
        return text

    normalized = text.lower()
    for phrase in _LEADING_GREETING_PATTERNS:
        if normalized.startswith(phrase):
            # Remove first sentence if it is just a greeting/sign-on line.
            split_idx = text.find(".")
            if split_idx != -1 and split_idx < 160:
                return text[split_idx + 1 :].strip()
            return text[len(phrase) :].lstrip(" ,:-")
    return text


def _ensure_complete_story_ending(script: str, story: StoryItem) -> str:
    text = _strip_leading_greeting(script)
    if not text:
        return text

    normalized = " ".join(text.lower().split())
    has_forbidden_ending = any(phrase in normalized[-180:] for phrase in _FORBIDDEN_ENDING_PHRASES)
    ends_with_terminal_punctuation = text.endswith((".", "!", "?", '"'))

    if has_forbidden_ending:
        text = text.rstrip(" .,:;-")
        text = (
            f"{text}. For now, this is the clearest verified picture of {story.topic}, "
            "and we will track changes as they happen."
        )

    if not ends_with_terminal_punctuation:
        text = text.rstrip(" .,:;-") + "."

    return text


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
    from datetime import datetime

    today_label = datetime.now().strftime("%A, %d %B %Y")
    lines = [
        f"Welcome to {title}.",
        f"Today is {today_label}.",
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


def build_topic_transition_line(previous_topic: str | None, next_topic: str) -> str:
    prev_label = (previous_topic or "").strip().lower()
    next_label = (next_topic or "general").strip().lower()

    topic_bits = {
        "tech": "From microchips to macro consequences, tech never really does quiet mode.",
        "finance": "Time to check the markets, where charts can move faster than coffee cools.",
        "crypto": "Now to crypto, where volatility still treats calm as a temporary bug.",
        "geopolitics": "Next, geopolitics, where every sentence has footnotes and consequences.",
    }

    opener = topic_bits.get(next_label, f"Next, we switch to {next_topic}.")
    if not prev_label:
        return f"First stop: {next_topic}. {opener}"
    return f"Quick pivot from {previous_topic} to {next_topic}. {opener}"


def _fallback_story_script(story: StoryItem, target_seconds: int) -> str:
    target_words = max(40, int(target_seconds * 2.2))
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
    target_words = max(40, int(target_seconds * 2.2))
    prompt = f"""
Write a spoken news segment for a daily news video.

Constraints:
- Length: exactly about {target_words} words — do NOT write more than {int(target_words * 1.05)} words.
- Audience: generally informed viewers who are interested in the topic but not necessarily experts.
- Tone: natural, confident, emotionally aware, conversational, and engaging; not robotic.
- Use plain, clear wording over technical jargon. If a technical term is necessary, briefly explain it in everyday language.
- Keep sentences mostly short to medium length, with a strong flow suitable for spoken narration.
- Avoid overly formal, academic, legalistic, or dense phrasing.
- Keep depth and nuance: do not oversimplify facts, but make them easy to follow on first listen.
- Do NOT open with any greeting, welcome, sign-on, or filler phrase (e.g. "Good morning", "Hello everyone", "Welcome back", "Next up", "Moving on to"). Begin immediately with the story's key fact or headline.
- Do NOT end with any farewell, sign-off, or closing phrase (e.g. "That's all for now", "Thanks for watching", "See you next time", "Stay tuned", "Goodbye", "Until next time"). Those belong only in the show outro.
- End with a complete, self-contained final sentence. Never end with teaser/transition lines like "coming up", "next we'll cover", or "now let's look at the following".
- Use short pauses with ellipses when a beat should land.
- Use only the supplied facts and context.
- If this is an update, explicitly say what changed.
- If this is related to prior coverage, refer back to it as a follow-up.
- You may include a bridge sentence, but it must still sound complete and final by itself.

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

    max_words = max(35, int(target_words * 1.02))
    script = _trim_to_word_budget(script, max_words=max_words)
    return _ensure_complete_story_ending(script, story)
