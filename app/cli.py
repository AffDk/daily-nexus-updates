from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.models import StoryRequest
from app.pipeline import run_pipeline
from app.services.youtube_uploader import upload_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Nexus Update pipeline")
    parser.add_argument("--topics", nargs="*", default=["tech", "finance", "crypto", "geopolitics"])
    parser.add_argument("--max-stories", type=int, default=None)
    parser.add_argument("--publish-to-youtube", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--upload-video", type=Path, default=None)
    parser.add_argument("--youtube-title", type=str, default=None)
    parser.add_argument("--youtube-description", type=str, default="")
    args = parser.parse_args()

    settings = get_settings()

    if args.upload_video:
        video_path = args.upload_video
        if not video_path.exists() or not video_path.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        title = args.youtube_title or f"Daily Nexus Update Test Upload | {video_path.stem}"
        description = args.youtube_description or "Manual test upload from local render output."
        video_id = upload_video(settings, video_path, title, description)
        print(
            json.dumps(
                {
                    "video_path": str(video_path),
                    "youtube_video_id": video_id,
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
                },
                indent=2,
            )
        )
        return

    request = StoryRequest(
        topics=args.topics,
        max_stories=args.max_stories or settings.max_stories,
        publish_to_youtube=args.publish_to_youtube,
    )
    result = run_pipeline(request=request, output_dir=args.output or settings.output_dir)
    print(json.dumps(result.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
