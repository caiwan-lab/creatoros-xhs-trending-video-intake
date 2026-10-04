#!/usr/bin/env python3
"""Probe a public XHS note for a structured spoken-caption track, never post text."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACK_KEYS = {"subtitle_tracks", "caption_tracks", "subtitles", "subtitle_list", "caption_list"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_track(value: Any, trail: str = "") -> tuple[str, list[dict[str, Any]]] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{trail}.{key}" if trail else key
            if key in TRACK_KEYS and isinstance(child, list):
                usable = [item for item in child if isinstance(item, dict) and (item.get("text") or item.get("content"))]
                if usable:
                    return here, usable
            found = find_track(child, here)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = find_track(child, f"{trail}[{index}]")
            if found:
                return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Find structured XHS spoken-caption tracks; never treats post body as transcript.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--xhs-bin", default="xhs")
    parser.add_argument("--input-json", help="Offline fixture: skip live xhs read.")
    args = parser.parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.input_json:
        payload = json.loads(Path(args.input_json).expanduser().read_text(encoding="utf-8"))
    else:
        completed = subprocess.run([args.xhs_bin, "read", args.url, "--json"], text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            result = {"checked_at": utc_now(), "url": args.url, "status": "read_failed", "decision": "local_asr_required", "error": (completed.stderr or completed.stdout or "xhs read failed").strip()[-500:]}
            (output_dir / "caption-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False))
            return 0
        payload = json.loads(completed.stdout)

    (output_dir / "xhs-read.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    found = find_track(payload)
    if found:
        trail, items = found
        result = {"checked_at": utc_now(), "url": args.url, "status": "structured_caption_track_found", "decision": "caption_adapter_required", "track_location": trail, "segment_count": len(items), "note": "A structured track was found, but this public Skill has no verified XHS caption-download adapter yet. Do not substitute post text; preserve this probe and use local ASR until an adapter is verified."}
    else:
        result = {"checked_at": utc_now(), "url": args.url, "status": "no_structured_caption_track", "decision": "local_asr_required", "note": "Visible post text is not treated as spoken captions."}
    (output_dir / "caption-probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
