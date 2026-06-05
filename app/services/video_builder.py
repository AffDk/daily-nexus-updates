from __future__ import annotations

import textwrap
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from moviepy import AudioFileClip, ImageClip, concatenate_videoclips, vfx, afx
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.models import StoryItem


def _fit_image(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale-to-cover then center-crop to exact target dimensions."""
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = max(int(img_w * scale), target_w)
    new_h = max(int(img_h * scale), target_h)
    scaled = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))


def _draw_vertical_gradient(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> None:
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        draw.line((0, y, width, y), fill=(r, g, b))


def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates: list[Path] = []
    if font_path:
        path = Path(font_path)
        if path.exists():
            candidates.append(path)

    # Common fonts available on Windows/Linux installations.
    candidates.extend(
        [
            Path("C:/Windows/Fonts/segoeuib.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except Exception:
                continue

    return ImageFont.load_default()


def _source_label_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if not host:
        return "source"

    host = host.split(":")[0]
    parts = [p for p in host.split(".") if p and p not in {"www", "m"}]

    if len(parts) >= 2 and parts[0] == "news" and parts[1] == "yahoo":
        return "yahoo news"
    if len(parts) >= 2 and parts[0] == "news" and parts[1] == "google":
        return "google"
    if parts and parts[0] == "google":
        return "google"

    if len(parts) >= 2:
        return parts[-2].replace("-", " ")
    return parts[0].replace("-", " ") if parts else "source"


def _source_label_for_story(story: StoryItem) -> str:
    if story.reference_urls:
        return _source_label_from_url(str(story.reference_urls[0]))
    if story.source_name:
        name = story.source_name.strip().lower()
        for suffix in [".com", ".org", ".net"]:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        return name[:24] if name else "source"
    return ""


def _draw_story_headline_box(
    draw: ImageDraw.ImageDraw,
    title: str,
    width: int,
    height: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> tuple[int, int, int, int]:
    wrapped = textwrap.wrap((title or "").strip(), width=44)[:3]
    if not wrapped:
        wrapped = ["Daily Nexus Update"]

    line_height = 66 if getattr(font, "size", 0) >= 40 else 22
    text_block_h = len(wrapped) * line_height + (len(wrapped) - 1) * 8
    box_pad_y = 24
    box_h = text_block_h + box_pad_y * 2

    margin_x = 90
    margin_bottom = 42
    y0 = height - box_h - margin_bottom
    y1 = height - margin_bottom
    x0 = margin_x
    x1 = width - margin_x

    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=(0, 0, 0, 170))

    current_y = y0 + box_pad_y
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        tx = (width - text_w) // 2
        draw.text((tx, current_y), line, font=font, fill=(238, 244, 252))
        current_y += line_height + 8

    return (x0, y0, x1, y1)


def _create_title_card(settings: Settings, title: str, subtitle: str, output_path: Path) -> Path:
    image = Image.new("RGB", (settings.video_width, settings.video_height), color=(8, 12, 22))
    draw = ImageDraw.Draw(image)
    _draw_vertical_gradient(draw, settings.video_width, settings.video_height, (10, 23, 48), (4, 9, 20))

    panel_margin = 72
    draw.rounded_rectangle(
        (
            panel_margin,
            panel_margin,
            settings.video_width - panel_margin,
            settings.video_height - panel_margin,
        ),
        radius=44,
        fill=(8, 18, 36, 255),
    )

    header_font = _load_font(settings.font_path or None, 96)
    body_font = _load_font(settings.font_path or None, 46)
    title_lines = "\n".join(textwrap.wrap(title, width=24))
    subtitle_lines = "\n".join(textwrap.wrap(subtitle, width=36))
    draw.multiline_text((130, 180), title_lines, font=header_font, fill=(246, 248, 252), spacing=14)
    draw.multiline_text((130, 430), subtitle_lines, font=body_font, fill=(185, 205, 236), spacing=12)
    image.save(output_path)
    return output_path


def _prepare_story_card(settings: Settings, story: StoryItem, screenshot_path: Path, output_dir: Path) -> Path:
    card_path = output_dir / f"{screenshot_path.stem}_card.png"
    raw = Image.open(screenshot_path).convert("RGB")
    # Smart center-crop so the screenshot fills the frame without distortion.
    card = _fit_image(raw, settings.video_width, settings.video_height)

    overlay = Image.new("RGBA", card.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    headline_font = _load_font(settings.font_path or None, 52)
    _, headline_y0, _, _ = _draw_story_headline_box(
        draw=draw,
        title=story.display_title or story.title,
        width=settings.video_width,
        height=settings.video_height,
        font=headline_font,
    )

    source_name = _source_label_for_story(story)
    if source_name:
        source_font = _load_font(settings.font_path or None, 38)
        label_text = f"Source: {source_name}"
        bbox = draw.textbbox((0, 0), label_text, font=source_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x, pad_y = 18, 10
        margin_right = 32
        margin_gap = 16

        pill_x0 = settings.video_width - text_w - pad_x * 2 - margin_right
        pill_y0 = max(20, headline_y0 - text_h - pad_y * 2 - margin_gap)
        pill_x1 = pill_x0 + text_w + pad_x * 2
        pill_y1 = pill_y0 + text_h + pad_y * 2

        draw.rounded_rectangle((pill_x0, pill_y0, pill_x1, pill_y1), radius=12, fill=(0, 0, 0, 180))
        draw.text((pill_x0 + pad_x, pill_y0 + pad_y), label_text, font=source_font, fill=(120, 190, 255))

    composite = Image.alpha_composite(card.convert("RGBA"), overlay)
    composite.convert("RGB").save(card_path)

    return card_path


def _create_topic_card(settings: Settings, topic: str, output_path: Path) -> Path:
    """Short separator card shown when the video topic changes."""
    image = Image.new("RGB", (settings.video_width, settings.video_height), color=(5, 10, 20))
    draw = ImageDraw.Draw(image)
    header_font = _load_font(settings.font_path or None, 80)
    accent_colors = {
        "tech": (100, 180, 255),
        "finance": (100, 230, 150),
        "crypto": (255, 190, 60),
        "geopolitics": (255, 120, 100),
    }
    color = accent_colors.get(topic.lower(), (200, 210, 230))
    label = topic.upper()
    bbox = draw.textbbox((0, 0), label, font=header_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (settings.video_width - text_w) // 2
    y = (settings.video_height - text_h) // 2
    # Subtle underline bar
    bar_y = y + text_h + 20
    draw.rectangle((x, bar_y, x + text_w, bar_y + 6), fill=color)
    draw.text((x, y), label, font=header_font, fill=color)
    image.save(output_path)
    return output_path


def _create_outro_card(settings: Settings, title: str, closing_line: str, output_path: Path) -> Path:
    image = Image.new("RGB", (settings.video_width, settings.video_height), color=(5, 9, 16))
    draw = ImageDraw.Draw(image)
    _draw_vertical_gradient(draw, settings.video_width, settings.video_height, (12, 24, 44), (3, 8, 18))

    panel_margin = 72
    draw.rounded_rectangle(
        (
            panel_margin,
            panel_margin,
            settings.video_width - panel_margin,
            settings.video_height - panel_margin,
        ),
        radius=44,
        fill=(10, 20, 38, 255),
    )

    header_font = _load_font(settings.font_path or None, 82)
    body_font = _load_font(settings.font_path or None, 42)
    title_lines = "\n".join(textwrap.wrap(title, width=28))
    closing_lines = "\n".join(textwrap.wrap(closing_line, width=42))
    draw.multiline_text((130, 185), title_lines, font=header_font, fill=(246, 248, 252), spacing=14)
    draw.multiline_text((130, 400), closing_lines, font=body_font, fill=(198, 214, 238), spacing=12)
    image.save(output_path)
    return output_path


def _attach_audio(
    clip: ImageClip,
    audio_path: Path,
    fade_seconds: float,
    max_duration: float | None = None,
) -> ImageClip:
    audio = AudioFileClip(str(audio_path))
    if max_duration is not None and audio.duration > max_duration:
        audio = audio.subclipped(0, max_duration)
    safe_fade = min(fade_seconds, max(0.05, float(audio.duration) * 0.45))
    audio = audio.with_effects([afx.AudioFadeIn(safe_fade), afx.AudioFadeOut(safe_fade)])
    return clip.with_audio(audio)


def _write_reference_manifest(title: str, stories: list[StoryItem], output_dir: Path) -> Path:
    manifest = output_dir / "references.html"
    rows: list[str] = []
    for story in stories:
        if not story.reference_urls:
            continue
        links = "<br/>".join(
            f'<a href="{escape(str(url))}" target="_blank" rel="noopener noreferrer">Reference</a>'
            for url in story.reference_urls[:3]
        )
        rows.append(
            "<li>"
            f"<strong>{escape(story.title)}</strong>"
            f"<div>{links}</div>"
            "</li>"
        )

    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        f"<title>{escape(title)} references</title>"
        "<style>body{font-family:Segoe UI,Tahoma,sans-serif;background:#0b1220;color:#e8eefc;padding:24px;}"
        "a{color:#8fc7ff} li{margin:12px 0} h1{font-size:1.4rem}</style></head><body>"
        f"<h1>{escape(title)} - References</h1>"
        "<p>Open links in new tabs.</p>"
        f"<ol>{''.join(rows) or '<li>No references captured.</li>'}</ol>"
        "</body></html>"
    )
    manifest.write_text(html, encoding="utf-8")
    return manifest


def build_video(
    settings: Settings,
    title: str,
    stories: list[StoryItem],
    closing_line: str,
    outro_audio_path: Path | None,
    output_dir: Path,
    intro_audio_path: Path | None = None,
    transition_audio_by_topic: dict[str, str] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    intro_path = _create_title_card(
        settings,
        title=title,
        subtitle="Tech, finance, crypto, and geopolitics in one daily cut.",
        output_path=output_dir / "intro.png",
    )

    intro_clip = ImageClip(str(intro_path)).with_duration(settings.intro_seconds).with_effects([vfx.FadeIn(0.8), vfx.FadeOut(0.8)])
    if intro_audio_path and Path(intro_audio_path).is_file():
        intro_audio_probe = AudioFileClip(str(intro_audio_path))
        raw_intro_dur = max(1.0, float(intro_audio_probe.duration or 0.0))
        intro_audio_probe.close()
        intro_dur = max(raw_intro_dur, float(settings.intro_seconds))
        intro_clip = intro_clip.with_duration(intro_dur)
        intro_clip = _attach_audio(
            intro_clip,
            intro_audio_path,
            settings.audio_crossfade_seconds,
        )
    clips = [intro_clip]
    current_topic: str = ""
    transition_audio_by_topic = transition_audio_by_topic or {}

    for story in stories:
        if not story.screenshot_paths:
            continue

        # Insert a topic separator card when the topic changes (longer fade for drama).
        if story.topic != current_topic:
            separator_path = output_dir / f"topic_{story.topic}.png"
            _create_topic_card(settings, story.topic, separator_path)
            separator_duration = 2.0
            transition_audio_value = (transition_audio_by_topic.get(story.topic) or "").strip()
            transition_audio = Path(transition_audio_value) if transition_audio_value else None
            if transition_audio and transition_audio.is_file():
                transition_probe = AudioFileClip(str(transition_audio))
                transition_duration = max(1.0, float(transition_probe.duration or 0.0))
                transition_probe.close()
                separator_duration = max(separator_duration, transition_duration)

            separator_clip = ImageClip(str(separator_path)).with_duration(separator_duration).with_effects(
                [vfx.FadeIn(1.0), vfx.FadeOut(1.0)]
            )

            if transition_audio and transition_audio.is_file():
                separator_clip = _attach_audio(separator_clip, transition_audio, settings.audio_crossfade_seconds)
            clips.append(separator_clip)
            current_topic = story.topic

        screenshot = Path(story.screenshot_paths[0])
        story_card = _prepare_story_card(settings, story, screenshot, output_dir)
        if story.audio_path and Path(story.audio_path).is_file():
            audio_probe = AudioFileClip(str(Path(story.audio_path)))
            raw_audio_duration = max(1.0, float(audio_probe.duration or 0.0))
            audio_probe.close()
            audio_duration = raw_audio_duration
            clip = (
                ImageClip(str(story_card))
                .with_duration(audio_duration)
                .with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
            )
            clips.append(
                _attach_audio(
                    clip,
                    Path(story.audio_path),
                    settings.audio_crossfade_seconds,
                )
            )
        else:
            silent_duration = max(1, story.target_seconds or settings.min_story_seconds)
            clip = (
                ImageClip(str(story_card))
                .with_duration(silent_duration)
                .with_effects([vfx.FadeIn(0.5), vfx.FadeOut(0.5)])
            )
            clips.append(clip)

    outro_path = _create_outro_card(
        settings,
        title="Subscribe for tomorrow's update.",
        closing_line=closing_line,
        output_path=output_dir / "outro.png",
    )
    if outro_audio_path and Path(outro_audio_path).is_file():
        outro_audio_probe = AudioFileClip(str(outro_audio_path))
        raw_outro_duration = max(1.0, float(outro_audio_probe.duration or 0.0))
        outro_audio_probe.close()
        outro_audio_duration = max(raw_outro_duration, float(settings.outro_seconds))
        outro_clip = (
            ImageClip(str(outro_path))
            .with_duration(outro_audio_duration)
            .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.8)])
        )
        clips.append(
            _attach_audio(
                outro_clip,
                outro_audio_path,
                settings.audio_crossfade_seconds,
            )
        )
    else:
        outro_clip = (
            ImageClip(str(outro_path))
            .with_duration(max(1, settings.outro_seconds))
            .with_effects([vfx.FadeIn(0.4), vfx.FadeOut(0.8)])
        )
        clips.append(outro_clip)

    if not clips:
        raise ValueError("No visual assets available to build video")

    video = concatenate_videoclips(clips, padding=0)
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
    _write_reference_manifest(title, stories, output_dir)
    return target
