#!/usr/bin/env python3
"""Generate a review-only pilot video without opening the interactive review server or uploading it."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Running a script inside scripts/ puts that folder, not the repository root, on sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from agents.researcher import research_topic
from agents.scriptwriter import write_script
from video.stock import download_images
from video.narrator import generate_narration
from video.creator import create_video


CHANNEL_DESCRIPTION = """
Canal brasileiro de história, mistérios históricos, civilizações antigas, guerras e descobertas arqueológicas.
Tom documental, curioso e cinematográfico; separar fatos comprovados de hipóteses e lendas.
Não apresentar especulações como fatos. Público geral brasileiro.
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topic", default="O mistério da construção das pirâmides do Egito")
    parser.add_argument("--output", default="output/pilot-pyramids")
    parser.add_argument("--video-type", choices=("normal", "shorts"), default="normal")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    (output / "images").mkdir(parents=True, exist_ok=True)

    # Override channel defaults for this pilot without changing tracked config.py.
    config.CHANNEL_NAME = "Além da História"
    config.BRAND_TEXT = "ALÉM DA HISTÓRIA"
    config.CHANNEL_DESCRIPTION = CHANNEL_DESCRIPTION
    config.OUTPUT_DIR = str(output)
    config.IMAGES_DIR = str(output / "images")

    print(f"\n=== PILOT VIDEO: {args.topic} ===")
    research = research_topic(CHANNEL_DESCRIPTION, topic_override=args.topic)
    with (output / "research.json").open("w", encoding="utf-8") as f:
        json.dump(research, f, ensure_ascii=False, indent=2)

    script = write_script(research, video_type=args.video_type)
    script["video_type"] = args.video_type
    with (output / "script.json").open("w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    image_map = download_images(script, str(output))
    audio_path = generate_narration(script, str(output))
    video_path = create_video(script, audio_path, str(output), image_map, video_type=args.video_type)

    video = Path(video_path)
    if not video.is_file() or video.stat().st_size < 50_000:
        raise RuntimeError("Render output is missing or unexpectedly small.")

    manifest = {
        "topic": args.topic,
        "title": script.get("title", research.get("video_title", args.topic)),
        "video_type": args.video_type,
        "video_path": str(video),
        "size_bytes": video.stat().st_size,
        "human_approval_required": True,
        "uploaded": False,
        "note": "Generated for review only. This script never uploads to YouTube.",
    }
    with (output / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\nPILOT_GENERATION_SUCCESS")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
