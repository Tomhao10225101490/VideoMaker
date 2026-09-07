"""loudnorm leaves FFmpeg graphs at 192 kHz unless we resample.

Chromium / Safari / Remotion <Audio> commonly fail to decode 192 kHz WAV,
so the delivered video looks silent even though ffmpeg volumedetect hears it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tools.audio.audio_enhance import (
    PLAYBACK_SAMPLE_RATE,
    AudioEnhance,
    _with_playback_rate,
)


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _probe_rate(path: Path) -> int:
    return int(
        subprocess.run(
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
            timeout=30,
        ).stdout.strip()
    )


def test_with_playback_rate_resamples_loudnorm() -> None:
    af = "highpass=f=80,loudnorm=I=-16:LRA=11:TP=-1.5"
    out = _with_playback_rate(af, 48000)
    assert out.endswith(",aresample=48000")
    assert _with_playback_rate(out, 48000) == out


def test_with_playback_rate_skips_filters_without_loudnorm() -> None:
    af = "highpass=f=80,lowpass=f=8000"
    assert _with_playback_rate(af, 48000) == af


def test_voice_clarity_does_not_emit_192khz(tmp_path: Path) -> None:
    src = tmp_path / "speech-24k.wav"
    dest = tmp_path / "enhanced.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.4:sample_rate=24000",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    # Control: raw loudnorm without aresample stays at 192 kHz.
    raw = tmp_path / "loudnorm-raw.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-af",
            "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-c:a",
            "pcm_s16le",
            str(raw),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    assert _probe_rate(raw) == 192000

    result = AudioEnhance().execute(
        {
            "input_path": str(src),
            "output_path": str(dest),
            "preset": "voice_clarity",
            "audio_codec": "pcm_s16le",
        }
    )
    assert result.success, result.error
    assert dest.is_file()
    assert _probe_rate(dest) == PLAYBACK_SAMPLE_RATE
    assert result.data["sample_rate"] == PLAYBACK_SAMPLE_RATE


def _load_explainer():
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "zero_cost_explainer",
        root / "scripts" / "zero_cost_explainer.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mux_narration_writes_web_safe_aac(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    wav = tmp_path / "voice.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=blue:s=320x180:d=1.5:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=1:sample_rate=24000",
            str(wav),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    _load_explainer().mux_narration_into_video(video, wav)
    assert _probe_rate(video) == 48000
    streams = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_name,codec_type", "-of", "csv=p=0", str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    assert "aac" in streams
    assert "h264" in streams
