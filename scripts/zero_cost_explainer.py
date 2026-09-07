"""Render a 60-120s zero-cost Chinese explainer with audible narration.

    python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json

Uses Piper TTS (offline), Remotion Explainer scenes, optional Pixabay BGM.
No paid API keys. Output: projects/<id>/renders/final.mp4
"""

from __future__ import annotations

import argparse
import json
import re
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
PUNCT_STRIP = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")
HOOK_SEGMENT_IDS = {"hook"}
PAD_EXCLAIM_S = 0.18
PAD_PERIOD_S = 0.12
HOOK_LENGTH_SCALE = 0.88
PER_SENTENCE_SILENCE = 0.04


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


def probe_sample_rate(path: Path) -> int:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(float(proc.stdout.strip()))


def concat_wavs(parts: list[Path], dest: Path, sample_rate: int = 22050) -> None:
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
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )


def make_silence(path: Path, seconds: float, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r={sample_rate}:cl=mono",
            "-t",
            f"{max(seconds, 0.02):.3f}",
            "-acodec",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def split_sentences(text: str) -> list[str]:
    buf: list[str] = []
    sentences: list[str] = []
    for ch in text.strip():
        buf.append(ch)
        if ch in PUNCT_BREAK:
            piece = "".join(buf).strip()
            if piece:
                sentences.append(piece)
            buf = []
    leftover = "".join(buf).strip()
    if leftover:
        sentences.append(leftover)
    return sentences


def spoken_chars(text: str) -> str:
    return PUNCT_STRIP.sub("", text)


def looks_truncated(text: str, duration: float, length_scale: float) -> bool:
    n = len(spoken_chars(text))
    if n < 4:
        return duration < 0.12
    expected = (n / 4.5) * length_scale
    return duration < expected * 0.45


def sentence_length_scale(segment_id: str, sentence: str, base: float) -> float:
    if segment_id in HOOK_SEGMENT_IDS or sentence.endswith(("！", "？")):
        return min(base, HOOK_LENGTH_SCALE)
    return base


def pad_after_sentence(sentence: str) -> float:
    if sentence.endswith(("！", "？")):
        return PAD_EXCLAIM_S
    if sentence.endswith("。"):
        return PAD_PERIOD_S
    return PAD_PERIOD_S


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


def captions_from_word_timestamps(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for item in words:
        raw = str(item.get("word") or "")
        start = float(item.get("start") or 0.0)
        end = float(item.get("end") or start)
        tokens = [ch for ch in raw if not ch.isspace()]
        if not tokens:
            continue
        span = max(end - start, 0.04)
        step = span / len(tokens)
        for i, ch in enumerate(tokens):
            captions.append(
                {
                    "word": ch,
                    "startMs": int(round((start + i * step) * 1000)),
                    "endMs": int(round((start + (i + 1) * step) * 1000)),
                    "pageBreakAfter": ch in PUNCT_BREAK,
                }
            )
    return captions


def align_captions_with_whisper(
    narration: Path,
    fallback: list[dict[str, Any]],
    source_text: str,
) -> list[dict[str, Any]]:
    try:
        from tools.analysis.transcriber import Transcriber

        result = Transcriber().execute(
            {
                "input_path": str(narration),
                "language": "zh",
                "model_size": "base",
                "output_dir": str(narration.parent),
            }
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    captions whisper skipped: {exc}")
        return fallback
    if not result.success:
        print(f"    captions whisper skipped: {result.error}")
        return fallback
    words = result.data.get("word_timestamps") or []
    aligned = captions_from_word_timestamps(words)
    got = len(spoken_chars("".join(c["word"] for c in aligned)))
    need = len(spoken_chars(source_text))
    if not aligned or (need >= 20 and got < need * 0.7):
        print(f"    captions whisper too thin ({got}/{need} chars), using duration split")
        return fallback
    print(f"    captions whisper words={len(words)} chars={got}")
    return aligned


def enhance_narration(narration: Path) -> Path:
    try:
        from tools.audio.audio_enhance import AudioEnhance

        enhanced = narration.with_name("narration_enhanced.wav")
        result = AudioEnhance().execute(
            {
                "input_path": str(narration),
                "output_path": str(enhanced),
                "preset": "voice_clarity",
                "audio_codec": "pcm_s16le",
            }
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    enhance skipped: {exc}")
        return narration
    if not result.success or not enhanced.exists() or enhanced.stat().st_size == 0:
        print(f"    enhance skipped: {getattr(result, 'error', 'missing output')}")
        return narration
    print(f"    enhance voice_clarity → {enhanced}")
    return enhanced


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


def synthesize_sentence(
    tts: PiperTTS,
    text: str,
    wav_path: Path,
    voice: str,
    length_scale: float,
    noise_scale: float,
    noise_w_scale: float,
) -> float:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": text,
        "model": voice,
        "output_path": str(wav_path),
        "length_scale": length_scale,
        "sentence_silence": PER_SENTENCE_SILENCE,
        "noise_scale": noise_scale,
        "noise_w_scale": noise_w_scale,
    }
    result = tts.execute(payload)
    if not result.success:
        raise SystemExit(f"Piper failed: {result.error}")
    duration = probe_duration(wav_path)
    if looks_truncated(text, duration, length_scale):
        print(f"    tts retry (short {duration:.2f}s): {text[:18]}…")
        result = tts.execute(payload)
        if not result.success:
            raise SystemExit(f"Piper retry failed: {result.error}")
        duration = probe_duration(wav_path)
    return duration


def synthesize_segments(
    segments: list[dict[str, Any]],
    work_dir: Path,
    voice: str,
    length_scale: float,
    sentence_silence: float,
    noise_scale: float = 0.667,
    noise_w_scale: float = 0.8,
) -> tuple[Path, list[tuple[float, float]], list[dict[str, Any]]]:
    del sentence_silence  # per-sentence pads replace Piper's paragraph silence
    tts = PiperTTS()
    if tts.get_status().value != "available":
        raise SystemExit("Piper TTS is not available. Run make setup and install piper-tts.")
    ensure_voice(voice)

    tts_dir = work_dir / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    parts: list[Path] = []
    spans: list[tuple[float, float]] = []
    captions: list[dict[str, Any]] = []
    cursor = 0.0
    sample_rate = 22050
    silence_index = 0
    total_sentences = sum(len(split_sentences(str(seg["narration"]))) for seg in segments)
    rendered = 0

    for index, segment in enumerate(segments):
        text = str(segment["narration"]).strip()
        sentences = split_sentences(text) or [text]
        seg_start = cursor
        for sent_i, sentence in enumerate(sentences):
            scale = sentence_length_scale(str(segment["id"]), sentence, length_scale)
            wav_path = tts_dir / f"{index:02d}-{segment['id']}-{sent_i:02d}.wav"
            duration = synthesize_sentence(
                tts,
                sentence,
                wav_path,
                voice=voice,
                length_scale=scale,
                noise_scale=noise_scale,
                noise_w_scale=noise_w_scale,
            )
            if not parts:
                try:
                    sample_rate = probe_sample_rate(wav_path)
                except (ValueError, subprocess.CalledProcessError):
                    sample_rate = 22050
            captions.extend(captions_for_text(sentence, cursor, cursor + duration))
            parts.append(wav_path)
            cursor += duration
            rendered += 1
            is_last = rendered >= total_sentences
            if not is_last:
                pad = pad_after_sentence(sentence)
                silence_path = tts_dir / f"silence-{silence_index:03d}.wav"
                make_silence(silence_path, pad, sample_rate)
                parts.append(silence_path)
                cursor += pad
                silence_index += 1
        spans.append((seg_start, cursor))
        print(f"    tts {segment['id']}: {cursor - seg_start:.2f}s  {text[:24]}…")

    narration = work_dir / "narration.wav"
    concat_wavs(parts, narration, sample_rate=sample_rate)
    volume = mean_volume_db(narration)
    print(f"    narration {narration}  duration={probe_duration(narration):.2f}s  mean_volume={volume}")
    if volume is None or volume < -45:
        raise SystemExit(f"Narration looks too quiet (mean_volume={volume} dB)")
    return narration, spans, captions


def overlays_from_spec(
    spec: dict[str, Any],
    spans: list[tuple[float, float]],
) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    for segment, (start, end) in zip(spec["segments"], spans):
        raw = segment.get("overlay")
        if not raw:
            continue
        item = dict(raw)
        delay = float(item.pop("delay_seconds", 0.12))
        pad = float(item.pop("end_pad_seconds", 0.05))
        item["in_seconds"] = round(start + delay, 3)
        item["out_seconds"] = round(max(item["in_seconds"] + 0.4, end - pad), 3)
        overlays.append(item)
    overlays.extend(spec.get("overlays") or [])
    return overlays


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

    props: dict[str, Any] = {
        "theme": spec.get("theme", "flat-motion-graphics"),
        "cuts": cuts,
        "overlays": overlays_from_spec(spec, spans),
        "captions": captions,
        "captionWordSeparator": spec.get("caption_word_separator", ""),
        "captionWordsPerPage": spec.get("caption_words_per_page", 8),
        "audio": audio,
        "motionEnergy": spec.get("motion_energy", "high"),
    }
    if spec.get("particles"):
        props["particles"] = spec["particles"]
    return props


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

    narration, spans, fallback_captions = synthesize_segments(
        spec["segments"],
        work_dir,
        voice=voice,
        length_scale=float(spec.get("length_scale", 0.92)),
        sentence_silence=float(spec.get("sentence_silence", 0.12)),
        noise_scale=float(spec.get("noise_scale", 0.85)),
        noise_w_scale=float(spec.get("noise_w_scale", 0.95)),
    )
    raw_end = spans[-1][1] if spans else 0.0
    narration = enhance_narration(narration)
    enhanced_dur = probe_duration(narration)
    if raw_end > 0 and abs(enhanced_dur - raw_end) > 0.08:
        ratio = enhanced_dur / raw_end
        spans = [(s * ratio, e * ratio) for s, e in spans]
        for cue in fallback_captions:
            cue["startMs"] = int(round(cue["startMs"] * ratio))
            cue["endMs"] = int(round(cue["endMs"] * ratio))
        print(f"    enhance duration {raw_end:.2f}s → {enhanced_dur:.2f}s, scaled timeline")
    source_text = "".join(str(seg["narration"]) for seg in spec["segments"])
    captions = align_captions_with_whisper(narration, fallback_captions, source_text)
    total = spans[-1][1] if spans else 0
    print(f"    total narration {enhanced_dur:.1f}s  scene_span={total:.1f}s  captions={len(captions)}")

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
