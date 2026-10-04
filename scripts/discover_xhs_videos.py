#!/usr/bin/env python3
"""Discover public Xiaohongshu video candidates serially through xhs CLI."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_piece(value: str) -> str:
    result = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip())
    return result.strip("-") or "keyword"


def text(value: Any) -> str:
    return str(value or "").strip()


def public_url(note_id: str, token: str) -> str:
    base = f"https://www.xiaohongshu.com/explore/{note_id}"
    if not token:
        return base
    return f"{base}?{urlencode({'xsec_token': token, 'xsec_source': 'pc_search'})}"


def candidate_from_item(item: dict[str, Any], keyword: str, ranking: str, position: int) -> dict[str, Any] | None:
    note = item.get("note_card", item)
    if not isinstance(note, dict):
        return None
    note_id = text(item.get("id") or note.get("note_id"))
    if not note_id:
        return None
    note_type = text(note.get("type"))
    if note_type and note_type != "video":
        return None
    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    interact = note.get("interact_info") if isinstance(note.get("interact_info"), dict) else {}
    token = text(item.get("xsec_token") or note.get("xsec_token"))
    return {
        "note_id": note_id,
        "url": public_url(note_id, token),
        "title": text(note.get("title") or note.get("display_title")) or "（平台未返回标题）",
        "author": text(user.get("nickname")),
        "author_id": text(user.get("user_id")),
        "note_type": "video",
        "public_signals": {
            "liked": text(interact.get("liked_count")) or None,
            "comment": text(interact.get("comment_count")) or None,
            "collected": text(interact.get("collected_count")) or None,
            "shared": text(interact.get("share_count")) or None,
        },
        "discoveries": [{"keyword": keyword, "ranking": ranking, "position": position}],
    }


def items_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            return [item for item in payload["items"] if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [item for item in data["items"] if isinstance(item, dict)]
    return []


def markdown_cell(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\n", " ")


def write_table(path: Path, candidates: list[dict[str, Any]]) -> None:
    rows = [
        "# 小红书高互动视频候选表", "",
        "> 这是关键词检索的公开候选，不等于已确认的全网爆款。互动字段缺失时保留为空。", "",
        "| 标题 | 链接 | 作者 | 点赞 | 评论 | 收藏 | 分享 | 命中检索 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for record in candidates:
        signals = record["public_signals"]
        discoveries = "；".join(f"{x['keyword']} / {x['ranking']} #{x['position']}" for x in record["discoveries"])
        rows.append(
            "| {title} | [打开]({url}) | {author} | {liked} | {comment} | {collected} | {shared} | {discoveries} |".format(
                title=markdown_cell(record["title"]), url=record["url"], author=markdown_cell(record["author"]),
                liked=signals["liked"] or "", comment=signals["comment"] or "", collected=signals["collected"] or "",
                shared=signals["shared"] or "", discoveries=markdown_cell(discoveries),
            )
        )
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def query_xhs(binary: str, keyword: str, ranking: str, page: int) -> dict[str, Any]:
    command = [binary, "search", keyword, "--sort", ranking, "--type", "video", "--page", str(page), "--json"]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "xhs search failed").strip())
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("xhs search returned non-JSON output") from exc


def merge(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    known = {(x["keyword"], x["ranking"], x["position"]) for x in existing["discoveries"]}
    for entry in incoming["discoveries"]:
        marker = (entry["keyword"], entry["ranking"], entry["position"])
        if marker not in known:
            existing["discoveries"].append(entry)
    for field, value in incoming["public_signals"].items():
        if existing["public_signals"].get(field) is None and value is not None:
            existing["public_signals"][field] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover public Xiaohongshu video candidates through xhs CLI.")
    parser.add_argument("--keyword", action="append", default=[], help="Repeat for each topic keyword.")
    parser.add_argument("--sort", action="append", choices=("popular", "latest", "general"), default=[])
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--xhs-bin", default="xhs")
    parser.add_argument("--input-json", help="Offline fixture: normalize one saved response instead of live search.")
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if args.delay_seconds < 0:
        parser.error("--delay-seconds cannot be negative")
    if not args.keyword and not args.input_json:
        parser.error("provide at least one --keyword, or --input-json for an offline fixture")

    output_dir = Path(args.output_dir).expanduser().resolve()
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    rankings = args.sort or ["popular", "latest"]

    if args.input_json:
        payload = json.loads(Path(args.input_json).expanduser().read_text(encoding="utf-8"))
        keyword = args.keyword[0] if args.keyword else "fixture"
        for position, item in enumerate(items_from(payload), start=1):
            record = candidate_from_item(item, keyword, "fixture", position)
            if record:
                candidates[record["note_id"]] = record
        raw_path = raw_dir / "fixture.json"
        write_json(raw_path, payload)
        searches.append({"keyword": keyword, "ranking": "fixture", "page": 1, "raw_file": str(raw_path), "status": "ok"})
    else:
        for keyword_index, keyword in enumerate(args.keyword):
            for ranking in rankings:
                for page in range(1, args.pages + 1):
                    raw_path = raw_dir / f"{safe_piece(keyword)}-{ranking}-page-{page}.json"
                    try:
                        payload = query_xhs(args.xhs_bin, keyword, ranking, page)
                        write_json(raw_path, payload)
                        searches.append({"keyword": keyword, "ranking": ranking, "page": page, "raw_file": str(raw_path), "status": "ok"})
                        for position, item in enumerate(items_from(payload), start=1):
                            record = candidate_from_item(item, keyword, ranking, position)
                            if not record:
                                continue
                            if record["note_id"] in candidates:
                                merge(candidates[record["note_id"]], record)
                            else:
                                candidates[record["note_id"]] = record
                    except Exception as exc:
                        searches.append({"keyword": keyword, "ranking": ranking, "page": page, "raw_file": str(raw_path), "status": "failed", "error": str(exc)})
                    last = keyword_index == len(args.keyword) - 1 and ranking == rankings[-1] and page == args.pages
                    if not last and args.delay_seconds:
                        time.sleep(args.delay_seconds)

    ordered = list(candidates.values())
    write_json(output_dir / "candidates.json", {"generated_at": utc_now(), "candidates": ordered})
    write_json(output_dir / "manifest.json", {"generated_at": utc_now(), "searches": searches, "candidate_count": len(ordered)})
    write_table(output_dir / "爆款候选表.md", ordered)
    print(f"output_dir: {output_dir}")
    print(f"candidate_count: {len(ordered)}")
    print("status: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
