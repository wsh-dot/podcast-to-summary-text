# MiMo Token Plan API 参考文档

本文档详细说明 MiMo Token Plan API 的接口规范，包括 ASR 语音转写和 LLM 文本生成的请求/响应格式、参数说明和错误处理。

## API 基础配置

| 配置项 | 值 |
|--------|-----|
| Base URL | `https://token-plan-sgp.xiaomimimo.com/v1` |
| 认证方式 | Bearer Token（`Authorization: Bearer tp-xxxx`） |
| API Key 格式 | `tp-` 开头（Token Plan 专用 Key） |
| SDK 兼容 | OpenAI Python SDK（指定 `base_url`） |

### 初始化客户端

```python
from openai import OpenAI

client = OpenAI(
    api_key="tp-xxxxxxxxxxxx",           # Token Plan API Key
    base_url="https://token-plan-sgp.xiaomimimo.com/v1"
)
```

> **注意**：Token Plan Key（`tp-` 开头）只能在 Token Plan 端点使用。标准 API 端点 `https://api.xiaomimimo.com/v1` 会返回 `401 Unauthorized`。

---

## ASR 语音转写接口

### 端点

`POST /chat/completions`

> **关键**：MiMo ASR 不走标准 OpenAI 的 `/audio/transcriptions` 端点（该端点返回 `404 Not Found`）。ASR 通过 `/chat/completions` 接口调用，音频以 base64 编码后放在 message 的 `input_audio` 字段中。

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定为 `mimo-v2.5-asr` |
| `messages` | array | 是 | 包含一条 user message，content 为音频数据 |
| `asr_options` | object | 否 | ASR 选项，如 `{"language": "auto"}` |

### 请求格式

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

### 音频编码要求

- 格式：MP3（推荐）
- 编码：base64
- 前缀：必须以 `data:audio/mpeg;base64,` 开头
- 放置位置：`messages[0].content[0].input_audio.data`

```python
import base64

with open("chunk.mp3", "rb") as f:
    audio_b64 = base64.b64encode(f.read()).decode()

audio_data_uri = f"data:audio/mpeg;base64,{audio_b64}"
```

### 使用 OpenAI SDK 调用

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

# 获取转写文本
transcript = response.choices[0].message.content
```

> **注意**：`asr_options` 不是 OpenAI SDK 的标准参数，需通过 `extra_body` 传递。

### 响应格式

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
        "content": "这是转写出的文字内容..."
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

转写文本通过 `response.choices[0].message.content` 获取（注意与标准 Whisper 的 `response.text` 不同）。

### 分片大小建议

| 分片时长 | 原始大小 | base64 后大小 | 是否安全 |
|----------|----------|---------------|----------|
| 1 分钟 | ~1 MB | ~1.3 MB | 安全，但调用次数高 |
| 3 分钟 | ~3 MB | ~4 MB | 时间线报告默认 |
| 5 分钟 | ~5 MB | ~6.7 MB | 吞吐优先时可用 |
| 10 分钟 | ~10 MB | ~13.3 MB | 可能超限 |
| 30 分钟 | ~30 MB | ~40 MB | 超限 |

默认使用 3 分钟（180 秒）分片，以便报告生成 `HH:MM` 时间点章节。若只需要普通转写或摘要，可使用 5 分钟提高吞吐；遇到 413 时继续缩短分片。

---

## LLM 文本生成接口

### 端点

`POST /chat/completions`

### 请求参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | string | 是 | 固定为 `mimo-v2.5-pro` |
| `messages` | array | 是 | 对话消息列表 |
| `max_tokens` | int | 否 | 最大生成 token 数（标准版 4096，深度版 8192） |
| `temperature` | float | 否 | 温度参数，默认 0.7 |

### 请求格式

```python
response = client.chat.completions.create(
    model="mimo-v2.5-pro",
    messages=[
        {
            "role": "system",
            "content": "你是一位专业的内容分析师。"
        },
        {
            "role": "user",
            "content": "请对以下转写文本生成结构化报告：\n\n..."
        }
    ],
    max_tokens=8192
)

report = response.choices[0].message.content
```

### 响应格式

与标准 OpenAI Chat Completions 格式一致，文本通过 `response.choices[0].message.content` 获取。

---

## 错误处理

### 常见错误码

| HTTP 状态码 | 原因 | 解决方案 |
|-------------|------|----------|
| 401 | API Key 无效或端点不匹配 | 确认使用 Token Plan Key（`tp-` 开头）和 Token Plan 端点 |
| 404 | 请求了不支持的端点（如 `/audio/transcriptions`） | 改用 `/chat/completions` + base64 方式 |
| 413 | 请求体过大 | 减小音频分片时长（从 5 分钟改为 3 分钟） |
| 429 | 请求频率超限 | 降低并发，加入重试机制 |
| 500 | 服务器内部错误 | 重试，指数退避 |

### Windows 环境变量问题

在 Windows cmd 中，`set VAR=value && python script.py` 可能因空格或编码问题失效。解决方案：

```bash
# 方案 1：使用 --api-key 参数（推荐）
python script.py --api-key "tp-xxxx"

# 方案 2：使用 cmd /c
cmd /c "set MIMO_API_KEY=tp-xxxx && python script.py"

# 方案 3：使用 PowerShell
$env:MIMO_API_KEY="tp-xxxx"; python script.py
```
