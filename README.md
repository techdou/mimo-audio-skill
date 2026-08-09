# mimo-audio-skill | MiMo 语音合成技能

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

**mimo-audio-skill** is a general-purpose MiMo TTS agent skill that turns any text into Chinese speech: lecture/course audio, audiobook narration, podcasts, short-video voiceovers, and marketing copy. It supports preset voices, voice design (`voicedesign`), voice cloning (`voiceclone`), and reusable personalized voice/style profiles. The `SKILL.md` uses standard YAML frontmatter (`name`/`description`) so agents can discover and trigger it implicitly.

### Features

- Three TTS routes: preset voice (`mimo-v2.5-tts`), text-described voice design (`mimo-v2.5-tts-voicedesign`), and sample-based voice cloning (`mimo-v2.5-tts-voiceclone`).
- Voice/style profiles: package model + voice + delivery style into one JSON and reuse it with `--profile`.
- Generic text intake: auto-clean and segment `.md/.txt/.html/.docx`, with `--text-kind` shortcuts for lecture/novel/podcast/marketing.
- Optional add-ons: ASR QA, SRT/VTT subtitles, HTML review player, WAV merge, duration stats, ZIP packaging.
- Official-doc self check before synthesis (models vs `/v1/models`).

### Quick start

```bash
export MIMO_API_KEY="your_sk_key"        # never commit this
python scripts/voice_profiles.py list    # list built-in + personal voice profiles

python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments examples/segments.sample.json \
  --out-dir output/audio \
  --manifest output/audio_manifest.json \
  --include-text-in-manifest
```

Clone your own voice:

```bash
python scripts/voice_profiles.py create \
  --name my-voice \
  --file templates/profiles/example-personal-clone.json
# edit profiles/my-voice.json -> set voice_sample_path to your 30-60s recording
python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments output/segments.json \
  --profile my-voice
```

### Security

- API keys are injected via environment variables only; `.env` and all key files are gitignored.
- Personal voice profiles (`profiles/`), internal docs (`references/`), and generated output (`output/`, `work/`) are kept out of version control.

See the Chinese section below for the full directory structure, pipeline examples, and testing instructions.

---

<a id="中文"></a>
## 中文

**mimo-audio-skill** 是通用 MiMo TTS 口播/有声内容合成技能：把任意文本合成为中文语音，覆盖课程讲义、小说有声书、播客、短视频口播、营销文案等场景。支持预置音色、voicedesign 音色设计、voiceclone 音色克隆，以及可复用的个性化音色风格模板（profile）。

### 特性

- 三种 TTS 路线：预置音色（`mimo-v2.5-tts`）、文字设计音色（`mimo-v2.5-tts-voicedesign`）、样本克隆音色（`mimo-v2.5-tts-voiceclone`）。
- 音色风格模板：把"模型 + 音色 + 语气风格"打包成一个 JSON，`--profile` 一键复用。
- 通用文本处理：`.md/.txt/.html/.docx` 自动清理并分段，支持 `--text-kind` 场景快捷选择（lecture / novel / podcast / marketing）。
- 可选增强：ASR 质检、SRT/VTT 字幕、HTML 播放页、音频合并、时长统计、ZIP 打包。
- 官方文档自检：合成前对照 MiMo 官方文档与 `/v1/models` 校验模型是否可用。
- Skills 规范合规：SKILL.md 使用标准 frontmatter（name/description），支持 Agent 隐式匹配调用。

### 目录结构

```text
mimo-audio-skill/
├── SKILL.md              # 技能入口（frontmatter + 指令）
├── README.md
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── requirements.txt
├── scripts/              # 可执行脚本（TTS / ASR / 字幕 / 模板管理 / 调度器）
├── templates/            # 配置文件与内置音色模板（templates/profiles/）
├── examples/             # 示例输入（课程 / 小说 / 播客）
└── tests/                # 标准库 unittest 测试
```

以下目录仅保留在本地，不纳入版本控制：`profiles/`（个人音色模板）、`references/`（内部文档）、`output/`（生成产物）、`work/`（中间状态）。

### 环境要求

- Python 3.9+
- MiMo API Key（`MIMO_API_KEY`），可选 `MIMO_BASE_URL`（默认 `https://api.xiaomimimo.com/v1`）
- 可选：`python-docx`（读取 .docx 输入）

### 快速开始

#### 1. 配置 API Key

通过环境变量注入，不要写进任何文件（`.env` 已被 gitignore）：

```bash
export MIMO_API_KEY="你的_sk_key"
```

PowerShell：

```powershell
$env:MIMO_API_KEY="你的_sk_key"
```

#### 2. 查看可用音色模板

```bash
python scripts/voice_profiles.py list
```

#### 3. 最小 TTS 流程

```bash
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

### 场景化使用

课程/讲义音频：

```bash
python scripts/run_pipeline.py \
  --input lecture.md \
  --text-kind lecture \
  --tts --duration --srt --vtt --html-player
```

小说有声书旁白：

```bash
python scripts/run_pipeline.py \
  --input examples/novel_sample.md \
  --text-kind novel \
  --tts --duration --html-player
```

克隆自己的音色（voiceclone）：

准备 30-60 秒、无背景音乐的 `.wav`/`.mp3` 录音（≤10MB），创建个人音色模板：

```bash
python scripts/voice_profiles.py create \
  --name my-voice \
  --file templates/profiles/example-personal-clone.json
```

编辑 `profiles/my-voice.json`，把 `voice_sample_path` 指向你的录音，然后合成：

```bash
python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments output/segments.json \
  --profile my-voice \
  --out-dir output/audio \
  --manifest output/audio_manifest.json
```

### 音色模板（profile）

- 内置模板：`templates/profiles/`（`lecture-natural` / `podcast-casual` / `novel-narration` / `short-video` / `example-personal-clone`）。
- 个人模板：`profiles/`（gitignored，不入库）。
- `--profile` 只填充 segments 缺失字段，不覆盖显式配置；`voice_profiles.py apply --overwrite` 可强制覆盖。
- `--text-kind` 场景快捷选择：`lecture` / `novel` / `podcast` / `marketing`。

### 测试

```bash
python -m compileall -q scripts
python -m unittest discover -s tests -v
```

### 安全说明

- API Key 只通过环境变量注入；`.env` 及所有密钥类文件已 gitignore，绝不提交。
- 个人音色模板（`profiles/`）含本地路径等个人信息，不纳入版本控制。
- 内部文档（`references/`）与生成产物（`output/`、`work/`）不纳入版本控制，避免内部文档和开发状态泄漏。

### License

MIT
