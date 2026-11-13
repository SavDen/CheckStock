"""Build a narrated walkthrough from real UI captures. macOS say + optional imageio-ffmpeg.

Install optional tooling: pip install imageio-ffmpeg==0.6.0
Run: python scripts/build_demo.py
No browser automation or fabricated UI states are used here.
"""

import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local" / "video"
OUT = ROOT / "deliverables"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def run(*args):
    subprocess.run(
        [str(x) for x in args], check=True, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)
    scenes = json.loads((ROOT / "docs/demo.json").read_text())
    subtitles, narration, durations = [], [], []
    elapsed = 0
    for i, scene in enumerate(scenes, 1):
        textfile = WORK / f"{i:02d}.txt"
        titlefile = WORK / f"{i:02d}-title.txt"
        audio = WORK / f"{i:02d}.aiff"
        clip = WORK / f"{i:02d}.mp4"
        textfile.write_text(scene["text"])
        titlefile.write_text(scene["title"])
        run("say", "-v", "Milena", "-r", "185", "-f", textfile, "-o", audio)
        probe = subprocess.run([FFMPEG, "-i", str(audio)], capture_output=True, text=True)
        h, m, s = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe.stderr).groups()
        duration = int(h) * 3600 + int(m) * 60 + float(s) + 1
        durations.append(duration)
        vf = (
            "scale=1440:1000:force_original_aspect_ratio=decrease,"
            "pad=1440:1080:(ow-iw)/2:0:color=0x173c32,"
            f"drawtext=fontfile='{ROOT / 'app/static/fonts/Onest.ttf'}':textfile='{titlefile}':"
            "fontsize=21:fontcolor=white:x=28:y=1026"
        )
        run(
            FFMPEG,
            "-y",
            "-loop",
            "1",
            "-framerate",
            "10",
            "-i",
            ROOT / scene["frame"],
            "-i",
            audio,
            "-vf",
            vf,
            "-af",
            "apad",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-b:a",
            "128k",
            clip,
        )
        # Short subtitle chunks track the narration approximately within each scene.
        chunks, chunk = [], ""
        for sentence in re.split(r"(?<=[.!?])\s+", scene["text"]):
            if len(chunk) + len(sentence) > 160 and chunk:
                chunks.append(chunk)
                chunk = ""
            chunk += (" " if chunk else "") + sentence
        if chunk:
            chunks.append(chunk)
        total_chars = sum(map(len, chunks))
        cursor = elapsed
        for chunk in chunks:
            end = cursor + (duration - 1) * len(chunk) / total_chars
            subtitles.append(f"{len(subtitles) + 1}\n{timestamp(cursor)} --> {timestamp(end)}\n{chunk}\n")
            cursor = end
        narration.append(f"{timestamp(elapsed)} — {scene['title']}\n\n{scene['text']}\n")
        elapsed += duration
        print(f"Scene {i}/{len(scenes)}: {duration:.1f}s", flush=True)
    concat = WORK / "clips.txt"
    concat.write_text("\n".join(f"file '{WORK / f'{i:02d}.mp4'}'" for i in range(1, len(scenes) + 1)))
    srt = OUT / "checkstock-demo.srt"
    srt.write_text("\n".join(subtitles))
    (ROOT / "docs/narration.txt").write_text(
        "Демонстрационный обзор. Синтезированная озвучка Milena.\n\n" + "\n".join(narration)
    )
    run(
        FFMPEG,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat,
        "-i",
        srt,
        "-map",
        "0:v",
        "-map",
        "0:a",
        "-map",
        "1:0",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=rus",
        "-metadata",
        "title=CheckStock — демонстрационный обзор",
        "-metadata",
        "comment=Real UI captures, synthetic Russian narration (Milena). Not a personal candidate recording.",
        "-movflags",
        "+faststart",
        OUT / "checkstock-demo.mp4",
    )
    (WORK / "timings.json").write_text(json.dumps({"duration": elapsed, "scenes": durations}))
    print(f"Video ready: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
