---
name: creatoros-xhs-trending-video-intake
description: Discover public Xiaohongshu high-engagement video candidates by topic, preserve titles, links and public signals, then route selected candidates through a verified CreatorOS local-transcription intake. Use when the user asks to find multiple recent/popular Xiaohongshu videos and obtain titles, URLs, public data, and transcripts. Never use for publishing, social interaction, or bypassing access restrictions.
---

# CreatorOS Xiaohongshu Trending Video Intake

## Outcome

Build a traceable research batch for a topic:

```text
topic keywords
  -> serial public-video search (popular + latest)
  -> deduplicated high-engagement candidates: title / URL / author / public signals
  -> one-at-a-time CreatorOS single-video intake
  -> post text + permitted media + local ASR transcript + pending video card
```

“爆款” is an editorial shorthand only. The search endpoint ranking and public
interaction signals create **high-engagement candidates**, not a verified
platform-wide popularity ranking or a causal traffic conclusion.

## Preconditions

1. Before every live Xiaohongshu session, run `xhs status`. Stop if the login
   is unavailable; never expose or copy cookies.
2. Use public, normally accessible video notes only. Search one request at a
   time, with a delay; stop on CAPTCHA, access denial, or repeated errors.
3. The CreatorOS destination must have the existing
   `04_系统维护/scripts/creator-platform-video-intake.py` and local
   `creator-local-transcribe` route available. Run the bundled check first if
   the computer is new.
4. Browser-cookie retries are opt-in: get the user's explicit authorization
   before adding `--allow-browser-cookies` to an intake command.

## 1. Discover candidates

Use two complementary search rankings by default: `popular` finds platform
high-engagement candidates; `latest` reduces the chance that research only
contains old posts. Keep the exact keywords and raw responses.

```bash
python scripts/discover_xhs_videos.py \
  --keyword '养生' \
  --keyword '健康生活方式' \
  --output-dir /path/to/research-batch
```

The script writes:

- `raw/`: one unmodified JSON response per query, ranking, and page;
- `candidates.json`: deduplicated machine-readable records;
- `爆款候选表.md`: readable title / link / author / available public-signal table;
- `manifest.json`: query, ranking, timing, and counts.

It searches only `--type video`, is serial, and never likes, saves, comments,
follows, replies, or publishes.

## Local transcription setup on a new computer

This Skill includes the runtime setup for the local `faster-whisper` route.
Checking changes nothing:

```bash
python scripts/setup_creatoros_transcription.py \
  --creatoros-vault /path/to/CreatorOS \
  --model small
```

Only after the user explicitly agrees to download dependencies and the model,
run the same command with `--install`. It creates/uses CreatorOS's isolated
`04_系统维护/.venvs/video-local` environment, installs `faster-whisper`, and
downloads the selected model to CreatorOS's local cache. It does not use a
transcription API or API tokens. Do not invoke `--install` silently.

## 2. Intake every selected candidate

Do not claim a platform post body is a word-for-word transcript. The current
Xiaohongshu adapter preserves visible post text separately. For spoken content,
it uses a verified caption track **only if a future adapter explicitly returns
one as a caption track**; otherwise it downloads permitted media and uses local
`faster-whisper small`. If media or a usable caption track is unavailable, keep
the failure status rather than inventing a transcript.

Run candidate intake one at a time. The command template is required so this
public Skill contains no personal machine path, vault name, or browser setting:

```bash
python scripts/run_creatoros_intake.py \
  --candidates /path/to/research-batch/candidates.json \
  --output-dir /path/to/research-batch/intake-runs \
  --limit 12 \
  --intake-command 'python /path/to/CreatorOS/04_系统维护/scripts/creator-platform-video-intake.py --vault /path/to/CreatorOS --content-line 普通人学AI {url}'
```

The runner substitutes only `{url}`, `{title}`, `{note_id}`, and `{output_dir}`
and runs each command without a shell. It records one result per candidate in
`intake-manifest.json`; a failed candidate never blocks later ones.

## 3. Interpret the resulting batch

For each attempted video, report separately:

- candidate title, canonical link, author, and any public likes/comments/
  collections/shares returned by the platform;
- post-body source versus spoken-transcript source;
- `done`, `failed`, or `unavailable` status and the raw/pending artifact path;
- unavailable metrics as `null`, never guessed values.

CreatorOS intake writes raw material and a `待提纯` video card only. It must not
write directly to final Wiki pages.

## Safety and retention

- Never bypass DRM, login, CAPTCHA, or a platform access restriction.
- Keep raw query responses and processing logs; they support later review.
- Do not put cookies, downloaded media, real user data, personal absolute paths,
  or private CreatorOS files in this Skill repository.
- Let CreatorOS retain post text, metadata, transcript, and card while removing
  a downloaded mp4 only after a verified transcript/card according to its
  existing retention policy.

## Included helpers

- `scripts/discover_xhs_videos.py`: public candidate discovery and normalization.
- `scripts/run_creatoros_intake.py`: serial command-template runner for the
  existing CreatorOS single-video intake.
- `scripts/setup_creatoros_transcription.py`: non-mutating runtime check plus
  an explicit, local `faster-whisper`/model installer.
