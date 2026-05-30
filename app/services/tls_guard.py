from __future__ import annotations

import os
from pathlib import Path

from app.config import Settings

_GTS_ROOT_MARKERS = (
    "GTS Root R1",
    "GTS Root R2",
    "GTS Root R3",
    "GTS Root R4",
)


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def validate_google_tls_configuration(settings: Settings) -> list[str]:
    warnings: list[str] = []

    if not settings.tls_enforce_system_roots:
        warnings.append(
            "TLS_ENFORCE_SYSTEM_ROOTS is false. Prefer system roots or a full CA bundle that includes all GTS roots."
        )

    pinning_indicators = [
        os.getenv("TLS_PINNED_CERT"),
        os.getenv("TLS_PINNED_INTERMEDIATE"),
        os.getenv("TLS_PIN_SHA256"),
        os.getenv("CERT_PINNING_ENABLED"),
    ]
    if any(value for value in pinning_indicators):
        warnings.append(
            "Certificate pinning indicators were detected in environment variables. Pinning Google intermediates/leaf certs can break after routine rotations."
        )

    custom_candidates = [
        os.getenv("SSL_CERT_FILE", "").strip(),
        os.getenv("REQUESTS_CA_BUNDLE", "").strip(),
        os.getenv("CURL_CA_BUNDLE", "").strip(),
        settings.custom_ca_bundle.strip(),
    ]
    custom_candidates = [candidate for candidate in custom_candidates if candidate]

    for raw_path in custom_candidates:
        path = Path(raw_path)
        if not path.exists():
            warnings.append(
                f"Custom trust store path not found: {path}. Google API connectivity may fail."
            )
            continue

        text = _read_text_if_exists(path)
        if not text:
            warnings.append(
                f"Custom trust store could not be read: {path}. Verify it contains full CA roots including GTS roots."
            )
            continue

        if not any(marker in text for marker in _GTS_ROOT_MARKERS):
            warnings.append(
                f"Custom trust store {path} does not appear to include GTS root markers ({', '.join(_GTS_ROOT_MARKERS)}). Update bundle before Google ECDSA rollout."
            )

    return warnings
