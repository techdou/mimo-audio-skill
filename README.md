# MiMo Lecture Audio Skill | MiMo 讲义语音 Skill

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

A modular Agent Skill that converts lecture notes, scripts, or course materials into **MiMo voice broadcast audio**. v1.3.0 design: TTS is the core capability; HTML player pages, SRT/VTT subtitles, ASR quality check, audio merging, duration stats, and ZIP packaging are all optional capabilities.

### When to use

- Convert lecture notes / scripts / course materials to speech audio
- Generate HTML audio player pages with subtitles
- ASR-based audio quality verification
- Batch audio merging and packaging

---

<a id="中文"></a>
## 中文

# MiMo Lecture Audio Skill v1.3.0

把讲义、文稿或课程脚本转成 MiMo 语音播报音频。v1.3.0 采用模块化设计：TTS 是核心能力，HTML 播放页、SRT/VTT 字幕、ASR 质检、音频合并、时长统计和 ZIP 打包都是可选能力。

## 目录结构

```text
mimo-lecture-audio-skill/
├── SKILL.md
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── docs/
│   ├── tts.md
│   ├── asr.md
│   ├── subtitles.md
│   ├── html_player.md
│   ├── pipeline.md
│   ├── mimo_v25_audio_rules.md
│   └── troubleshooting.md
├── scripts/
│   ├── clean_lecture_text.py
│   ├── make_segments.py
│   ├── validate_segments.py
│   ├── mimo_tts_batch.py
│   ├── mimo_asr_transcribe.py
│   ├── generate_srt.py
│   ├── generate_html_player.py
│   ├── inject_audio_to_html.py
│   ├── merge_wav.py
│   ├── audio_duration.py
│   ├── mimo_smoke_test.py
│   └── run_pipeline.py
├── templates/
├── examples/
└── tests/
```

## 0. 配置 Key

```bash
export MIMO_API_KEY="你的_sk_key"
export MIMO_BASE_URL="https://api.xiaomimimo.com/v1"
```

Windows PowerShell：

```powershell
$env:MIMO_API_KEY="你的_sk_key"
$env:MIMO_BASE_URL="https://api.xiaomimimo.com/v1"
```

## 1. 最小 TTS 流程

```bash
python scripts/validate_segments.py --segments examples/segments.sample.json

python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments examples/segments.sample.json \
  --out-dir output/audio \
  --manifest output/audio_manifest.json \
  --include-text-in-manifest
```

不消耗 API 的检查：

```bash
python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments examples/segments.sample.json \
  --dry-run
```

## 2. 一键 pipeline，但按需开启

默认没有任何功能开关时，pipeline 只执行 TTS：

```bash
python scripts/run_pipeline.py --input examples/ai_literacy_sample.md
```

只生成音频：

```bash
python scripts/run_pipeline.py --input lecture.md --tts
```

音频 + 时长 + 播放页：

```bash
python scripts/run_pipeline.py \
  --input lecture.md \
  --tts \
  --duration \
  --html-player \
  --course-title "AI 通识课音频"
```

视频旁白场景：

```bash
python scripts/run_pipeline.py \
  --input video_script.md \
  --tts \
  --duration \
  --srt \
  --vtt \
  --merge
```

完整课程包：

```bash
python scripts/run_pipeline.py \
  --input lecture.md \
  --tts \
  --asr-check \
  --duration \
  --srt \
  --vtt \
  --html-player \
  --merge \
  --zip
```

## 3. 已有 HTML 只注入音频

如果你已经有设计好的讲义 HTML，不要重新生成播放页，直接注入音频块：

```bash
python scripts/inject_audio_to_html.py \
  --html lecture.html \
  --manifest output/audio_manifest.json \
  --output lecture_with_audio.html
```

## 4. 单脚本能力

统计时长：

```bash
python scripts/audio_duration.py --manifest output/audio_manifest.json --update-manifest
```

生成字幕：

```bash
python scripts/generate_srt.py \
  --manifest output/audio_manifest.json \
  --segments output/segments.json \
  --srt output/subtitles/course.srt \
  --vtt output/subtitles/course.vtt
```

生成播放页：

```bash
python scripts/generate_html_player.py \
  --manifest output/audio_manifest.json \
  --segments output/segments.json \
  --output output/player.html
```

合并音频：

```bash
python scripts/merge_wav.py \
  --manifest output/audio_manifest.json \
  --output output/full_course.wav
```

ASR 质检：

```bash
python scripts/mimo_asr_transcribe.py \
  --config templates/config.example.json \
  --audio output/audio/*.wav \
  --language zh \
  --out-dir output/asr \
  --manifest output/asr_manifest.json
```

## 5. 测试

```bash
python -m py_compile scripts/*.py
python -m unittest discover -s tests -v
python scripts/run_pipeline.py --input examples/ai_literacy_sample.md --tts --duration --html-player --dry-run
```

真实 API smoke test：

```bash
python scripts/mimo_smoke_test.py --config templates/config.example.json --out-dir output/smoke
```

## 6. 设计原则

- `SKILL.md` 只写核心能力和路由规则。
- `README.md` 写快速开始和常用命令。
- `docs/` 写详细说明。
- `scripts/` 每个脚本只负责一类任务。
- `run_pipeline.py` 只是可选调度器，不替代单脚本。
