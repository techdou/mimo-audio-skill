# Pipeline 调度器说明

`run_pipeline.py` 是可选调度器，不是唯一入口。单脚本仍然可以独立使用。

默认没有传任何功能开关时，pipeline 只执行 TTS：

```bash
python scripts/run_pipeline.py --input examples/ai_literacy_sample.md
```

## 场景与音色模板

`--text-kind` 按内容场景自动套用内置模板：

```bash
# 小说/故事 → novel-narration 模板
python scripts/run_pipeline.py --input examples/novel_sample.md --text-kind novel --tts --duration

# 播客脚本 → podcast-casual 模板
python scripts/run_pipeline.py --input examples/podcast_sample.md --text-kind podcast --tts --merge

# 短视频/营销口播 → short-video 模板
python scripts/run_pipeline.py --input ad_copy.md --text-kind marketing --tts --srt --vtt
```

显式指定个人克隆模板（优先级高于 `--text-kind`）：

```bash
python scripts/run_pipeline.py --input lecture.md --profile douge-lecture --tts --duration --html-player
```

## 常见组合

只生成音频：

```bash
python scripts/run_pipeline.py --input lecture.md --tts
```

生成音频并统计时长：

```bash
python scripts/run_pipeline.py --input lecture.md --tts --duration
```

生成音频检查页（`--title` 是 `--course-title` 的别名）：

```bash
python scripts/run_pipeline.py --input lecture.md --tts --duration --html-player
```

为视频旁白生成音频和字幕：

```bash
python scripts/run_pipeline.py --input video_script.md --tts --duration --srt --vtt --merge
```

完整课程包：

```bash
python scripts/run_pipeline.py --input lecture.md --tts --asr-check --duration --srt --vtt --html-player --merge --zip
```

## 功能开关

- `--tts`：生成 MiMo TTS 音频。
- `--asr-check`：用 MiMo ASR 转写音频。
- `--srt`：生成 SRT 字幕。
- `--vtt`：生成 WebVTT 字幕。
- `--html-player`：生成独立播放页。
- `--inject-html lecture.html`：给已有 HTML 注入音频。
- `--merge`：合并全部 wav。
- `--duration`：统计音频时长。
- `--zip`：打包输出目录。
