# MiMo-V2.5 Audio Rules Embedded in This Skill

本文件记录 Skill 内置的 MiMo-V2.5-TTS / ASR 调用规则，便于维护和排错。

## TTS

Endpoint:

```text
POST https://api.xiaomimimo.com/v1/chat/completions
```

关键规则：

- 合成目标文本必须放在 `messages[].role=assistant` 的 `content` 中。
- `user.content` 用于自然语言风格控制、场景控制、情绪控制和 voice design prompt。
- 音频标签控制放在 `assistant.content` 中，可用 `speech_prefix_tags` 自动加到开头。
- 非流式默认 `audio.format=wav`。
- 流式调用使用 `audio.format=pcm16`。
- 流式 PCM16 为 24kHz、16-bit、mono；脚本会写入 WAV 容器。
- 输出文件名统一使用 `.wav`；`pcm16` 只表示接口返回 chunk 的编码格式，不表示保存为 `.pcm16` 裸流。
- 默认只发送一种认证 Header：`api-key`。如运行环境需要 OpenAI-style 鉴权，可使用 `--auth-mode bearer`。

## TTS models

| Model | What it does | Restrictions |
|---|---|---|
| `mimo-v2.5-tts` | Preset voice synthesis | Uses preset `voice`; supports low-latency stream |
| `mimo-v2.5-tts-voicedesign` | Text-described voice creation | Do not pass preset `voice`; use `voice_design_prompt`; low-latency streaming is not available, only compatibility streaming |
| `mimo-v2.5-tts-voiceclone` | Clone voice from audio sample | Use `.mp3`/`.wav` sample as data URL; low-latency streaming is not available, only compatibility streaming |

## Preset voices

```text
mimo_default, 冰糖, 茉莉, 苏打, 白桦, Mia, Chloe, Milo, Dean
```

## Voice design prompt rules

Recommended prompt length: 1-4 sentences.

Good dimensions:

- gender / age
- timbre / texture
- emotion / tone
- speed / rhythm
- role / persona
- speaking style
- scene

Avoid:

- contradictory voice requirements
- vague words like “普通的” or “正常的”
- post-processing terms such as reverb, EQ, compression

## Voice clone sample rules

- Supported sample formats: `.mp3`, `.wav`
- Data URL format: `data:audio/mpeg;base64,...` or `data:audio/wav;base64,...`
- Base64 encoded sample size limit: 10 MB

Use `voice_sample_path` when possible; the script converts it to a data URL automatically.

## ASR

Endpoint:

```text
POST https://api.xiaomimimo.com/v1/chat/completions
```

Payload pattern:

```json
{
  "model": "mimo-v2.5-asr",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "input_audio",
          "input_audio": {
            "data": "data:audio/wav;base64,$BASE64_AUDIO"
          }
        }
      ]
    }
  ],
  "asr_options": {
    "language": "zh"
  }
}
```

Rules:

- Supported input formats: `.wav`, `.mp3`
- Base64 encoded audio size limit: 10 MB
- `asr_options.language`: `auto`, `zh`, `en`
- Specify `zh` or `en` when known to improve recognition reliability.
