"""Piper local text-to-speech provider tool."""

from __future__ import annotations

import shutil
import subprocess
import sys
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

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_VOICE_DIR = REPO_ROOT / "models" / "piper"
DEFAULT_CHINESE_VOICE = "zh_CN-huayan-medium"
DEFAULT_ENGLISH_VOICE = "en_US-lessac-medium"


def extra_piper_paths() -> list[Path]:
    """Piper binaries that shutil.which may miss (venv without PATH)."""
    exe_dir = Path(sys.executable).resolve().parent
    return [
        exe_dir / "piper",
        exe_dir / "piper.exe",
        REPO_ROOT / ".venv" / "bin" / "piper",
        REPO_ROOT / ".venv" / "Scripts" / "piper.exe",
    ]


def find_piper() -> str | None:
    """Return the Piper CLI path, or None if it is not installed."""
    which = shutil.which("piper")
    if which:
        return which
    for candidate in extra_piper_paths():
        if candidate.is_file():
            return str(candidate)
    return None


def voice_dir() -> Path:
    return DEFAULT_VOICE_DIR


def voice_model_path(model: str) -> Path:
    name = model.strip()
    if name.endswith(".onnx"):
        return Path(name).expanduser()
    return voice_dir() / f"{name}.onnx"


def ensure_voice(model: str) -> Path:
    """Download a Piper voice onnx into models/piper/ if missing."""
    dest = voice_model_path(model)
    sidecar = Path(str(dest) + ".json")
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    from piper.download_voices import download_voice

    download_voice(Path(model).stem if model.endswith(".onnx") else model, dest.parent)
    if not dest.exists():
        raise FileNotFoundError(f"Piper voice download did not create {dest}")
    if not sidecar.exists():
        alt = dest.with_suffix(".onnx.json")
        if not alt.exists():
            raise FileNotFoundError(f"Piper voice config missing next to {dest}")
    return dest


class PiperTTS(BaseTool):
    name = "piper_tts"
    version = "0.2.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "piper"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:piper"]
    install_instructions = (
        "Install Piper TTS:\n"
        "  pip install piper-tts\n"
        "Then download a voice (Chinese default for VideoMaker):\n"
        "  python -m piper.download_voices zh_CN-huayan-medium --download-dir models/piper"
    )
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline narration fallback",
        "zero-cost Chinese explainer narration",
        "privacy-sensitive local-only workflows",
    ]
    not_good_for = [
        "best-in-class expressive voice quality",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "model": {
                "type": "string",
                "default": DEFAULT_CHINESE_VOICE,
            },
            "speaker_id": {
                "type": "integer",
                "default": 0,
            },
            "length_scale": {
                "type": "number",
                "default": 1.0,
            },
            "sentence_silence": {
                "type": "number",
                "default": 0.3,
            },
            "noise_scale": {
                "type": "number",
                "default": 0.667,
            },
            "noise_w_scale": {
                "type": "number",
                "default": 0.8,
            },
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=200, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["text", "model", "speaker_id", "length_scale"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for intelligibility"]

    def get_status(self) -> ToolStatus:
        if find_piper():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Piper TTS not available. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"Local TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        piper_bin = find_piper()
        if not piper_bin:
            raise RuntimeError("Piper executable not found")

        output_path = Path(inputs.get("output_path", "tts_output.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model = inputs.get("model", DEFAULT_CHINESE_VOICE)
        model_file = ensure_voice(model)

        cmd = [
            piper_bin,
            "--model", str(model_file),
            "--data-dir", str(model_file.parent),
            "--length-scale", str(inputs.get("length_scale", 1.0)),
            "--sentence-silence", str(inputs.get("sentence_silence", 0.3)),
            "--noise-scale", str(inputs.get("noise_scale", 0.667)),
            "--noise-w-scale", str(inputs.get("noise_w_scale", 0.8)),
            "--output_file", str(output_path),
        ]
        if "speaker_id" in inputs:
            cmd.extend(["--speaker", str(inputs.get("speaker_id", 0))])

        proc = subprocess.run(
            cmd,
            input=inputs["text"],
            capture_output=True,
            text=True,
            timeout=300,
        )

        if proc.returncode != 0:
            return ToolResult(success=False, error=f"Piper failed (exit {proc.returncode}): {proc.stderr}")
        if not output_path.exists():
            return ToolResult(success=False, error=f"Piper output file missing: {output_path}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "speaker_id": inputs.get("speaker_id", 0),
                "text_length": len(inputs["text"]),
                "output": str(output_path),
                "format": "wav",
            },
            artifacts=[str(output_path)],
            model=model,
        )
