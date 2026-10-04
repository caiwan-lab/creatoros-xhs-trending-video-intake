# Output data contract

`candidates.json` is a batch envelope:

```json
{
  "generated_at": "ISO-8601 UTC timestamp",
  "candidates": [
    {
      "note_id": "platform note id",
      "url": "canonical public explore URL",
      "title": "platform title or an explicit unavailable label",
      "author": "public nickname when returned",
      "published_at": "YYYY-MM-DD or null",
      "public_signals": {
        "liked": "string or null",
        "comment": "string or null",
        "collected": "string or null",
        "shared": "string or null"
      },
      "discoveries": [
        {"keyword": "query", "ranking": "popular|latest", "position": 1}
      ],
      "interaction_total": 0,
      "scores": {"relevance": 0, "heat": 0, "recency": 0, "total": 0, "method": "local_heuristic_v1"}
    }
  ]
}
```

Public signals are stored as returned strings because platforms may return
localized compact values such as `1.2万`. Consumers must not compare them as
exact numbers without explicit parsing and provenance.

The local score is a transparent candidate-ranking heuristic: title/query
match (0–10), batch-relative interaction heat (0–3), and publication recency
(0–2). It is neither a Xiaohongshu platform score nor a complete historical
ranking.

`intake-manifest.json` records the attempted intake command result only. The
authoritative transcript, media-retention decision, raw source and pending card
remain in the configured CreatorOS vault.
