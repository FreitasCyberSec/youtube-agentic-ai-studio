"""Offline integration smoke test for the actual MoviePy video renderer.

Uses synthetic image/audio assets so CI does not need Gemini, Pexels, Edge TTS,
YouTube credentials, or any paid API. It exercises create_video() and validates
the resulting MP4 with ffprobe and a full decode pass.
"""
import json
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from video.creator import create_video


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def test_create_video_produces_valid_mp4(tmp_path):
    # Create a real image asset for the renderer.
    image_path = tmp_path / "scene.png"
    image = Image.new("RGB", (640, 360), (18, 30, 55))
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 600, 320), outline=(120, 140, 255), width=8)
    draw.text((80, 130), "Offline render validation", fill="white")
    image.save(image_path)

    # Generate an 8-second audio track locally; no network/TTS required.
    audio_path = tmp_path / "narration.mp3"
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=8", "-q:a", "5", str(audio_path)
    ])

    (tmp_path / "narration.srt").write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nOffline render validation\n",
        encoding="utf-8",
    )

    script = {
        "video_type": "normal",
        "sections": [{
            "id": 1,
            "title": "Offline render validation",
            "section_type": "hook",
            "narration": (
                "This is a synthetic narration used to validate the complete "
                "video rendering path without external API credentials."
            ),
            "bullet_points": ["Renderer", "Audio", "MP4 validation"],
        }],
    }

    output_path = Path(create_video(script, str(audio_path), str(tmp_path), {1: str(image_path)}))
    assert output_path.is_file(), "create_video() did not create the output file"
    assert output_path.stat().st_size > 50_000, "MP4 output is unexpectedly small"

    probe = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height",
        "-of", "json", str(output_path)
    ])
    metadata = json.loads(probe.stdout)
    streams = metadata["streams"]
    video = next((s for s in streams if s["codec_type"] == "video"), None)
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)

    assert video is not None, f"No video stream found: {metadata}"
    assert audio is not None, f"No audio stream found: {metadata}"
    assert video["codec_name"] == "h264", f"Unexpected video codec: {video}"
    assert audio["codec_name"] == "aac", f"Unexpected audio codec: {audio}"
    assert (video["width"], video["height"]) == (1920, 1080), video
    duration = float(metadata["format"]["duration"])
    assert 7.0 <= duration <= 8.5, f"Unexpected duration {duration:.2f}s"
    assert int(metadata["format"]["size"]) > 50_000

    # Decode the entire file; catches corrupt/truncated frames and audio packets.
    run(["ffmpeg", "-v", "error", "-i", str(output_path), "-f", "null", "-"])

    print(f"Validated MP4: {output_path.name}, {duration:.2f}s, "
          f"{video['width']}x{video['height']}, H.264 + AAC, "
          f"{output_path.stat().st_size} bytes")
