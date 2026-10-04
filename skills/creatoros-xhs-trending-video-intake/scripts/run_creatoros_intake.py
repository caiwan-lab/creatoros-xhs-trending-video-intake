#!/usr/bin/env python3
"""Run a caller-supplied CreatorOS intake command serially for video candidates."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Route XHS candidate URLs through an explicit CreatorOS intake command.")
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--intake-command", required=True, help="Command template with {url}; runs without a shell.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=4800)
    parser.add_argument("--caption-probe", choices=("auto", "off"), default="auto")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.delay_seconds < 0 or args.timeout_seconds < 1:
        parser.error("delays must be non-negative and timeout must be positive")

    payload = json.loads(Path(args.candidates).expanduser().read_text(encoding="utf-8"))
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    if not isinstance(candidates, list):
        raise ValueError("candidates.json must contain a candidates list")
    selected = [item for item in candidates if isinstance(item, dict) and item.get("url")][:args.limit]
    output_dir = Path(args.output_dir).expanduser().resolve()
    logs_dir = output_dir / "logs"
    probe_script = Path(__file__).with_name("probe_xhs_spoken_captions.py")
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for index, item in enumerate(selected, start=1):
        values = {"url": str(item.get("url", "")), "title": str(item.get("title", "")), "note_id": str(item.get("note_id", "")), "output_dir": str(output_dir)}
        started_at = utc_now()
        probe: dict[str, Any] | None = None
        try:
            if args.caption_probe == "auto":
                probe_dir = output_dir / "caption-probes" / f"{index:03d}-{values['note_id'] or 'unknown'}"
                probed = subprocess.run([sys.executable, str(probe_script), "--url", values["url"], "--output-dir", str(probe_dir)], text=True, capture_output=True, timeout=120, check=False)
                try:
                    probe = json.loads(probed.stdout)
                except json.JSONDecodeError:
                    probe = {"status": "probe_failed", "decision": "local_asr_required"}
            command = shlex.split(args.intake_command.format(**values))
            if not command:
                raise ValueError("intake command is empty")
            completed = subprocess.run(command, text=True, capture_output=True, timeout=args.timeout_seconds, check=False)
            log_path = logs_dir / f"{index:03d}-{values['note_id'] or 'unknown'}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text((completed.stdout or "") + "\n--- STDERR ---\n" + (completed.stderr or ""), encoding="utf-8")
            results.append({"index": index, "note_id": values["note_id"], "url": values["url"], "title": values["title"], "started_at": started_at, "finished_at": utc_now(), "caption_probe": probe, "status": "done" if completed.returncode == 0 else "failed", "returncode": completed.returncode, "log": str(log_path)})
        except Exception as exc:
            results.append({"index": index, "note_id": values["note_id"], "url": values["url"], "title": values["title"], "started_at": started_at, "finished_at": utc_now(), "status": "failed", "error": str(exc)})
        if index < len(selected) and args.delay_seconds:
            time.sleep(args.delay_seconds)

    manifest = {"generated_at": utc_now(), "attempted_count": len(selected), "done_count": sum(x["status"] == "done" for x in results), "failed_count": sum(x["status"] == "failed" for x in results), "results": results}
    write_json(output_dir / "intake-manifest.json", manifest)
    print(f"output_dir: {output_dir}")
    print(f"done_count: {manifest['done_count']}")
    print(f"failed_count: {manifest['failed_count']}")
    print("status: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
