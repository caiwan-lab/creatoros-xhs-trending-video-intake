#!/usr/bin/env python3
"""Discover, time-filter, and locally score public Xiaohongshu video candidates."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


WINDOWS = (1, 3, 7, 30)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def text(value: Any) -> str:
    return str(value or "").strip()


def safe_piece(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip("-") or "keyword"


def parse_count(value: Any) -> int | None:
    raw = text(value).lower().replace(",", "").replace("+", "")
    if not raw:
        return None
    multiplier = 10000 if "万" in raw or "w" in raw else 1
    raw = raw.replace("万", "").replace("w", "")
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return None


def publish_date(note: dict[str, Any]) -> str | None:
    for tag in note.get("corner_tag_info", []) if isinstance(note.get("corner_tag_info"), list) else []:
        if isinstance(tag, dict) and tag.get("type") == "publish_time":
            value = text(tag.get("text"))
            try:
                return date.fromisoformat(value[:10]).isoformat()
            except ValueError:
                return None
    for key in ("publish_time", "publish_date", "time"):
        value = text(note.get(key))
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            continue
    return None


def public_url(note_id: str, token: str) -> str:
    base = f"https://www.xiaohongshu.com/explore/{note_id}"
    return base if not token else f"{base}?{urlencode({'xsec_token': token, 'xsec_source': 'pc_search'})}"


def candidate_from_item(item: dict[str, Any], keyword: str, ranking: str, position: int) -> dict[str, Any] | None:
    note = item.get("note_card", item)
    if not isinstance(note, dict):
        return None
    note_id = text(item.get("id") or note.get("note_id"))
    if not note_id or (text(note.get("type")) and text(note.get("type")) != "video"):
        return None
    user = note.get("user") if isinstance(note.get("user"), dict) else {}
    interact = note.get("interact_info") if isinstance(note.get("interact_info"), dict) else {}
    signals = {
        "liked": text(interact.get("liked_count")) or None,
        "comment": text(interact.get("comment_count")) or None,
        "collected": text(interact.get("collected_count")) or None,
        "shared": text(interact.get("shared_count") or interact.get("share_count")) or None,
    }
    numeric = {key: parse_count(value) for key, value in signals.items()}
    return {
        "note_id": note_id,
        "url": public_url(note_id, text(item.get("xsec_token") or note.get("xsec_token"))),
        "title": text(note.get("title") or note.get("display_title")) or "（平台未返回标题）",
        "author": text(user.get("nickname")),
        "author_id": text(user.get("user_id")),
        "note_type": "video",
        "published_at": publish_date(note),
        "public_signals": signals,
        "interaction_total": sum(value for value in numeric.values() if value is not None),
        "signals_missing": [key for key, value in numeric.items() if value is None],
        "discoveries": [{"keyword": keyword, "ranking": ranking, "position": position}],
    }


def items_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        source = payload.get("items") or (payload.get("data") or {}).get("items")
        return [item for item in source if isinstance(item, dict)] if isinstance(source, list) else []
    return []


def query_xhs(binary: str, keyword: str, ranking: str, page: int) -> dict[str, Any]:
    completed = subprocess.run([binary, "search", keyword, "--sort", ranking, "--type", "video", "--page", str(page), "--json"], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "xhs search failed").strip())
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("xhs search returned non-JSON output") from exc


def merge(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    known = {(x["keyword"], x["ranking"], x["position"]) for x in existing["discoveries"]}
    for entry in incoming["discoveries"]:
        if (entry["keyword"], entry["ranking"], entry["position"]) not in known:
            existing["discoveries"].append(entry)
    for field, value in incoming["public_signals"].items():
        if existing["public_signals"].get(field) is None and value is not None:
            existing["public_signals"][field] = value
    existing["interaction_total"] = max(existing["interaction_total"], incoming["interaction_total"])
    if not existing.get("published_at"):
        existing["published_at"] = incoming.get("published_at")


def relevance(title: str, discoveries: list[dict[str, Any]]) -> float:
    title_lower = title.lower()
    scores: list[float] = []
    for discovery in discoveries:
        query = text(discovery["keyword"]).lower()
        if query and query in title_lower:
            scores.append(10.0)
            continue
        terms = [part for part in re.split(r"[\s,，、/]+", query) if len(part) > 1]
        if not terms:
            scores.append(3.0)
            continue
        matched = sum(term in title_lower for term in terms)
        scores.append(round(3 + 7 * matched / len(terms), 2))
    return max(scores, default=0.0)


def age_score(published_at: str | None, as_of: date) -> tuple[float, int | None]:
    if not published_at:
        return 0.0, None
    days_old = max(0, (as_of - date.fromisoformat(published_at)).days)
    if days_old <= 1:
        return 2.0, days_old
    if days_old <= 3:
        return 1.5, days_old
    if days_old <= 7:
        return 1.0, days_old
    if days_old <= 30:
        return 0.5, days_old
    return 0.0, days_old


def score(candidates: list[dict[str, Any]], as_of: date) -> None:
    values = sorted({math.log1p(item["interaction_total"]) for item in candidates})
    for item in candidates:
        heat_base = math.log1p(item["interaction_total"])
        heat = 1.5 if len(values) <= 1 else round(3 * values.index(heat_base) / (len(values) - 1), 2)
        relevance_score = relevance(item["title"], item["discoveries"])
        recency, days_old = age_score(item.get("published_at"), as_of)
        item["scores"] = {
            "relevance": relevance_score,
            "heat": heat,
            "recency": recency,
            "total": round(relevance_score + heat + recency, 2),
            "method": "local_heuristic_v1",
        }
        item["age_days"] = days_old
        item["selection_reason"] = f"本地启发式总分 {item['scores']['total']} / 15；互动总数 {item['interaction_total']}。"


def select_window(candidates: list[dict[str, Any]], requested: str, minimum: int, as_of: date, include_unknown: bool) -> tuple[list[dict[str, Any]], int]:
    def within(days: int) -> list[dict[str, Any]]:
        result = []
        for item in candidates:
            age = item.get("age_days")
            if age is None:
                if include_unknown:
                    result.append(item)
            elif age <= days:
                result.append(item)
        return result
    if requested != "auto":
        return within(int(requested)), int(requested)
    last: list[dict[str, Any]] = []
    for days in WINDOWS:
        last = within(days)
        if len(last) >= minimum:
            return last, days
    return last, 30


def cell(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\n", " ")


def write_markdown(path: Path, records: list[dict[str, Any]], days: int, threshold: int) -> None:
    rows = [
        "# 小红书高互动视频候选表", "",
        f"> 当前结果基于公开搜索返回中发布日期在近 {days} 天且总互动不低于 {threshold} 的候选。不是全站历史库或平台官方爆款结论。", "",
        "| 标题 | 链接 | 发布日 | 作者 | 总互动 | 相关性 | 热度 | 时效 | 总分 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in records:
        scores = item["scores"]
        rows.append(f"| {cell(item['title'])} | [打开]({item['url']}) | {item.get('published_at') or '未知'} | {cell(item['author'])} | {item['interaction_total']} | {scores['relevance']} | {scores['heat']} | {scores['recency']} | **{scores['total']}** |")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_html(path: Path, records: list[dict[str, Any]], days: int, threshold: int) -> None:
    cards = []
    for item in records:
        scores = item["scores"]
        cards.append(f"<article><h2><a href=\"{html.escape(item['url'], quote=True)}\">{html.escape(item['title'])}</a></h2><p>{html.escape(item['author'])} · {item.get('published_at') or '发布日期未知'}</p><strong>{scores['total']} / 15</strong><dl><dt>总互动</dt><dd>{item['interaction_total']}</dd><dt>相关性</dt><dd>{scores['relevance']} / 10</dd><dt>热度</dt><dd>{scores['heat']} / 3</dd><dt>时效</dt><dd>{scores['recency']} / 2</dd></dl><p>{html.escape(item['selection_reason'])}</p></article>")
    document = f"<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\"><title>小红书高互动视频候选</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:980px;margin:40px auto;padding:0 20px;background:#fafafa;color:#222}}article{{background:#fff;border:1px solid #eee;border-radius:16px;padding:20px;margin:14px 0}}h1{{color:#ff2442}}h2{{margin:0}}a{{color:#222}}strong{{font-size:24px;color:#ff2442}}dl{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}}dt{{font-size:12px;color:#777}}dd{{margin:2px 0;font-weight:700}}</style><h1>小红书高互动视频候选</h1><p>公开搜索结果中：近 {days} 天、总互动 ≥ {threshold}。分数为本地启发式，不是平台官方分数。</p>{''.join(cards) or '<p>没有符合当前时间窗和互动门槛的候选。</p>'}</html>"
    path.write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and locally score public Xiaohongshu video candidates.")
    parser.add_argument("--keyword", action="append", default=[], help="Repeat for every chosen query; pass multiple keywords after optional broad-term expansion.")
    parser.add_argument("--sort", action="append", choices=("popular", "latest", "general"), default=[])
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--days", choices=("auto", "1", "3", "7", "30"), default="auto")
    parser.add_argument("--min-candidates", type=int, default=10)
    parser.add_argument("--min-interactions", type=int, default=1000)
    parser.add_argument("--include-unknown-date", action="store_true")
    parser.add_argument("--as-of", help="YYYY-MM-DD; useful for reproducible offline verification.")
    parser.add_argument("--delay-seconds", type=float, default=5.0)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--xhs-bin", default="xhs")
    parser.add_argument("--input-json", help="Offline fixture: normalize one saved response instead of live search.")
    args = parser.parse_args()
    if args.pages < 1 or args.min_candidates < 1 or args.min_interactions < 0 or args.delay_seconds < 0:
        parser.error("pages/min-candidates must be positive; delays and interaction threshold cannot be negative")
    if not args.keyword and not args.input_json:
        parser.error("provide at least one --keyword, or --input-json for an offline fixture")
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    output_dir = Path(args.output_dir).expanduser().resolve()
    raw_dir = output_dir / "raw"
    candidates: dict[str, dict[str, Any]] = {}
    searches: list[dict[str, Any]] = []
    rankings = args.sort or ["popular", "latest"]

    def add(payload: dict[str, Any], keyword: str, ranking: str, raw_path: Path) -> None:
        write_json(raw_path, payload)
        for position, item in enumerate(items_from(payload), start=1):
            record = candidate_from_item(item, keyword, ranking, position)
            if not record:
                continue
            if record["note_id"] in candidates:
                merge(candidates[record["note_id"]], record)
            else:
                candidates[record["note_id"]] = record

    if args.input_json:
        payload = json.loads(Path(args.input_json).expanduser().read_text(encoding="utf-8"))
        keyword = args.keyword[0] if args.keyword else "fixture"
        raw_path = raw_dir / "fixture.json"
        add(payload, keyword, "fixture", raw_path)
        searches.append({"keyword": keyword, "ranking": "fixture", "page": 1, "raw_file": str(raw_path), "status": "ok"})
    else:
        for query_index, keyword in enumerate(args.keyword):
            for ranking in rankings:
                for page in range(1, args.pages + 1):
                    raw_path = raw_dir / f"{safe_piece(keyword)}-{ranking}-page-{page}.json"
                    try:
                        add(query_xhs(args.xhs_bin, keyword, ranking, page), keyword, ranking, raw_path)
                        searches.append({"keyword": keyword, "ranking": ranking, "page": page, "raw_file": str(raw_path), "status": "ok"})
                    except Exception as exc:
                        searches.append({"keyword": keyword, "ranking": ranking, "page": page, "raw_file": str(raw_path), "status": "failed", "error": str(exc)})
                    is_last = query_index == len(args.keyword) - 1 and ranking == rankings[-1] and page == args.pages
                    if not is_last and args.delay_seconds:
                        time.sleep(args.delay_seconds)

    all_records = list(candidates.values())
    score(all_records, as_of)
    thresholded = [item for item in all_records if item["interaction_total"] >= args.min_interactions]
    selected, used_days = select_window(thresholded, args.days, args.min_candidates, as_of, args.include_unknown_date)
    selected.sort(key=lambda item: (item["scores"]["total"], item["interaction_total"]), reverse=True)
    manifest = {"generated_at": utc_now(), "as_of": as_of.isoformat(), "query_keywords": args.keyword, "rankings": rankings, "searches": searches, "scoring": {"method": "local_heuristic_v1", "relevance_max": 10, "heat_max": 3, "recency_max": 2, "interaction_threshold": args.min_interactions}, "requested_days": args.days, "used_days": used_days, "all_video_candidates": len(all_records), "selected_candidate_count": len(selected)}
    write_json(output_dir / "candidates.json", {"generated_at": utc_now(), "candidates": selected})
    write_json(output_dir / "manifest.json", manifest)
    write_markdown(output_dir / "爆款候选表.md", selected, used_days, args.min_interactions)
    write_html(output_dir / "小红书高互动视频候选报告.html", selected, used_days, args.min_interactions)
    print(f"output_dir: {output_dir}")
    print(f"candidate_count: {len(selected)}")
    print(f"used_days: {used_days}")
    print("status: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
