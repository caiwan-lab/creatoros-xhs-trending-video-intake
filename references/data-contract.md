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
      "public_signals": {
        "liked": "string or null",
        "comment": "string or null",
        "collected": "string or null",
        "shared": "string or null"
      },
      "discoveries": [
        {"keyword": "query", "ranking": "popular|latest", "position": 1}
      ]
    }
  ]
}
```

Public signals are stored as returned strings because platforms may return
localized compact values such as `1.2万`. Consumers must not compare them as
exact numbers without explicit parsing and provenance.

`intake-manifest.json` records the attempted intake command result only. The
authoritative transcript, media-retention decision, raw source and pending card
remain in the configured CreatorOS vault.
