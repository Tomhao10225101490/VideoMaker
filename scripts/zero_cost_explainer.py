"""Render a 60-120s zero-cost Chinese explainer with audible narration.

    python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json

Uses Piper TTS (offline), Remotion Explainer scenes, optional Pixabay BGM.
No paid API keys. Output: projects/<id>/renders/final.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.audio.piper_tts import (  # noqa: E402
    DEFAULT_CHINESE_VOICE,
    PiperTTS,
    ensure_voice,
    find_piper,
)

COMPOSER_DIR = ROOT / "remotion-composer"
PUBLIC_DIR = COMPOSER_DIR / "public"
PUNCT_BREAK = set("。！？")
PUNCT_LIGHT = set("，、；：")


def find_command(*names: str) -> str | None:
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(proc.stdout.strip())


def mean_volume_db(path: Path) -> float | None:
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    for line in (proc.stderr or "").splitlines():
        if "mean_volume" in line:
            # mean_volume: -13.6 dB
            try:
                return float(line.split("mean_volume:")[1].strip().split()[0])
            except (IndexError, ValueError):
                return None
    return None


def concat_wavs(parts: list[Path], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = dest.with_suffix(".concat.txt")
    list_path.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in parts),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def captions_for_text(text: str, start_s: float, end_s: float) -> list[dict[str, Any]]:
    chars = list(text)
    weights = []
    for ch in chars:
        if ch in PUNCT_BREAK:
            weights.append(0.45)
        elif ch in PUNCT_LIGHT:
            weights.append(0.3)
        elif ch.strip():
            weights.append(1.0)
        else:
            weights.append(0.2)
    total_w = sum(weights) or 1.0
    span = max(end_s - start_s, 0.05)
    acc = 0.0
    captions: list[dict[str, Any]] = []
    for ch, weight in zip(chars, weights):
        dur = span * (weight / total_w)
        captions.append(
            {
                "word": ch,
                "startMs": int(round((start_s + acc) * 1000)),
                "endMs": int(round((start_s + acc + dur) * 1000)),
                "pageBreakAfter": ch in PUNCT_BREAK,
            }
        )
        acc += dur
    return captions


def try_music(query: str, dest: Path) -> Path | None:
    try:
        from tools.audio.pixabay_music import PixabayMusic

        dest.parent.mkdir(parents=True, exist_ok=True)
        result = PixabayMusic().execute(
            {
                "query": query,
                "min_duration": 60,
                "max_duration": 180,
                "output_path": str(dest),
            }
        )
        if result.success and dest.exists() and dest.stat().st_size > 0:
            print(f"    music: {dest} ({result.data})")
            return dest
        print(f"    music skipped: {result.error}")
    except Exception as exc:  # noqa: BLE001
        print(f"    music skipped: {exc}")
    return None


def synthesize_segments(
    segments: list[dict[str, Any]],
    work_dir: Path,
    voice: str,
    length_scale: float,
    sentence_silence: float,
) -> tuple[Path, list[tuple[float, float]], list[dict[str, Any]]]:
    tts = PiperTTS()
    if tts.get_status().value != "available":
        raise SystemExit("Piper TTS is not available. Run make setup and install piper-tts.")
    ensure_voice(voice)

    parts: list[Path] = []
    spans: list[tuple[float, float]] = []
    captions: list[dict[str, Any]] = []
    cursor = 0.0
    for index, segment in enumerate(segments):
        text = str(segment["narration"]).strip()
        wav_path = work_dir / "tts" / f"{index:02d}-{segment['id']}.wav"
        result = tts.execute(
            {
                "text": text,
                "model": voice,
                "output_path": str(wav_path),
                "length_scale": length_scale,
                "sentence_silence": sentence_silence,
            }
        )
        if not result.success:
            raise SystemExit(f"Piper failed on segment {segment['id']}: {result.error}")
        duration = probe_duration(wav_path)
        start, end = cursor, cursor + duration
        spans.append((start, end))
        captions.extend(captions_for_text(text, start, end))
        parts.append(wav_path)
        print(f"    tts {segment['id']}: {duration:.2f}s  {text[:24]}…")
        cursor = end

    narration = work_dir / "narration.wav"
    concat_wavs(parts, narration)
    volume = mean_volume_db(narration)
    print(f"    narration {narration}  duration={probe_duration(narration):.2f}s  mean_volume={volume}")
    if volume is None or volume < -45:
        raise SystemExit(f"Narration looks too quiet (mean_volume={volume} dB)")
    return narration, spans, captions


def build_props(
    spec: dict[str, Any],
    spans: list[tuple[float, float]],
    captions: list[dict[str, Any]],
    narration_public: str,
    music_public: str | None,
) -> dict[str, Any]:
    cuts = []
    for segment, (start, end) in zip(spec["segments"], spans):
        cut = dict(segment.get("cut") or {})
        cut["id"] = segment["id"]
        cut["source"] = cut.get("source", "")
        cut["in_seconds"] = round(start, 3)
        cut["out_seconds"] = round(end, 3)
        cuts.append(cut)

    audio: dict[str, Any] = {
        "narration": {"src": narration_public, "volume": 1.0},
    }
    if music_public:
        audio["music"] = {
            "src": music_public,
            "volume": 0.1,
            "fadeInSeconds": 1.5,
            "fadeOutSeconds": 2.5,
            "loop": True,
        }

    return {
        "theme": spec.get("theme", "flat-motion-graphics"),
        "cuts": cuts,
        "overlays": spec.get("overlays", []),
        "captions": captions,
        "captionWordSeparator": spec.get("caption_word_separator", ""),
        "captionWordsPerPage": spec.get("caption_words_per_page", 12),
        "audio": audio,
    }


def stage_public(project_id: str, narration: Path, music: Path | None) -> tuple[str, str | None]:
    dest_dir = PUBLIC_DIR / "zero-cost" / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    nar_name = "narration.wav"
    shutil.copy2(narration, dest_dir / nar_name)
    music_rel = None
    if music and music.exists():
        ext = music.suffix or ".mp3"
        music_name = f"music{ext}"
        shutil.copy2(music, dest_dir / music_name)
        music_rel = f"zero-cost/{project_id}/{music_name}"
    return f"zero-cost/{project_id}/{nar_name}", music_rel


def render_explainer(props_path: Path, output_path: Path) -> None:
    npx = find_command("npx", "npx.cmd", "npx.exe")
    if not npx:
        raise SystemExit("npx is required to render with Remotion")
    if not (COMPOSER_DIR / "node_modules").exists():
        raise SystemExit("remotion-composer/node_modules missing — run make setup")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            npx,
            "remotion",
            "render",
            "src/index.tsx",
            "Explainer",
            str(output_path),
            "--props",
            str(props_path),
            "--codec",
            "h264",
        ],
        cwd=COMPOSER_DIR,
        check=True,
    )


def verify_output(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Render produced no file: {path}")
    duration = probe_duration(path)
    volume = mean_volume_db(path)
    print(f"==> output {path}  duration={duration:.2f}s  mean_volume={volume} dB  size={path.stat().st_size}")
    if duration < 50:
        raise SystemExit(f"Video too short for a 1-2 minute explainer template: {duration:.1f}s")
    if volume is None or volume < -45:
        raise SystemExit(f"Final video still sounds silent (mean_volume={volume} dB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-cost Chinese explainer with Piper narration")
    parser.add_argument(
        "spec",
        nargs="?",
        default=str(ROOT / "fixtures" / "zero-cost" / "why-sky-is-blue.json"),
        help="Project JSON (segments + Remotion cuts)",
    )
    parser.add_argument("--skip-music", action="store_true")
    parser.add_argument("--no-render", action="store_true", help="Write props and audio only")
    args = parser.parse_args()

    spec_path = Path(args.spec).resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project_id = spec["id"]
    voice = spec.get("voice", DEFAULT_CHINESE_VOICE)
    work_dir = ROOT / "projects" / project_id
    work_dir.mkdir(parents=True, exist_ok=True)

    print("==> zero-cost explainer")
    print(f"    spec={spec_path}")
    print(f"    piper={find_piper()}")
    print(f"    voice={voice}")

    narration, spans, captions = synthesize_segments(
        spec["segments"],
        work_dir,
        voice=voice,
        length_scale=float(spec.get("length_scale", 1.08)),
        sentence_silence=float(spec.get("sentence_silence", 0.28)),
    )
    total = spans[-1][1] if spans else 0
    print(f"    total narration {total:.1f}s  captions={len(captions)}")

    music_path = None
    if not args.skip_music and spec.get("music_query"):
        music_path = try_music(spec["music_query"], work_dir / "music.mp3")

    narration_rel, music_rel = stage_public(project_id, narration, music_path)
    props = build_props(spec, spans, captions, narration_rel, music_rel)
    props_path = work_dir / "explainer-props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    public_props = PUBLIC_DIR / "zero-cost" / project_id / "explainer-props.json"
    public_props.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(props_path, public_props)
    print(f"    props {props_path}")

    output_path = work_dir / "renders" / "final.mp4"
    if args.no_render:
        print("    skip render (--no-render)")
        return 0

    render_explainer(props_path, output_path)
    verify_output(output_path)
    print("==> OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
