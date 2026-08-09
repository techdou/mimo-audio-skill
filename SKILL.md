---
name: mimo-lecture-audio-skill
version: 2.4.0
description: Generate MiMo-powered lecture narration audio from teaching notes, with optional ASR QA, subtitles, HTML review pages, WAV merge, duration stats, packaging, and runtime official-doc sync checking. Use progressive disclosure: route to the smallest script needed for the user's task.
---

# MiMo Lecture Audio Skill

Use this Skill when the user wants to turn lecture notes, scripts, Markdown, HTML, or segmented narration text into MiMo audio. The core capability is MiMo TTS. ASR, subtitles, HTML player, audio merge, duration stats, and ZIP packaging are optional add-ons.

## Progressive disclosure rule

Do not run the full pipeline by default. Choose the smallest script that satisfies the user's request.

- Only generate narration audio: use `scripts/mimo_tts_batch.py`.
- Transcribe generated audio for checking: use `scripts/mimo_asr_transcribe.py`.
- Generate subtitles for video/voiceover: use `scripts/generate_srt.py`.
- Generate a standalone review page: use `scripts/generate_html_player.py`.
- Add audio controls to an existing lecture HTML: use `scripts/inject_audio_to_html.py`.
- Merge segment WAV files: use `scripts/merge_wav.py`.
- Measure audio durations: use `scripts/audio_duration.py`.
- Check whether local rules match official MiMo docs and `/v1/models`: use `scripts/check_official_docs.py`.
- Run a common multi-step workflow: use `scripts/run_pipeline.py` with explicit flags.

After TTS synthesis completes, always execute the Post-TTS ask rule (see below), even if the user only asked for "generate audio".

## Core workflow

1. Clean source notes if needed.
2. Create or receive `segments.json`.
3. Validate segments.
4. Run TTS.
5. Optionally run ASR, duration stats, subtitles, HTML player, merge, or ZIP.

## Key MiMo API rules

- TTS uses `/v1/chat/completions`.
- Put narration text in `assistant.content`.
- Put style, tone, or voice design instructions in `user.content`.
- Use `mimo-v2.5-tts` for preset voices.
- Use `mimo-v2.5-tts-voicedesign` with `voice_design_prompt`; do not pass preset `voice`.
- Use `mimo-v2.5-tts-voiceclone` with `voice_sample_path` or `data:audio/...;base64,...`.
- Use `--stream` only for preset TTS by default. Use `--stream-all` only when compatibility streaming is explicitly desired.
- ASR uses `mimo-v2.5-asr` and `input_audio.data` data URLs.

## Self-update guard

This skill checks itself against official MiMo docs before synthesis. Two complementary layers:

- **API layer**: `GET /v1/models` — verifies the 4 models this skill uses are still listed. Catches deprecations (the V2 series was retired 2026.6.30).
- **Doc layer**: fetches `llms.txt` → `.md` sources and diffs preset voices / languages / formats against `templates/known_rules.json`.

Behavior: default non-blocking (read cache → warn → continue). Use `--check-docs` to make it blocking. Use `--skip-check` to bypass. See `docs/self_update.md` for details.

## Default commands

Validate segments:

```bash
python scripts/validate_segments.py --segments output/segments.json
```

Generate TTS audio:

```bash
python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments output/segments.json \
  --out-dir output/audio \
  --manifest output/audio_manifest.json \
  --include-text-in-manifest
```

Run optional pipeline with explicit switches:

```bash
python scripts/run_pipeline.py \
  --input lecture.md \
  --tts \
  --duration \
  --html-player
```

Merge existing segment WAVs into one long audio:

```bash
python scripts/merge_wav.py \
  --manifest output/audio_manifest.json \
  --output output/full_course.wav
```

## Post-TTS ask rule

After TTS synthesis completes (`mimo_tts_batch.py` or `run_pipeline.py --tts`), the agent **must** use AskUserQuestion to ask the user which post-processing steps they want. This is a **multiSelect** question with these options:

| Option label | What it does | Script to call if selected |
|---|---|---|
| 合并成一个长音频 | Merge all segments into one WAV | `merge_wav.py --manifest <manifest> --output <out_dir>/full_course.wav` |
| 生成 HTML 播放页 | Standaway review page with audio players | `generate_html_player.py --manifest <manifest> --output <out_dir>/player.html --title <title>` |
| 测各段时长 | Measure each segment's duration | `audio_duration.py --manifest <manifest> --update-manifest` |
| 生成 SRT 字幕 | Subtitles for video/voiceover | `generate_srt.py --manifest <manifest> --segments <segments> --srt <out_dir>/subtitles.srt` |
| 都不用，音频够用了 | Skip all post-processing | Call nothing |

Rules:
- If the user selects multiple items, execute in dependency order: **duration → merge → srt → html-player** (duration enriches the manifest so srt/html-player can show timings).
- After the user picks, call the scripts immediately via Bash. Do not ask again.
- If running via `run_pipeline.py` with flags like `--merge --html-player` already set, skip the ask (user already chose).

## Optional pipeline flags

- `--tts`: generate MiMo TTS audio.
- `--asr-check`: transcribe generated audio for QA.
- `--srt`: generate SRT subtitles.
- `--vtt`: generate WebVTT subtitles.
- `--html-player`: generate standalone audio review page.
- `--inject-html PATH`: inject audio controls into an existing HTML lecture.
- `--merge`: merge WAV segments into `full_course.wav`.
- `--duration`: measure WAV duration and enrich manifest.
- `--zip`: package output directory.

## Output expectations

For TTS tasks, return links or paths to generated audio files and `audio_manifest.json`. For optional add-ons, return only the requested artifacts, such as `player.html`, `course.srt`, `course.vtt`, `full_course.wav`, or the ZIP package.

## Intermediate cleanup (optional)

The pipeline leaves several internal state files that most users do not need after a successful run: `work/` (cleaned text + segments), `duration_manifest.json`, `asr_manifest.json`, `merge_manifest.json`, and `*.jsonl` logs.

Set the env var to auto-clean these after success:

```bash
export MIMO_AUDIO_CLEAN_INTERMEDIATES=1
```

When enabled, the pipeline deletes only the items above. It preserves all final deliverables: `audio/*.wav`, `audio_manifest.json`, `full_course.wav`, `player.html`, `subtitles/*.srt`, `subtitles/*.vtt`, `asr/*.txt`, `<stem>_with_audio.html`, and `*.zip`. Failed runs are never cleaned (so you can debug). To make this permanent on Windows, set it as a user environment variable.

## Details

Load deeper docs only when needed:

- `docs/tts.md`
- `docs/asr.md`
- `docs/subtitles.md`
- `docs/html_player.md`
- `docs/pipeline.md`
- `docs/mimo_v25_audio_rules.md`
- `docs/self_update.md`
- `docs/troubleshooting.md`
