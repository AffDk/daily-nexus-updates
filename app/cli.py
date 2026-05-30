from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.config import get_settings
from app.models import StoryRequest
from app.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Nexus Update pipeline")
    parser.add_argument("--topics", nargs="*", default=["tech", "finance", "crypto", "geopolitics"])
    parser.add_argument("--max-stories", type=int, default=None)
    parser.add_argument("--publish-to-youtube", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    request = StoryRequest(
        topics=args.topics,
        max_stories=args.max_stories or settings.max_stories,
        publish_to_youtube=args.publish_to_youtube,
    )
    result = run_pipeline(request=request, output_dir=args.output or settings.output_dir)
    print(json.dumps(result.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()
