from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Daily Nexus Update", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=False, alias="DEBUG")

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.1-flash-lite", alias="GEMINI_MODEL")

    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", alias="ELEVENLABS_VOICE_ID")
    elevenlabs_model_id: str = Field(default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL_ID")

    youtube_client_secrets_file: Path = Field(
        default=Path("secrets/youtube_client_secret.json"),
        alias="YOUTUBE_CLIENT_SECRETS_FILE",
    )
    youtube_token_file: Path = Field(default=Path("secrets/youtube_token.json"), alias="YOUTUBE_TOKEN_FILE")
    youtube_upload_enabled: bool = Field(default=False, alias="YOUTUBE_UPLOAD_ENABLED")
    youtube_privacy_status: str = Field(default="private", alias="YOUTUBE_PRIVACY_STATUS")
    youtube_channel_name: str = Field(default="dailynexusupdate", alias="YOUTUBE_CHANNEL_NAME")

    failure_email_enabled: bool = Field(default=False, alias="FAILURE_EMAIL_ENABLED")
    failure_email_to: str = Field(default="", alias="FAILURE_EMAIL_TO")
    failure_email_from: str = Field(default="", alias="FAILURE_EMAIL_FROM")
    failure_email_subject_prefix: str = Field(default="[Daily Nexus Update]", alias="FAILURE_EMAIL_SUBJECT_PREFIX")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")

    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    news_memory_file: Path = Field(default=Path("data/news_memory.json"), alias="NEWS_MEMORY_FILE")
    news_memory_archive_file: Path = Field(
        default=Path("data/news_memory_archive.json"),
        alias="NEWS_MEMORY_ARCHIVE_FILE",
    )
    custom_ca_bundle: str = Field(default="", alias="CUSTOM_CA_BUNDLE")
    tls_enforce_system_roots: bool = Field(default=True, alias="TLS_ENFORCE_SYSTEM_ROOTS")
    max_stories: int = Field(default=5, alias="MAX_STORIES")
    intro_seconds: int = Field(default=8, alias="INTRO_SECONDS")
    outro_seconds: int = Field(default=14, alias="OUTRO_SECONDS")
    min_story_seconds: int = Field(default=30, alias="MIN_STORY_SECONDS")
    max_story_seconds: int = Field(default=90, alias="MAX_STORY_SECONDS")
    max_video_seconds: int = Field(default=300, alias="MAX_VIDEO_SECONDS")
    audio_crossfade_seconds: float = Field(default=1.2, alias="AUDIO_CROSSFADE_SECONDS")
    retry_max_attempts: int = Field(default=3, alias="RETRY_MAX_ATTEMPTS")
    retry_delay_seconds: int = Field(default=300, alias="RETRY_DELAY_SECONDS")
    retry_backoff_multiplier: float = Field(default=1.0, alias="RETRY_BACKOFF_MULTIPLIER")
    video_width: int = Field(default=1920, alias="VIDEO_WIDTH")
    video_height: int = Field(default=1080, alias="VIDEO_HEIGHT")
    story_seconds: int = Field(default=8, alias="STORY_SECONDS")
    font_path: str = Field(default="", alias="FONT_PATH")
    background_music_file: str = Field(default="", alias="BACKGROUND_MUSIC_FILE")

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.news_memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.news_memory_archive_file.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_token_file.parent.mkdir(parents=True, exist_ok=True)
        self.youtube_client_secrets_file.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
