from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

logger = logging.getLogger("daily_nexus_update.screenshot")

_BLOCK_MARKERS = (
    "unusual activity",
    "verify you are human",
    "captcha",
    "access denied",
    "temporarily blocked",
    "cloudflare",
    "checking your browser",
)

_CONSENT_MARKERS = (
    "cookie",
    "consent",
    "privacy",
    "gdpr",
)


def _sanitize_filename(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)


def _is_blocked_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def _looks_like_consent_gate(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CONSENT_MARKERS)


def _click_common_consent_buttons(page) -> None:
    selectors = [
        "button:has-text('Accept all')",
        "button:has-text('I agree')",
        "button:has-text('Accept')",
        "button:has-text('Agree')",
        "button:has-text('Allow all')",
        "button:has-text('Got it')",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.click(timeout=1500)
                page.wait_for_timeout(500)
                return
        except Exception:
            continue


def _build_fallback_card(target: Path, url: str, label: str, reason: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1440, 900), color=(15, 20, 34))
    draw = ImageDraw.Draw(image)
    font_title = ImageFont.load_default()
    font_body = ImageFont.load_default()
    draw.rectangle((60, 60, 1380, 840), fill=(24, 34, 56))
    draw.text((100, 120), "Reference Snapshot Unavailable", font=font_title, fill=(245, 245, 245))
    draw.text((100, 180), f"Reason: {reason}", font=font_body, fill=(220, 225, 235))
    draw.text((100, 240), f"Source: {url}", font=font_body, fill=(175, 200, 240))
    draw.text((100, 300), f"Label: {label}", font=font_body, fill=(195, 210, 230))
    draw.text((100, 380), "The website returned an interstitial, consent gate, or anti-bot page.", font=font_body, fill=(210, 215, 225))
    draw.text((100, 420), "The pipeline kept this story using a safe fallback card.", font=font_body, fill=(210, 215, 225))
    image.save(target)
    return target


def capture_screenshot(url: str, output_dir: Path, label: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{_sanitize_filename(label)}.png"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1200)

            first_text = (page.inner_text("body", timeout=3_000) or "")[:8000]
            if _looks_like_consent_gate(first_text):
                _click_common_consent_buttons(page)
                page.wait_for_timeout(800)

            body_text = (page.inner_text("body", timeout=3_000) or "")[:12000]
            if _is_blocked_text(body_text):
                logger.warning("Blocked/interstitial page detected for %s; using fallback card", url)
                _build_fallback_card(target, url, label, "blocked or unusual activity")
            elif _looks_like_consent_gate(body_text) and len(body_text.strip()) < 500:
                logger.warning("Consent interstitial remained for %s; using fallback card", url)
                _build_fallback_card(target, url, label, "consent gate")
            else:
                page.screenshot(path=str(target), full_page=True)
        except Exception as exc:  # noqa: BLE001 - fallback keeps pipeline moving
            logger.warning("Screenshot failed for %s (%s); using fallback card", url, exc)
            _build_fallback_card(target, url, label, "snapshot error")
        finally:
            context.close()
            browser.close()

    return target
