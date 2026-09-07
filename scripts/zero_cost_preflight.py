"""VideoMaker zero-cost preflight.

Checks that the overlay is locked to $0 spend, no paid generation API keys
are configured, and the local render stack (Node, FFmpeg, Remotion) exists.
Prints a compact provider menu so an agent can see what is actually free.

    python scripts/zero_cost_preflight.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib.config_model import BudgetMode, OpenMontageConfig
from lib.env_loader import load_env

# Paid / billable generation keys. Empty is required for the $0 overlay.
# Free-tier stock keys (Pexels / Pixabay / Unsplash) are allowed and omitted.
PAID_ENV_KEYS = (
    "FAL_KEY",
    "FAL_AI_API_KEY",
    "MINIMAX_API_KEY",
    "REPLICATE_API_TOKEN",
    "HIGGSFIELD_API_KEY",
    "HIGGSFIELD_API_SECRET",
    "HIGGSFIELD_KEY",
    "KLING_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "ELEVENLABS_API_KEY",
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "DOUBAO_SPEECH_API_KEY",
    "FISH_AUDIO_API_KEY",
    "DASHSCOPE_API_KEY",
    "TENCENT_TOKENHUB_API_KEY",
    "SUNO_API_KEY",
    "ARK_API_KEY",
    "HEYGEN_API_KEY",
    "RUNWAY_API_KEY",
    "VOLC_ACCESSKEY",
    "VOLC_SECRETKEY",
    "ATLASCLOUD_API_KEY",
    "AZURE_SPEECH_KEY",
)

FREE_OPTIONAL_KEYS = (
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "UNSPLASH_ACCESS_KEY",
    "NASA_API_KEY",
)


def _set(name: str) -> bool:
    value = os.environ.get(name, "")
    return bool(value and value.strip())


def _find(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def main() -> int:
    load_env(ROOT)
    errors: list[str] = []
    warnings: list[str] = []

    config = OpenMontageConfig.load(ROOT / "config.yaml")
    print("==> budget")
    print(f"    mode={config.budget.mode.value} total_usd={config.budget.total_usd:.2f}")
    if config.budget.mode != BudgetMode.CAP:
        errors.append("config.yaml budget.mode must be 'cap' for the zero-cost overlay")
    if config.budget.total_usd != 0:
        errors.append(
            f"config.yaml budget.total_usd must be 0.00 (got {config.budget.total_usd})"
        )

    print("==> paid API keys (must be empty)")
    paid_set = [key for key in PAID_ENV_KEYS if _set(key)]
    if paid_set:
        errors.append("paid keys are set (raise budget cap before using them): " + ", ".join(paid_set))
        for key in paid_set:
            print(f"    SET  {key}")
    else:
        print("    none configured")

    free_set = [key for key in FREE_OPTIONAL_KEYS if _set(key)]
    print("==> optional free stock keys")
    if free_set:
        for key in free_set:
            print(f"    SET  {key}")
    else:
        print("    none (Archive.org / NASA / Wikimedia still work without keys)")

    print("==> local binaries")
    node = _find("node", "node.exe")
    npm = _find("npm", "npm.cmd", "npm.exe")
    npx = _find("npx", "npx.cmd", "npx.exe")
    ffmpeg = _find("ffmpeg", "ffmpeg.exe")
    ffprobe = _find("ffprobe", "ffprobe.exe")
    for label, path in (
        ("node", node),
        ("npm", npm),
        ("npx", npx),
        ("ffmpeg", ffmpeg),
        ("ffprobe", ffprobe),
    ):
        print(f"    {label:8} {path or 'MISSING'}")
        if path is None:
            errors.append(f"{label} is not on PATH")

    remotion_modules = ROOT / "remotion-composer" / "node_modules"
    if remotion_modules.is_dir():
        print("    remotion node_modules: present")
    else:
        warnings.append("remotion-composer/node_modules missing — run make setup")
        print("    remotion node_modules: MISSING")

    print("==> piper TTS")
    try:
        from tools.audio.piper_tts import (
            DEFAULT_CHINESE_VOICE,
            PiperTTS,
            ensure_voice,
            find_piper,
        )

        piper_bin = find_piper()
        print(f"    piper    {piper_bin or 'MISSING'}")
        if not piper_bin:
            errors.append("piper CLI not found (install piper-tts in the venv)")
        else:
            voice_path = ensure_voice(DEFAULT_CHINESE_VOICE)
            print(f"    voice    {voice_path}")
            sample = ROOT / "projects" / "_preflight" / "piper-sample.wav"
            sample.parent.mkdir(parents=True, exist_ok=True)
            result = PiperTTS().execute(
                {
                    "text": "天空是蓝色的。",
                    "model": DEFAULT_CHINESE_VOICE,
                    "output_path": str(sample),
                }
            )
            if not result.success:
                errors.append(f"piper sample synthesis failed: {result.error}")
            else:
                probe = subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        str(sample),
                        "-af",
                        "volumedetect",
                        "-f",
                        "null",
                        "-",
                    ],
                    capture_output=True,
                    text=True,
                )
                mean = None
                for line in (probe.stderr or "").splitlines():
                    if "mean_volume" in line:
                        try:
                            mean = float(line.split("mean_volume:")[1].strip().split()[0])
                        except (IndexError, ValueError):
                            mean = None
                print(f"    sample   {sample} mean_volume={mean} dB")
                if mean is None or mean < -45:
                    errors.append(f"piper sample is too quiet (mean_volume={mean})")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"piper preflight failed: {exc}")

    print("==> provider menu (registry)")
    try:
        from tools.tool_registry import registry

        registry.discover()
        summary = registry.provider_menu_summary()
        print(json.dumps(summary, indent=2, ensure_ascii=False)[:8000])
        if len(json.dumps(summary)) > 8000:
            print("    ... truncated ...")
    except Exception as exc:  # noqa: BLE001 — preflight should not crash on missing extras
        warnings.append(f"tool registry discover failed: {exc}")
        print(f"    skipped: {exc}")

    if warnings:
        print("==> warnings")
        for item in warnings:
            print(f"    - {item}")

    if errors:
        print("==> FAIL")
        for item in errors:
            print(f"    - {item}")
        return 1

    print("==> OK — zero-cost overlay is locked; local render stack looks usable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
