# creatoros-xhs-trending-video-intake

A public Codex Skill for serially discovering public Xiaohongshu video candidates
by topic, preserving title/link/public interaction signals, and sending selected
videos to a local CreatorOS transcription pipeline.

It is deliberately read-only toward Xiaohongshu: no publishing, likes, saves,
comments, follows, or CAPTCHA/login bypass.

## Install

```bash
npx skills add Akumahate11/creatoros-xhs-trending-video-intake -g
```

## What it does

1. Searches public **video** notes serially, using `popular` and `latest`.
2. Writes raw JSON, a deduplicated `candidates.json`, and a readable candidate table.
3. Runs a caller-supplied local CreatorOS command once per selected candidate.
4. Keeps failures visible rather than making up metrics or transcripts.

For spoken transcription, the current CreatorOS Xiaohongshu adapter uses local
ASR after a permitted media download. It preserves the post body separately;
it does not mislabel post copy as word-for-word speech.

## Requirements

- [`xiaohongshu-cli`](https://github.com/xyou365/xiaohongshu-cli) installed and authenticated;
- a local CreatorOS checkout containing `creator-platform-video-intake.py` and
  the local `faster-whisper` route.

## Set up local transcription

Check the complete local pipeline without changing it:

```bash
python scripts/check_xhs_intake_environment.py \
  --creatoros-vault /path/to/CreatorOS \
  --model small
```

This checks that `xhs` is installed and logged in, the CreatorOS single-video
intake/downloader is present, and local ASR is ready. It reports only booleans;
it never prints browser cookies.

Check a new CreatorOS checkout without changing it:

```bash
python scripts/setup_creatoros_transcription.py \
  --creatoros-vault /path/to/CreatorOS \
  --model small
```

After the user approves the dependency/model download, add `--install`. The
setup is local and creates the isolated CreatorOS `video-local` environment;
it does not call an API or consume transcription tokens.

## Caption handling

Before each selected video enters the existing CreatorOS intake, the runner
probes `xhs read` for a structured, timed caption track. Note-body text is
always kept separate and is never presented as a spoken transcript. The current
XHS route normally proceeds to local ASR because no verified downloadable
spoken-caption track is exposed; if a future track appears, the batch records
that an explicit caption adapter is still needed rather than silently using the
wrong text.

Do not put cookies, real captures, local media, or personal paths into this repo.

## License

MIT. See [LICENSE](LICENSE).
