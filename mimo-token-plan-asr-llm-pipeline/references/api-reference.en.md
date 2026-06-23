# MiMo Token Plan API Reference

[中文版本](api-reference.md)

This document describes the MiMo Token Plan API contract used by this skill, including ASR transcription, LLM text generation, request and response shapes, parameters, and error handling.

## API Base Configuration

| Item | Value |
|------|-------|
| Base URL | `https://token-plan-sgp.xiaomimimo.com/v1` |
| Authentication | Bearer token (`Authorization: Bearer tp-xxxx`) |
| API key format | Starts with `tp-` (Token Plan key) |
| SDK compatibility | OpenAI Python SDK with a custom `base_url` |

### Initialize Client

```python
from openai import OpenAI

client = OpenAI(
    api_key="tp-xxxxxxxxxxxx",           # Token Plan API key
    base_url="https://token-plan-sgp.xiaomimimo.com/v1"
)
```

> **Note**: Token Plan keys that start with `tp-` must be used with the Token Plan endpoint. The standard API endpoint `https://api.xiaomimimo.com/v1` returns `401 Unauthorized` for these keys.

---

## ASR Transcription API

### Endpoint

`POST /chat/completions`

> **Important**: MiMo ASR does not use the standard OpenAI `/audio/transcriptions` endpoint. That endpoint returns `404 Not Found`. MiMo ASR is called through `/chat/completions`, with base64 audio placed in the message `input_audio` field.

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Fixed to `mimo-v2.5-asr` |
| `messages` | array | Yes | Contains one user message whose content holds the audio data |
| `asr_options` | object | No | ASR options, for example `{"language": "auto"}` |

### Request Shape

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
            "data": "data:audio/mpeg;base64,AAAA...."
          }
        }
      ]
    }
  ],
  "asr_options": {
    "language": "auto"
  }
}
```

### Audio Encoding Requirements

- Format: MP3 is recommended.
- Encoding: base64.
- Prefix: must start with `data:audio/mpeg;base64,`.
- Location: `messages[0].content[0].input_audio.data`.

```python
import base64

with open("chunk.mp3", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

audio_data_uri = f"data:audio/mpeg;base64,{audio_b64}"
```

### Call With OpenAI SDK

```python
response = client.chat.completions.create(
    model="mimo-v2.5-asr",
    messages=[{
        "role": "user",
        "content": [{
            "type": "input_audio",
            "input_audio": {
                "data": f"data:audio/mpeg;base64,{audio_b64}"
            }
        }]
    }],
    extra_body={"asr_options": {"language": "auto"}}
)

transcript = response.choices[0].message.content
```

> **Note**: `asr_options` is not a standard OpenAI SDK parameter. Pass it through `extra_body`.

### Response Shape

```json
{
  "id": "chatcmpl-xxxx",
  "object": "chat.completion",
  "model": "mimo-v2.5-asr",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Transcribed text content..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

Read the transcript from `response.choices[0].message.content`. This differs from the standard Whisper-style `response.text`.

### Recommended Chunk Size

| Chunk duration | Raw size | Base64 size | Safety |
|----------------|----------|-------------|--------|
| 1 minute | ~1 MB | ~1.3 MB | Safe, but more API calls |
| 3 minutes | ~3 MB | ~4 MB | Timeline-report default |
| 5 minutes | ~5 MB | ~6.7 MB | Useful when throughput matters |
| 10 minutes | ~10 MB | ~13.3 MB | May exceed request limits |
| 30 minutes | ~30 MB | ~40 MB | Too large |

The default is 3-minute chunks so the report can produce `HH:MM` timeline sections. If you only need plain transcription or a brief summary, 5-minute chunks can improve throughput. If a request returns `413`, shorten the chunk duration.

---

## LLM Text Generation API

### Endpoint

`POST /chat/completions`

### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Fixed to `mimo-v2.5-pro` |
| `messages` | array | Yes | Chat message list |
| `max_tokens` | int | No | Maximum generated tokens, for example 4096 or 8192 |
| `temperature` | float | No | Sampling temperature. Default is 0.7 |

### Request Shape

```python
response = client.chat.completions.create(
    model="mimo-v2.5-pro",
    messages=[
        {
            "role": "system",
            "content": "You are a professional content analyst."
        },
        {
            "role": "user",
            "content": "Generate a structured report from the following transcript:\n\n..."
        }
    ],
    max_tokens=8192
)

report = response.choices[0].message.content
```

### Response Shape

The response follows the standard OpenAI Chat Completions shape. Read generated text from `response.choices[0].message.content`.

---

## Error Handling

### Common Error Codes

| HTTP status | Cause | Fix |
|-------------|-------|-----|
| 401 | Invalid API key or endpoint mismatch | Use a Token Plan key that starts with `tp-` and the Token Plan endpoint |
| 404 | Unsupported endpoint, such as `/audio/transcriptions` | Use `/chat/completions` with base64 audio |
| 413 | Request body too large | Reduce audio chunk duration, for example from 5 minutes to 3 minutes |
| 429 | Rate limit exceeded | Lower concurrency and add retries |
| 500 | Server-side error | Retry with exponential backoff |

### Windows Environment Variable Notes

In Windows cmd, `set VAR=value && python script.py` may fail because of spacing or encoding issues. Use one of these options:

```bash
# Option 1: use --api-key directly, recommended
python script.py --api-key "tp-xxxx"

# Option 2: use cmd /c
cmd /c "set MIMO_API_KEY=tp-xxxx && python script.py"

# Option 3: use PowerShell
$env:MIMO_API_KEY="tp-xxxx"; python script.py
```
