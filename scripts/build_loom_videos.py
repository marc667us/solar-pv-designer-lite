"""Build the 3 Loom-style walkthrough MP4s from the shell scripts in docs/.

Multi-shot slideshow:
  1. Read each docs/loom_shell_0{1,2,3}_*.md
  2. Extract spoken voiceover from the "Voiceover" column
  3. Synthesize MP3 via edge-tts (en-US-AriaNeural)
  4. Per video, build an ffmpeg concat list that shows each feature-
     specific screenshot for its proportional slice of the audio
     duration (so screens change as the voice describes them).
  5. Composite into MP4 via ffmpeg (binary from imageio-ffmpeg).

Each shell maps to a directory of screenshots taken by
scripts/screenshot_for_loom.py. The number of screenshots determines
the slideshow granularity; audio length determines per-shot duration.

Outputs (also mirrored to Desktop):
  docs/SolarPro_BOQ_60s.mp4
  docs/SolarPro_CostEstimate_60s.mp4
  docs/SolarPro_SendToClient_30s.mp4
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(r"C:\Users\USER\Desktop\solar-pv-designer-lite")
DOCS = PROJECT / "docs"
SCREENS_BASE = DOCS / "screens"
DESKTOP = Path(r"C:\Users\USER\Desktop")

# (shell_md, screens_subdir, output_mp3, output_mp4, voice)
SHELLS = [
    ("loom_shell_01_BOQ_in_60_seconds.md",
     "loom_boq",
     "SolarPro_BOQ_60s.mp3",
     "SolarPro_BOQ_60s.mp4",
     "en-US-AriaNeural"),
    ("loom_shell_02_Cost_estimate_in_60_seconds.md",
     "loom_cost",
     "SolarPro_CostEstimate_60s.mp3",
     "SolarPro_CostEstimate_60s.mp4",
     "en-US-AriaNeural"),
    ("loom_shell_03_Send_to_client_in_30_seconds.md",
     "loom_send",
     "SolarPro_SendToClient_30s.mp3",
     "SolarPro_SendToClient_30s.mp4",
     "en-US-AriaNeural"),
]


def extract_voiceover(md_text: str) -> str:
    """Pull every double-quoted span from inside the shot-list table."""
    lines = md_text.splitlines()
    in_table = False
    vos: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("| #") and "Voiceover" in s:
            in_table = True
            continue
        if in_table:
            if s.startswith("|") and not s.startswith("|---"):
                cells = [c.strip() for c in s.split("|")]
                if len(cells) >= 5:
                    vo = cells[4]
                    for m in re.finditer(r'"([^"]+)"', vo):
                        vos.append(m.group(1).strip())
            elif s == "" and not s.startswith("|"):
                in_table = False
    return " ".join(v for v in vos if v)


async def _render_audio_async(text: str, out: Path, voice: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(out))


def render_audio(text: str, out: Path, voice: str) -> None:
    asyncio.run(_render_audio_async(text, out, voice))


def audio_duration_seconds(mp3: Path) -> float:
    """Probe MP3 duration via ffprobe (shipped with imageio-ffmpeg)."""
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # imageio-ffmpeg doesn't ship ffprobe; use ffmpeg with -f null to detect.
    cmd = [ffmpeg, "-i", str(mp3), "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # Duration line example: "  Duration: 00:00:32.40, start: 0.025056, bitrate: 64 kb/s"
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def list_screenshots(d: Path) -> list[Path]:
    return sorted(p for p in d.glob("*.png") if p.is_file())


def render_slideshow_video(
    images: list[Path], audio: Path, out: Path, per_image_seconds: float
) -> None:
    """Build an ffmpeg concat list and render H.264/AAC 1280x720 MP4.

    Each image shows for per_image_seconds, then crossfades to the next
    (well -- here we just hard cut for simplicity). Audio is overlaid
    on top with -shortest so the video matches the audio length.
    """
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    with tempfile.TemporaryDirectory() as tmp:
        # Build the concat demuxer input list.
        listfile = Path(tmp) / "shots.txt"
        lines = []
        for img in images:
            # Escape backslashes for ffmpeg concat format.
            p = str(img).replace("\\", "/")
            lines.append(f"file '{p}'")
            lines.append(f"duration {per_image_seconds:.3f}")
        # The last file must be repeated WITHOUT a duration so the
        # demuxer ends cleanly at the audio end via -shortest.
        last = str(images[-1]).replace("\\", "/")
        lines.append(f"file '{last}'")
        listfile.write_text("\n".join(lines), encoding="utf-8")

        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(listfile),
            "-i", str(audio),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-shortest",
            str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)


def main() -> int:
    n_ok = 0
    for shell_md, screens_subdir, mp3_name, mp4_name, voice in SHELLS:
        src = DOCS / shell_md
        if not src.exists():
            print(f"  skip: {src} not found")
            continue
        screens_dir = SCREENS_BASE / screens_subdir
        images = list_screenshots(screens_dir)
        if not images:
            print(f"  skip: no screenshots in {screens_dir}")
            print(f"        run scripts/screenshot_for_loom.py first")
            continue

        text = src.read_text(encoding="utf-8")
        vo = extract_voiceover(text)
        if not vo:
            print(f"  FAIL: no voiceover extracted from {src.name}")
            continue
        print(f"\n=== {shell_md} ===")
        print(f"  {len(images)} screenshots in {screens_subdir}/")
        print(f"  voiceover ({len(vo)} chars): {vo[:100]}...")

        mp3 = DOCS / mp3_name
        try:
            render_audio(vo, mp3, voice)
            print(f"  wrote: {mp3} ({voice})")
        except Exception as e:
            print(f"  FAIL audio: {type(e).__name__}: {e}")
            continue

        duration = audio_duration_seconds(mp3)
        if duration <= 0:
            print(f"  WARN: could not probe audio duration; using 5s per shot")
            per_image = 5.0
        else:
            # Audio length / number of images = per-image duration.
            # Add a small slack so the last image fades naturally with -shortest.
            per_image = duration / len(images)
            print(f"  audio={duration:.1f}s / {len(images)} shots -> {per_image:.2f}s per shot")

        mp4 = DOCS / mp4_name
        try:
            render_slideshow_video(images, mp3, mp4, per_image)
            print(f"  wrote: {mp4}")
            try:
                shutil.copy2(mp4, DESKTOP / mp4_name)
                print(f"  wrote: {DESKTOP / mp4_name}")
            except Exception:
                pass
            n_ok += 1
        except subprocess.CalledProcessError as e:
            print(f"  FAIL video: ffmpeg returned {e.returncode}")
            print(f"  stderr: {(e.stderr or '')[:600]}")
        except Exception as e:
            print(f"  FAIL video: {type(e).__name__}: {e}")

    print(f"\n=== Done: {n_ok}/{len(SHELLS)} Loom MP4s built ===")
    return 0 if n_ok == len(SHELLS) else 1


if __name__ == "__main__":
    sys.exit(main())
