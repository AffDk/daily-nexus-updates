from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import Settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _get_credentials(settings: Settings) -> Credentials:
    token_file = settings.youtube_token_file
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    else:
        credentials = None

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not settings.youtube_client_secrets_file.exists():
                raise FileNotFoundError(
                    f"Missing YouTube client secrets file: {settings.youtube_client_secrets_file}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(settings.youtube_client_secrets_file), SCOPES)
            credentials = flow.run_local_server(port=0)

        token_file.write_text(credentials.to_json(), encoding="utf-8")

    return credentials


def upload_video(settings: Settings, video_path: Path, title: str, description: str) -> str:
    if not settings.youtube_upload_enabled:
        return ""

    credentials = _get_credentials(settings)
    service = build("youtube", "v3", credentials=credentials)
    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "25",
        },
        "status": {
            "privacyStatus": settings.youtube_privacy_status,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    response = service.videos().insert(part="snippet,status", body=request_body, media_body=media).execute()
    return response["id"]
