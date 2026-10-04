#!/usr/bin/env python3
"""Check or explicitly install CreatorOS's local faster-whisper runtime."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check or install the local faster-whisper runtime used by CreatorOS video intake."
    )
    parser.add_argument("--creatoros-vault", required=True, help="CreatorOS root containing 04_系统维护/.")
    parser.add_argument("--model", default="small", choices=("tiny", "base", "small", "medium", "large-v3"))
    parser.add_argument("--install", action="store_true", help="Create venv, install faster-whisper, and download the requested model.")
    args = parser.parse_args()

    vault = Path(args.creatoros_vault).expanduser().resolve()
    maintenance = vault / "04_系统维护"
    runner = maintenance / "scripts" / "creator-local-transcribe"
    target = maintenance / ".venvs" / "video-local" / "bin" / "python"
    model_dir = maintenance / ".cache" / "faster-whisper-models" / args.model
    state = {
        "creatoros_vault": str(vault),
        "runner_exists": runner.exists(),
        "runtime_exists": target.exists(),
        "model": args.model,
        "model_cached": model_dir.exists(),
        "ffmpeg_found": bool(shutil.which("ffmpeg")),
    }
    if not args.install:
        state["status"] = "ready" if state["runner_exists"] and state["runtime_exists"] and state["model_cached"] else "needs_install"
        state["next_step"] = "Run again with --install only after approving the dependency and model download."
        emit(state)
        return 0 if state["status"] == "ready" else 2

    if not maintenance.exists() or not runner.exists():
        raise SystemExit("This does not look like a CreatorOS vault: missing 04_系统维护/scripts/creator-local-transcribe")

    venv_dir = target.parents[2]
    if not target.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    subprocess.run([str(target), "-m", "pip", "install", "--upgrade", "pip", "faster-whisper"], check=True)
    model_dir.parent.mkdir(parents=True, exist_ok=True)
    download_code = (
        "from faster_whisper.utils import download_model; "
        f"download_model({args.model!r}, output_dir={str(model_dir)!r}); "
        "print('model_downloaded')"
    )
    subprocess.run([str(target), "-c", download_code], check=True)
    emit({**state, "runtime_exists": True, "model_cached": model_dir.exists(), "status": "installed"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
