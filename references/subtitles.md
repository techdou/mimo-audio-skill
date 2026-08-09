# 字幕生成说明

字幕脚本只负责生成字幕，不负责 TTS 或 ASR：

```bash
python scripts/generate_srt.py --manifest output/audio_manifest.json --segments output/segments.json --srt output/subtitles/course.srt --vtt output/subtitles/course.vtt
```

## 文本来源优先级

1. 如果提供 `--asr-manifest`，优先使用 ASR 转写文本。
2. 否则使用 TTS manifest 中的 `speech_text`。
3. 如果 manifest 没有文本，使用 `--segments` 中的原始 `speech_text`。

## 时间轴

字幕时间轴以每个音频片段的 WAV 时长为准。它不是字级对齐字幕，而是“片段级字幕”，适合课程旁白、音频预览和视频初稿。

如果需要更精细的字级字幕，建议后续接入专门的强制对齐工具。
