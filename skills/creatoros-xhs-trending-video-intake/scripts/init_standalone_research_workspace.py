#!/usr/bin/env python3
"""Create a portable, source-preserving research workspace when CreatorOS is absent."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-.")
    return (cleaned or "未命名主题")[:56]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a standalone Xiaohongshu video research batch outside CreatorOS."
    )
    parser.add_argument("--topic", required=True, help="Human-readable research topic used in the batch name.")
    parser.add_argument(
        "--root",
        default=str(Path.home() / "Documents" / "CreatorOS-Research"),
        help="Parent folder for standalone batches (default: ~/Documents/CreatorOS-Research).",
    )
    parser.add_argument("--date", default=date.today().isoformat(), help="Batch date, YYYY-MM-DD.")
    parser.add_argument("--reuse", action="store_true", help="Reuse an existing matching batch folder.")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    batch = root / "小红书爆款研究" / f"{args.date}-{safe_name(args.topic)}"
    if batch.exists() and not args.reuse:
        parser.error(f"Batch already exists: {batch}. Pass --reuse only when resuming this exact batch.")

    for relative in (
        "00_原始搜索",
        "01_候选与报告",
        "02_逐字稿",
        "03_分析草稿",
        "临时媒体",
        "logs",
    ):
        (batch / relative).mkdir(parents=True, exist_ok=True)

    manifest_path = batch / "research-manifest.json"
    if not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "topic": args.topic,
                    "mode": "standalone_without_creatoros",
                    "media_retention": {
                        "temporary_folder": "临时媒体",
                        "delete_after": "a verified local transcript is saved in 02_逐字稿",
                        "never_delete": ["00_原始搜索", "01_候选与报告", "02_逐字稿", "03_分析草稿", "logs"],
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps({"workspace": str(batch), "status": "ready"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
