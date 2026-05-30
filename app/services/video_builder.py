from __future__ import annotations

from pathlib import Path

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips, vfx, afx
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import StoryItem


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if font_path:
        path = Path(font_path)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _create_title_card(settings: Settings, title: str, subtitle: str, output_path: Path) -> Path:
    image = Image.new("RGB", (settings.video_width, settings.video_height), color=(8, 12, 22))
    draw = ImageDraw.Draw(image)
    header_font = _load_font(settings.font_path or None, 72)
    body_font = _load_font(settings.font_path or None, 34)
    draw.rounded_rectangle((80, 80, settings.video_width - 80, settings.video_height - 80), radius=40, fill=(18, 27, 42))
    draw.text((140, 180), title, font=header_font, fill=(245, 245, 245))
    draw.text((140, 310), subtitle, font=body_font, fill=(175, 185, 205), spacing=16)
    image.save(output_path)
    return output_path


def _prepare_story_card(settings: Settings, story: StoryItem, screenshot_path: Path, output_dir: Path) -> Path:
    card_path = output_dir / f"{screenshot_path.stem}_card.png"
    card = Image.open(screenshot_path).convert("RGB").resize((settings.video_width, settings.video_height))
    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    header_font = _load_font(settings.font_path or None, 52)
    body_font = _load_font(settings.font_path or None, 28)
    draw.rectangle((0, 0, settings.video_width, 240), fill=(0, 0, 0, 170))
    draw.text((80, 45), story.title, font=header_font, fill=(255, 255, 255))
    draw.text((80, 125), story.summary[:220], font=body_font, fill=(220, 225, 235), spacing=12)
    composite = Image.alpha_composite(card.convert("RGBA"), overlay)
    composite.convert("RGB").save(card_path)
    return card_path


def _create_outro_card(settings: Settings, title: str, closing_line: str, output_path: Path) -> Path:
    image = Image.new("RGB", (settings.video_width, settings.video_height), color=(5, 9, 16))
    draw = ImageDraw.Draw(image)
    header_font = _load_font(settings.font_path or None, 60)
    body_font = _load_font(settings.font_path or None, 32)
    draw.rounded_rectangle((80, 80, settings.video_width - 80, settings.video_height - 80), radius=40, fill=(17, 26, 41))
    draw.text((140, 170), title, font=header_font, fill=(245, 245, 245))
    draw.multiline_text((140, 310), closing_line, font=body_font, fill=(215, 225, 245), spacing=14)
    image.save(output_path)
    return output_path


def _attach_audio(clip: ImageClip, audio_path: Path, fade_seconds: float) -> ImageClip:
    audio = AudioFileClip(str(audio_path)).with_effects([afx.AudioFadeIn(fade_seconds), afx.AudioFadeOut(fade_seconds)])
    return clip.with_duration(audio.duration).with_audio(audio)


def build_video(
    settings: Settings,
    title: str,
    stories: list[StoryItem],
    closing_line: str,
    outro_audio_path: Path,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    intro_path = _create_title_card(
        settings,
        title=title,
        subtitle="Tech, finance, crypto, and geopolitics in one daily cut.",
        output_path=output_dir / "intro.png",
    )

    clips = [ImageClip(str(intro_path)).with_duration(settings.intro_seconds).with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])]

    for story in stories:
        if not story.screenshot_paths:
            continue
        screenshot = Path(story.screenshot_paths[0])
        story_card = _prepare_story_card(settings, story, screenshot, output_dir)
        clip = ImageClip(str(story_card)).with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.4)])
        clips.append(_attach_audio(clip, Path(story.audio_path), settings.audio_crossfade_seconds))

    outro_path = _create_outro_card(
        settings,
        title="Subscribe for tomorrow's update.",
        closing_line=closing_line,
        output_path=output_dir / "outro.png",
    )
    outro_clip = ImageClip(str(outro_path)).with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.8)])
    clips.append(_attach_audio(outro_clip, outro_audio_path, settings.audio_crossfade_seconds))

    if not clips:
        raise ValueError("No visual assets available to build video")

    video = concatenate_videoclips(clips, method="compose", padding=-settings.audio_crossfade_seconds)
    target = output_dir / "daily_nexus_update.mp4"
    video.write_videofile(
        str(target),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
    )
    for clip in clips:
        if hasattr(clip, "audio") and clip.audio:
            clip.audio.close()
    if getattr(video, "audio", None):
        video.audio.close()
    video.close()
    return target
