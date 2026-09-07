"""Microsoft Edge neural TTS via the free ``edge-tts`` package.

No API key. Same YunxiNeural stack used by many Chinese short-video tools.
Needs outbound network. Offline fallback is ``piper_tts``.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

DEFAULT_CHINESE_VOICE = "zh-CN-YunxiNeural"
DEFAULT_RATE = "+10%"
DEFAULT_VOLUME = "+0%"
TICKS_PER_SECOND = 10_000_000
PUNCT_STRIP = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]")


def spoken_chars(text: str) -> str:
    return PUNCT_STRIP.sub("", text)


def looks_truncated(text: str, words: list[dict[str, Any]]) -> bool:
    if not words:
        return True
    org = spoken_chars(text)
    last = spoken_chars(str(words[-1].get("word") or ""))
    if not org or not last:
        return False
    idx = org.rfind(last)
    if idx < 0:
        return True
    leftover = len(org) - (idx + len(last))
    return leftover / len(org) > 0.015


def _mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to convert Edge TTS mp3 to wav")
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(mp3_path),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg mp3→wav failed: {proc.stderr[-400:]}")


async def _stream_tts(
    text: str,
    voice: str,
    rate: str,
    volume: str,
    mp3_path: Path,
) -> list[dict[str, Any]]:
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate,
        volume=volume,
        boundary="WordBoundary",
    )
    words: list[dict[str, Any]] = []
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    with mp3_path.open("wb") as fh:
        async for chunk in communicate.stream():
            kind = chunk.get("type")
            if kind == "audio":
                fh.write(chunk["data"])
            elif kind == "WordBoundary":
                offset = float(chunk.get("offset") or 0) / TICKS_PER_SECOND
                duration = float(chunk.get("duration") or 0) / TICKS_PER_SECOND
                token = str(chunk.get("text") or "")
                if token.strip():
                    words.append(
                        {
                            "word": token,
                            "start": round(offset, 3),
                            "end": round(offset + max(duration, 0.04), 3),
                        }
                    )
    return words


class EdgeTTS(BaseTool):
    name = "edge_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "edge"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.HYBRID

    dependencies = ["python:edge_tts", "cmd:ffmpeg"]
    install_instructions = (
        "Install the free Microsoft Edge TTS client:\n"
        "  pip install edge-tts\n"
        "Needs outbound network. No API key. Default Chinese voice: zh-CN-YunxiNeural."
    )
    fallback = "piper_tts"
    fallback_tools = ["piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "word_timestamps",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "word_timestamps": True,
    }
    best_for = [
        "zero-cost Chinese explainer narration",
        "marketing-style short-video voiceover",
        "WordBoundary captions without a paid TTS key",
    ]
    not_good_for = [
        "fully offline production",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "voice": {
                "type": "string",
                "default": DEFAULT_CHINESE_VOICE,
            },
            "model": {
                "type": "string",
                "description": "Alias for voice (zh-CN-YunxiNeural).",
            },
            "rate": {
                "type": "string",
                "default": DEFAULT_RATE,
                "description": "Edge TTS rate, e.g. +10% or -5%.",
            },
            "volume": {
                "type": "string",
                "default": DEFAULT_VOLUME,
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=20, network_required=True
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["Timeout", "403", "connection"])
    idempotency_key_fields = ["text", "voice", "rate", "volume"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for intelligibility"]

    def get_status(self) -> ToolStatus:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return ToolStatus.UNAVAILABLE
        if not shutil.which("ffmpeg"):
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(
                success=False,
                error="Edge TTS is not available. " + self.install_instructions,
            )

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"Edge TTS generation failed: {exc}")
        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        text = str(inputs.get("text") or "").strip()
        if not text:
            return ToolResult(success=False, error="text is required")

        output_path = Path(inputs.get("output_path", "tts_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        voice = str(inputs.get("voice") or inputs.get("model") or DEFAULT_CHINESE_VOICE)
        rate = str(inputs.get("rate") or DEFAULT_RATE)
        volume = str(inputs.get("volume") or DEFAULT_VOLUME)

        mp3_path = output_path.with_suffix(".mp3")
        words = asyncio.run(_stream_tts(text, voice, rate, volume, mp3_path))
        if looks_truncated(text, words):
            words = asyncio.run(_stream_tts(text, voice, rate, volume, mp3_path))

        if not mp3_path.exists() or mp3_path.stat().st_size == 0:
            return ToolResult(success=False, error=f"Edge TTS wrote no audio: {mp3_path}")

        if output_path.suffix.lower() in {".wav", ".flac"}:
            _mp3_to_wav(mp3_path, output_path)
            artifact = output_path
        else:
            if output_path.suffix.lower() != ".mp3":
                shutil.copy2(mp3_path, output_path)
                artifact = output_path
            else:
                artifact = mp3_path

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "voice": voice,
                "rate": rate,
                "volume": volume,
                "text_length": len(text),
                "output": str(artifact),
                "format": artifact.suffix.lstrip(".") or "mp3",
                "word_timestamps": words,
            },
            artifacts=[str(artifact)],
            model=voice,
        )
