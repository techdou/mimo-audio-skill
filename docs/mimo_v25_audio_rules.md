# MiMo-V2.5 Audio Rules Embedded in This Skill

> **官方文档来源 / Official sources** (snapshot_date: 2026-07-15)
> - TTS: https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5
> - ASR:  https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition
> - LLM-friendly index: https://mimo.mi.com/llms.txt
>
> 本文件是人工维护的规则副本,可能滞后于官方文档。运行 `python scripts/check_official_docs.py`
> 可自动对比本地规则与官方 `.md` 源、并探测 `/v1/models` 是否仍列出本 skill 依赖的模型。
> 详见 `docs/self_update.md`。

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
| `mimo-v2.5-tts` | Preset voice synthesis | Uses preset `voice`; supports low-latency stream and singing mode; does not support voice design or voice cloning |
| `mimo-v2.5-tts-voicedesign` | Text-described voice creation | Do not pass preset `voice`; use `voice_design_prompt`; supports `optimize_text_preview`; low-latency streaming is not available, only compatibility streaming |
| `mimo-v2.5-tts-voiceclone` | Clone voice from audio sample | Use `.mp3`/`.wav` sample as data URL; supports natural-language style instructions and audio tags; low-latency streaming is not available, only compatibility streaming |

## Preset voices

```text
mimo_default, 冰糖, 茉莉, 苏打, 白桦, Mia, Chloe, Milo, Dean
```

| Voice name | Voice ID | Language | Gender |
|---|---|---|---|
| MiMo-默认 | mimo_default | 因部署集群而异(中国集群默认冰糖,其他集群默认 Mia) | — |
| 冰糖 | 冰糖 | 中文 | 女性 |
| 茉莉 | 茉莉 | 中文 | 女性 |
| 苏打 | 苏打 | 中文 | 男性 |
| 白桦 | 白桦 | 中文 | 男性 |
| Mia | Mia | 英文 | 女性 |
| Chloe | Chloe | 英文 | 女性 |
| Milo | Milo | 英文 | 男性 |
| Dean | Dean | 英文 | 男性 |

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
- vague words like "普通的" or "正常的"
- post-processing terms such as reverb, EQ, compression

`mimo-v2.5-tts-voicedesign` 支持可选参数 `optimize_text_preview`:设为 `true` 时可对目标播报文本智能润色,此时可不传 assistant 消息。

## Director mode (导演模式)

voicedesign 的一种进阶写法,从角色/场景/指导三个维度刻画:

- 【角色】人物身份、性格底色、说话习惯。
- 【场景】此刻发生了什么、和谁说话、情绪处在什么位置。
- 【指导】语速、气息、停顿、重音、共鸣位置、音色质感、情绪起伏。

模型据此生成更富层次的演绎。适合角色配音、影视级内容。

## Audio tag control (音频标签控制)

在 `assistant.content` 中嵌入标签实现精细控制:

- **风格标签**(开头):`(风格1 风格2)待合成内容`,支持半角 `()`、全角 `（）`或 `[]`。
  - 基础情绪:开心/悲伤/愤怒/恐惧/惊讶/兴奋/委屈/平静/冷漠
  - 复合情绪:怅然/欣慰/无奈/愧疚/释然/嫉妒/厌倦/忐忑/动情
  - 整体语调:温柔/高冷/活泼/严肃/慵懒/俏皮/深沉/干练/凌厉
  - 音色定位:磁性/醇厚/清亮/空灵/稚嫩/苍老/甜美/沙哑/醇雅
  - 人设腔调:夹子音/御姐音/正太音/大叔音/台湾腔
  - 方言:东北话/四川话/河南话/粤语
  - 唱歌:`(唱歌)歌词`,歌词建议用中文;标签内标识支持 唱歌/sing/singing
- **音频标签**(任意位置插入):`[吸气]`、`[深呼吸]`、`[叹气]`、`[长叹一口气]`、`[喘息]`、`[屏息]`、`[紧张]`、`[害怕]`、`[激动]`、`[疲惫]`、`[笑]`、`[轻笑]`、`[大笑]`、`[冷笑]`、`[抽泣]`、`[呜咽]`、`[哽咽]`、`[颤抖]`、`[破音]`、`[沉默片刻]` 等。

## Voice clone sample rules

- Supported sample formats: `.mp3`, `.wav`
- Data URL format: `data:audio/mpeg;base64,...` or `data:audio/wav;base64,...`
- Base64 encoded sample size limit: 10 MB

Use `voice_sample_path` when possible; the script converts it to a data URL automatically.

voiceclone 也支持在 user message 中传入自然语言风格指令,以及在 assistant.content 中使用音频标签,控制方式与 `mimo-v2.5-tts` 一致。

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

ASR 核心能力(官方文档):

- 覆盖中英双语识别及自动语种检测,**原生支持粤语、吴语、闽南语、四川话等中国方言**(通过 `auto` 或语种接近的主语言触发)。
- 在噪声、远场拾音、多人重叠对话等复杂声学条件下保持稳定识别,支持带伴奏的歌词转写。
- 精准识别古诗词、专业术语、人名地名等知识密集型内容,自动生成标点无需后处理。
