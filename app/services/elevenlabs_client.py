from __future__ import annotations

import json
from pathlib import Path

import httpx

from app.config import Settings


def generate_voiceover(settings: Settings, text: str, output_dir: Path, target_path: Path | None = None) -> Path:
    api_key = settings.elevenlabs_api_key.strip()
    voice_id = settings.elevenlabs_voice_id.strip()
    model_id = settings.elevenlabs_model_id.strip()

    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY is required")
    if not voice_id:
        raise ValueError("ELEVENLABS_VOICE_ID is required")

    output_dir.mkdir(parents=True, exist_ok=True)
    target = target_path or (output_dir / "voiceover.mp3")
    target.parent.mkdir(parents=True, exist_ok=True)
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        f"?output_format=mp3_44100_128"
    )
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.8,
            "style": 0.65,
            "use_speaker_boost": True,
        },
    }
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            detail = ""
            try:
                parsed = response.json()
                detail = json.dumps(parsed)
            except Exception:  # noqa: BLE001 - best effort detail extraction
                detail = (response.text or "").strip()
            raise RuntimeError(
                "ElevenLabs request failed "
                f"(status={response.status_code}, voice_id={voice_id}, model_id={model_id}): {detail}"
            )
        target.write_bytes(response.content)

    return target
