# Troubleshooting

## `MIMO_API_KEY is required unless --dry-run is used`

设置环境变量：

```bash
export MIMO_API_KEY="sk-你的key"
export MIMO_BASE_URL="https://api.xiaomimimo.com/v1"
```

或在命令行显式传入：

```bash
python scripts/mimo_tts_batch.py --api-key "sk-xxx" ...
```

## Token Plan 调不通

Token Plan 的 Key 与普通 API Key 不可混用。请同时确认：

- Key 是 `tp-...` 还是 `sk-...`
- `MIMO_BASE_URL` 是否来自 Token Plan 页面
- Base URL 是否包含 `/v1`

## TTS 返回 JSON 但没有音频文件

curl 直接调用只会返回 JSON，音频在 `choices[0].message.audio.data` 中，是 Base64。使用本 Skill 的 `mimo_tts_batch.py` 会自动解码并写入音频文件。

## `response does not contain choices[0].message.audio.data`

常见原因：

- 使用了 ASR 模型却运行了 TTS 脚本
- 请求被服务端拒绝，返回的是错误 JSON
- 传入了不符合模型要求的字段，例如 voicedesign 误传 preset `voice`
- API 兼容层响应结构发生变化；可加 `--save-raw-response` 查看原始响应

## `streaming TTS must use format=pcm16`

流式 TTS 应使用：

```json
"audio": { "format": "pcm16" },
"stream": true
```

本 Skill 中可以直接加：

```bash
--stream
```

脚本会把 PCM16 chunk 写入 WAV 容器。

## voicedesign 效果不稳定

优化 `voice_design_prompt`：

- 控制在 1-4 句
- 写清年龄、性别、音色、节奏、情绪、角色
- 避免“普通的”“正常的”“随便”这类模糊词
- 避免“混响、EQ、压缩”等后期处理词

## voiceclone 报错

确认：

- `voice_sample_path` 指向真实存在的 `.mp3` 或 `.wav`
- Base64 编码后不超过 10 MB
- 如果直接传 `voice`，必须是 `data:audio/wav;base64,...` 或 `data:audio/mpeg;base64,...`

## ASR 空文本

可能原因：

- 音频太短或是静音
- 语言参数不合适，尝试 `--language auto` 或明确 `--language zh`
- 原始响应结构变化，使用 `--save-raw-response` 查看完整 JSON

## 429 / 限流

增加间隔和重试：

```bash
python scripts/mimo_tts_batch.py ... --sleep-between 1.5 --retries 4
```

脚本会读取服务端的 `Retry-After` 头并等待。

## 只重跑失败音频

```bash
python scripts/mimo_tts_batch.py \
  --segments output/segments.json \
  --manifest output/audio_manifest.json \
  --failed-only \
  --overwrite
```
