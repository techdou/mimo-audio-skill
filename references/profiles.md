# 音色风格模板（Profile）

v2.0.0 新增。Profile 把"模型 + 音色 + 语气风格 + 音频标签"打包成一份可复用的 JSON，让同一套 TTS 管线在课程、小说、播客、短视频、个人克隆等场景间无缝切换。

## 存放位置

个人模板优先于内置模板：

| 目录 | 说明 |
| --- | --- |
| `<skill>/profiles/*.json` | 个人模板（已在 .gitignore 中排除，不随仓库提交） |
| `<skill>/templates/profiles/*.json` | 内置模板（随技能分发） |

## 字段定义

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 模板名，同时是文件名（不含 `.json`） |
| `label` | 否 | 人类可读的展示名 |
| `description` | 否 | 用途说明 |
| `model` | 是 | `mimo-v2.5-tts` / `mimo-v2.5-tts-voicedesign` / `mimo-v2.5-tts-voiceclone` |
| `voice` | 视模型 | 预置音色（preset 模型用）；voicedesign 必须为空 |
| `voice_design_prompt` | 视模型 | 1-4 句音色描述（voicedesign 用） |
| `voice_sample_path` | 视模型 | 本地 `.wav`/`.mp3` 样本（voiceclone 用） |
| `style_instruction` | 推荐 | 语气/风格指令，放进 `user.content` |
| `speech_prefix_tags` | 否 | 附加到 `assistant.content` 开头的风格标签，如 `["轻松","活泼"]` |
| `use_cases` | 否 | 适用场景标签 |

## 内置模板

| 模板名 | 模型 | 音色 | 适用 |
| --- | --- | --- | --- |
| `lecture-natural` | preset | 冰糖 | 课程讲解、教程旁白、知识口播 |
| `podcast-casual` | preset | 苏打 | 播客、访谈、口语化内容 |
| `novel-narration` | voicedesign | 文字设计 | 有声书、小说、故事旁白 |
| `short-video` | voicedesign | 文字设计 | 短视频口播、营销内容 |
| `example-personal-clone` | voiceclone | 样本 | 个人克隆模板示例（复制后修改） |

## 个人克隆模板

1. 复制示例：

```bash
python scripts/voice_profiles.py create \
  --name my-voice \
  --file templates/profiles/example-personal-clone.json
```

2. 编辑 `<skill>/profiles/my-voice.json`，把 `voice_sample_path` 换成自己的录音（30-60 秒、干净无背景音乐、`.wav`/`.mp3`、≤10MB）。
3. 校验：

```bash
python scripts/voice_profiles.py validate my-voice
```

技能已内置一个豆哥模板 `douge-lecture`（基于 2026-08-09 录音样本）。想派生变体（例如"豆哥·轻松版""豆哥·故事版"），复制该文件改 `name`、`label`、`style_instruction` 即可。

## 使用方式

### 1. 直接合成时指定

```bash
python scripts/mimo_tts_batch.py \
  --config templates/config.example.json \
  --segments output/segments.json \
  --profile douge-lecture \
  --out-dir output/audio \
  --manifest output/audio_manifest.json
```

`--profile` 只填充 segments 里缺失的字段；已有字段优先，不会被覆盖（`voice_profiles.py apply --overwrite` 可强制覆盖）。

### 2. 生成分段时指定

```bash
python scripts/make_segments.py \
  --input output/cleaned.txt \
  --output output/segments.json \
  --profile novel-narration
```

### 3. pipeline 场景快捷选择

```bash
python scripts/run_pipeline.py --input story.md --text-kind novel --tts --duration
python scripts/run_pipeline.py --input script.md --profile douge-lecture --tts --srt
```

`--text-kind` 取值：`lecture`（lecture-natural）、`novel`（novel-narration）、`podcast`（podcast-casual）、`marketing`（short-video）。显式 `--profile` 优先于 `--text-kind`。

### 4. 单独把模板灌入已有 segments

```bash
python scripts/voice_profiles.py apply \
  --profile short-video \
  --segments output/segments.json \
  --output output/segments_styled.json
```

## 设计取舍

- Profile 只做"缺省值注入"，不覆盖显式写的字段：单段特殊处理（比如某一段想要不同语气）仍然可行。
- 个人目录 `profiles/` 被 gitignore：样本路径属于个人环境，不应随仓库分发。
- 内置模板使用预置/文字设计音色，保证开箱可用；克隆模板只提供示例与个人使用。
