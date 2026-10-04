#!/usr/bin/env python3
"""Non-mutating preflight for the local XHS discovery and CreatorOS ASR route."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=45)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the public-XHS-to-local-ASR intake environment without installing or downloading.")
    parser.add_argument("--creatoros-vault", required=True)
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    vault = Path(args.creatoros_vault).expanduser().resolve()
    xhs = shutil.which("xhs")
    xhs_authenticated = False
    if xhs:
        xhs_authenticated = run([xhs, "status", "--yaml"]).returncode == 0

    intake = vault / "04_系统维护" / "scripts" / "creator-platform-video-intake.py"
    intake_usable = intake.exists() and run([sys.executable, str(intake), "--help"]).returncode == 0
    setup = Path(__file__).with_name("setup_creatoros_transcription.py")
    asr_check = run([sys.executable, str(setup), "--creatoros-vault", str(vault), "--model", args.model])
    try:
        asr = json.loads(asr_check.stdout)
    except json.JSONDecodeError:
        asr = {"status": "unknown"}

    downloader = vault / "04_系统维护" / "tools" / "video-downloader" / "scripts" / "download_video.py"
    result = {
        "xhs_installed": bool(xhs),
        "xhs_authenticated": xhs_authenticated,
        "creatoros_intake_available": intake_usable,
        "video_downloader_available": downloader.exists(),
        "local_asr_status": asr.get("status", "unknown"),
        "small_model_cached": asr.get("model_cached") if args.model == "small" else None,
    }
    result["status"] = "ready" if all((result["xhs_installed"], result["xhs_authenticated"], result["creatoros_intake_available"], result["video_downloader_available"], result["local_asr_status"] == "ready")) else "needs_attention"
    result["next_step"] = "Safe to run a capped live acceptance batch." if result["status"] == "ready" else "Fix only the false checks; run setup_creatoros_transcription.py --install only after approval."
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
