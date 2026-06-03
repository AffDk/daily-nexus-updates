from __future__ import annotations

import logging
import re
import textwrap
from pathlib import Path
from urllib.parse import quote_plus
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.parse import parse_qs
from xml.etree import ElementTree

import httpx
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
    "attention required",
    "enable javascript and cookies",
    "bot detected",
    "automated queries",
    "request blocked",
)

_CONSENT_MARKERS = (
    "cookie",
    "consent",
    "privacy",
    "gdpr",
)

_ERROR_MARKERS = (
    "404",
    "not found",
    "page not found",
    "error 404",
    "http 404",
    "410 gone",
    "403 forbidden",
    "503 service unavailable",
)

_BAD_IMAGE_URL_MARKERS = (
    "404",
    "not-found",
    "not_found",
    "placeholder",
    "error",
    "captcha",
    "blocked",
    "access-denied",
)

_HUMAN_IMAGE_MARKERS = (
    "person",
    "people",
    "man",
    "woman",
    "human",
    "portrait",
    "face",
    "headshot",
    "selfie",
    "ceo",
    "politician",
    "speaker",
)


def _sanitize_filename(value: str) -> str:
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value)


def _is_blocked_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def _looks_like_consent_gate(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CONSENT_MARKERS)


def _looks_like_error_page(text: str, title: str, status_code: int | None, final_url: str) -> bool:
    lowered_text = text.lower()
    lowered_title = title.lower()
    lowered_url = final_url.lower()

    if status_code is not None and status_code >= 400:
        return True

    if any(marker in lowered_title for marker in _ERROR_MARKERS):
        return True

    if any(marker in lowered_text for marker in _ERROR_MARKERS):
        return True

    suspicious_url_markers = ("/404", "error", "access-denied", "blocked", "captcha", "challenge")
    if any(marker in lowered_url for marker in suspicious_url_markers):
        return True

    # Heuristic: challenge/error pages often have very short useful text.
    stripped = " ".join(lowered_text.split())
    if len(stripped) < 280 and (_is_blocked_text(stripped) or _looks_like_consent_gate(stripped)):
        return True

    return False


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


def _headline_from_label(label: str) -> str:
    # Label format: <topic>_<index>_<headline>; keep only the headline part.
    parts = label.split("_", 2)
    raw = parts[2] if len(parts) == 3 else label
    cleaned = raw.replace("_", " ").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:220] if cleaned else "Daily Nexus Update"


def _draw_headline_box(draw: ImageDraw.ImageDraw, headline: str) -> None:
    try:
        title_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 52)
    except Exception:
        title_font = ImageFont.load_default()

    wrapped = textwrap.wrap(headline, width=44)[:3]
    if not wrapped:
        wrapped = ["Daily Nexus Update"]

    lines = len(wrapped)
    line_height = 66 if getattr(title_font, "size", 0) >= 40 else 22
    text_block_h = lines * line_height + (lines - 1) * 8
    box_pad_x = 48
    box_pad_y = 26
    box_h = text_block_h + box_pad_y * 2
    y0 = 900 - box_h - 42
    y1 = 900 - 42
    x0 = 90
    x1 = 1440 - 90

    draw.rounded_rectangle((x0, y0, x1, y1), radius=22, fill=(0, 0, 0, 170))

    current_y = y0 + box_pad_y
    for line in wrapped:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        tx = (1440 - text_w) // 2
        draw.text((tx, current_y), line, font=title_font, fill=(238, 244, 252))
        current_y += line_height + 8


def _build_topic_visual_fallback(target: Path, topic: str, label: str, reason: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1440, 900), color=(14, 22, 36))
    draw = ImageDraw.Draw(image)

    # Simple gradients per topic so fallback remains informative and non-human.
    palette = {
        "crypto": ((22, 36, 64), (12, 18, 32), (255, 190, 60)),
        "finance": ((18, 44, 40), (10, 24, 24), (98, 226, 156)),
        "geopolitics": ((40, 28, 44), (18, 14, 28), (255, 140, 120)),
        "tech": ((16, 34, 52), (10, 18, 30), (120, 190, 255)),
    }
    top_color, bottom_color, accent = palette.get(topic, ((24, 30, 42), (12, 16, 24), (180, 200, 235)))
    for y in range(900):
        t = y / 899
        r = int(top_color[0] * (1 - t) + bottom_color[0] * t)
        g = int(top_color[1] * (1 - t) + bottom_color[1] * t)
        b = int(top_color[2] * (1 - t) + bottom_color[2] * t)
        draw.line((0, y, 1440, y), fill=(r, g, b))

    # Topic motif (abstract + no people).
    if topic == "finance":
        for i, h in enumerate([180, 260, 340, 220, 300, 420, 360]):
            x0 = 220 + i * 130
            draw.rectangle((x0, 740 - h, x0 + 70, 740), fill=(accent[0], accent[1], accent[2], 220))
        draw.line((180, 670, 380, 540, 560, 620, 760, 470, 980, 520, 1200, 390), fill=accent, width=8)
    elif topic == "crypto":
        draw.ellipse((460, 210, 980, 730), outline=accent, width=18)
        draw.ellipse((530, 280, 910, 660), outline=(accent[0], accent[1], accent[2], 180), width=12)
        draw.line((720, 300, 720, 640), fill=accent, width=14)
        draw.line((620, 360, 820, 360), fill=accent, width=14)
        draw.line((620, 520, 820, 520), fill=accent, width=14)
    elif topic == "geopolitics":
        draw.ellipse((350, 150, 1090, 890), outline=accent, width=14)
        draw.arc((380, 220, 1060, 820), start=10, end=170, fill=accent, width=8)
        draw.arc((380, 220, 1060, 820), start=190, end=350, fill=accent, width=8)
        draw.line((720, 170, 720, 870), fill=accent, width=8)
        draw.line((400, 520, 1040, 520), fill=accent, width=8)
    else:
        for i in range(8):
            x = 260 + i * 120
            draw.rectangle((x, 260, x + 70, 330), outline=accent, width=6)
            draw.line((x + 35, 330, x + 35, 620), fill=accent, width=5)

    try:
        topic_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 88)
    except Exception:
        topic_font = ImageFont.load_default()

    draw.text((90, 70), topic.upper(), font=topic_font, fill=(242, 246, 252))
    _draw_headline_box(draw, _headline_from_label(label))

    image.save(target)
    return target


def _extract_meta_image_urls(html: str, base_url: str) -> list[str]:
    # Prefer metadata image tags commonly used by publishers.
    pattern = re.compile(
        r"<meta[^>]+(?:property|name)=[\"'](?:og:image|twitter:image)[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    urls: list[str] = []
    for match in pattern.findall(html):
        candidate = urljoin(base_url, match.strip())
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            urls.append(candidate)
    return urls


def _center_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale to cover then center-crop to exact target dimensions."""
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w = max(int(img_w * scale), target_w)
    new_h = max(int(img_h * scale), target_h)
    scaled = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return scaled.crop((left, top, left + target_w, top + target_h))


def _tile_to_canvas(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    canvas = Image.new("RGB", (target_w, target_h), color=(16, 22, 34))
    tile_w, tile_h = img.size
    if tile_w <= 0 or tile_h <= 0:
        return canvas
    for x in range(0, target_w, tile_w):
        for y in range(0, target_h, tile_h):
            canvas.paste(img, (x, y))
    return canvas


def _is_wikimedia_image_url(image_url: str) -> bool:
    lowered = image_url.lower()
    return "wikimedia.org" in lowered or "wikipedia.org" in lowered


def _is_likely_human_image_url(image_url: str) -> bool:
    lowered = image_url.lower()
    return any(marker in lowered for marker in _HUMAN_IMAGE_MARKERS)


def _matches_non_human_topic_keywords(image_url: str, topic_hint: str) -> bool:
    topic = topic_hint.lower().strip()
    if not topic:
        return True

    marker_map = {
        "finance": ("chart", "graph", "market", "index", "candlestick", "trading", "equity"),
        "crypto": ("bitcoin", "crypto", "blockchain", "token", "coin", "ledger", "hash"),
        "geopolitics": ("map", "globe", "satellite", "border", "geopolit", "world", "atlas"),
        "tech": ("chip", "circuit", "network", "server", "code", "silicon", "diagram"),
    }
    markers = marker_map.get(topic)
    if not markers:
        return True

    lowered = image_url.lower()
    return any(marker in lowered for marker in markers)


def _save_image_from_url(image_url: str, target: Path, timeout: float = 15.0) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    }
    try:
        from io import BytesIO

        lowered_url = image_url.lower()
        if any(marker in lowered_url for marker in _BAD_IMAGE_URL_MARKERS):
            return False

        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(image_url)
        if response.status_code >= 400:
            return False
        if "image" not in (response.headers.get("content-type") or "").lower():
            return False
        img = Image.open(BytesIO(response.content)).convert("RGB")
        width, height = img.size
        # Reject only truly tiny images; center-crop handles any aspect ratio.
        if width < 200 or height < 150:
            return False

        # For small Wikimedia thumbnails, tile instead of stretching.
        if _is_wikimedia_image_url(image_url) and (width < 720 or height < 420):
            fitted = _tile_to_canvas(img, 1440, 900)
        else:
            fitted = _center_crop(img, 1440, 900)
        fitted.save(target)
        return True
    except Exception:
        return False


# Default Wikipedia article titles to use as per-topic image fallbacks.
_TOPIC_FALLBACK_ARTICLES: dict[str, list[str]] = {
    "tech": ["Artificial intelligence", "Technology", "Computer science"],
    "finance": ["Financial market", "Stock market", "Economics"],
    "crypto": ["Cryptocurrency", "Bitcoin", "Blockchain"],
    "geopolitics": ["Geopolitics", "International relations", "World politics"],
}


def _upscale_wiki_thumb_url(url: str, target_px: int = 1440) -> str:
    """Replace the pixel-width segment in a Wikimedia thumbnail URL to get a larger image."""
    return re.sub(r"/(\d+)px-", f"/{target_px}px-", url)


def _wiki_pageimage_url(title: str, thumb_px: int = 1440) -> list[str]:
    """Fetch a large thumbnail for a known Wikipedia article title via the pageimages API."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    found: list[str] = []
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "titles": title,
                    "prop": "pageimages",
                    "pithumbsize": str(thumb_px),
                    "pilicense": "any",
                    "format": "json",
                    "redirects": "1",
                },
            )
            if resp.status_code < 400:
                pages = resp.json().get("query", {}).get("pages", {})
                for page in pages.values():
                    thumb = (page.get("thumbnail") or {}).get("source")
                    if thumb:
                        # Ensure we request the largest possible version.
                        found.append(_upscale_wiki_thumb_url(thumb, thumb_px))
                        found.append(thumb)
    except Exception:
        pass
    return found


def _fetch_wikipedia_images_for_query(query_hint: str, topic_hint: str = "", timeout: float = 15.0) -> list[str]:
    """Search Wikipedia for the most relevant article and return large image URLs."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    found: list[str] = []

    if query_hint.strip():
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            try:
                search_resp = client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query_hint,
                        "srlimit": "5",
                        "format": "json",
                    },
                )
                if search_resp.status_code < 400:
                    titles = [
                        r["title"]
                        for r in search_resp.json().get("query", {}).get("search", [])
                        if r.get("title")
                    ]
                    for article_title in titles[:5]:
                        found.extend(_wiki_pageimage_url(article_title))
                        if len(found) >= 6:
                            break
            except Exception:
                pass

    # Per-topic fallback articles guarantee at least one image is found.
    topic_key = topic_hint.lower().strip()
    for fallback_title in _TOPIC_FALLBACK_ARTICLES.get(topic_key, ["Technology"]):
        if len(found) >= 6:
            break
        found.extend(_wiki_pageimage_url(fallback_title))

    return found


def _extract_google_news_links(rss_xml: str) -> list[str]:
    links: list[str] = []
    try:
        root = ElementTree.fromstring(rss_xml)
    except ElementTree.ParseError:
        return links

    for item in root.findall("./channel/item"):
        link_node = item.find("link")
        if link_node is not None and link_node.text:
            links.append(link_node.text.strip())
    return links


def _decode_bing_apiclick_url(link: str) -> str:
    parsed = urlparse(link)
    params = parse_qs(parsed.query)
    direct = (params.get("url") or [""])[0]
    if direct:
        return direct
    return link


def _fetch_bing_news_image_urls(query_hint: str, topic_hint: str = "", timeout: float = 15.0) -> list[str]:
    topic_non_human = {
        "finance": "stock market chart graph no people",
        "crypto": "blockchain bitcoin chart infographic no people",
        "geopolitics": "world map geopolitical map infographic no people",
        "tech": "technology circuit diagram infographic no people",
    }
    hinted = topic_non_human.get(topic_hint.lower().strip(), "news infographic no people")
    query = " ".join(token for token in [query_hint.strip(), topic_hint.strip(), hinted] if token)
    if not query:
        return []

    rss_url = f"https://www.bing.com/news/search?q={quote_plus(query)}&format=RSS"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    }

    candidates: list[str] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            rss_response = client.get(rss_url)
            if rss_response.status_code >= 400:
                return []

            article_links = _extract_google_news_links(rss_response.text)
            for link in article_links[:8]:
                article_link = _decode_bing_apiclick_url(link)
                try:
                    page_response = client.get(article_link)
                    if page_response.status_code >= 400:
                        continue
                    candidates.extend(
                        _extract_meta_image_urls(page_response.text, str(page_response.url))
                    )
                    if len(candidates) >= 10:
                        break
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        return []

    return candidates


def _fetch_google_news_image_urls(query_hint: str, topic_hint: str = "", timeout: float = 15.0) -> list[str]:
    query = " ".join(token for token in [query_hint.strip(), topic_hint.strip(), "news"] if token)
    if not query:
        return []

    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    }

    candidates: list[str] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            rss_response = client.get(rss_url)
            if rss_response.status_code >= 400:
                return []

            article_links = _extract_google_news_links(rss_response.text)
            for article_link in article_links[:6]:
                try:
                    page_response = client.get(article_link)
                    if page_response.status_code >= 400:
                        continue
                    candidates.extend(
                        _extract_meta_image_urls(page_response.text, str(page_response.url))
                    )
                    if len(candidates) >= 10:
                        break
                except httpx.HTTPError:
                    continue
    except httpx.HTTPError:
        return []

    return candidates


def _try_download_related_image(url: str, query_hint: str, target: Path, topic_hint: str = "") -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
    }
    candidates: list[str] = []
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
            page = client.get(url)
            if page.status_code < 400:
                candidates.extend(_extract_meta_image_urls(page.text, str(page.url)))
    except httpx.HTTPError:
        pass

    # Prefer topically relevant images discovered via Google News search results.
    candidates.extend(
        _fetch_google_news_image_urls(
            query_hint=query_hint or topic_hint or "world news",
            topic_hint=topic_hint,
        )
    )

    # If Google News links are consent-blocked in this region, use Bing News search.
    if not candidates:
        candidates.extend(
            _fetch_bing_news_image_urls(
                query_hint=query_hint or topic_hint or "world news",
                topic_hint=topic_hint,
            )
        )

    # Wikipedia search (story-specific) + per-topic guaranteed fallback images.
    candidates.extend(_fetch_wikipedia_images_for_query(query_hint or "world news", topic_hint=topic_hint))

    for candidate in candidates:
        if _is_likely_human_image_url(candidate):
            continue
        if not _matches_non_human_topic_keywords(candidate, topic_hint):
            continue
        if _save_image_from_url(candidate, target):
            logger.info("Saved related fallback image for %s from %s", url, candidate)
            return True
    return False


def capture_screenshot(url: str, output_dir: Path, label: str, query_hint: str = "") -> Path:
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
            response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1200)
            status_code = response.status if response is not None else None
            final_url = page.url or url

            first_text = (page.inner_text("body", timeout=3_000) or "")[:8000]
            if _looks_like_consent_gate(first_text):
                _click_common_consent_buttons(page)
                page.wait_for_timeout(800)

            body_text = (page.inner_text("body", timeout=3_000) or "")[:12000]
            title_text = page.title() or ""

            # Derive the topic from the label (label format: "<topic>_<index>_<title>").
            topic_hint = label.split("_")[0] if "_" in label else ""
            if _looks_like_error_page(body_text, title_text, status_code, final_url):
                logger.warning("Error/interstitial page detected for %s (status=%s, final_url=%s)", url, status_code, final_url)
                if not _try_download_related_image(url, query_hint or label, target, topic_hint=topic_hint):
                    _build_topic_visual_fallback(target, topic_hint, label, "error or interstitial page")
            elif _is_blocked_text(body_text):
                logger.warning("Blocked/interstitial page detected for %s; using fallback card", url)
                if not _try_download_related_image(url, query_hint or label, target, topic_hint=topic_hint):
                    _build_topic_visual_fallback(target, topic_hint, label, "blocked or unusual activity")
            elif _looks_like_consent_gate(body_text) and len(body_text.strip()) < 500:
                logger.warning("Consent interstitial remained for %s; using fallback card", url)
                if not _try_download_related_image(url, query_hint or label, target, topic_hint=topic_hint):
                    _build_topic_visual_fallback(target, topic_hint, label, "consent gate")
            else:
                page.screenshot(path=str(target), full_page=True)
        except Exception as exc:  # noqa: BLE001 - fallback keeps pipeline moving
            topic_hint = label.split("_")[0] if "_" in label else ""
            logger.warning("Screenshot failed for %s (%s); using fallback card", url, exc)
            if not _try_download_related_image(url, query_hint or label, target, topic_hint=topic_hint):
                _build_topic_visual_fallback(target, topic_hint, label, "snapshot error")
        finally:
            context.close()
            browser.close()

    return target
