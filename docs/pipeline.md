# Pipeline 调度器说明

`run_pipeline.py` 是可选调度器，不是唯一入口。单脚本仍然可以独立使用。

默认没有传任何功能开关时，pipeline 只执行 TTS：

```bash
python scripts/run_pipeline.py --input examples/ai_literacy_sample.md
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

生成课程音频检查页：

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
