# 阶跃星辰 StepAudio ASR 参考

[English version](stepfun-asr.en.md)

仅在选择阶跃星辰 ASR、判断普通 API 与 Step Plan 路径、排查 SSE 事件或修改 provider 时读取本文档。

## 路由决策

| 用户授权 | CLI | 请求地址 |
|---|---|---|
| 普通开放平台计费 | `--asr-provider stepfun` | `POST https://api.stepfun.com/v1/audio/asr/sse` |
| Step Plan 订阅额度 | `--asr-provider stepfun --stepfun-plan` | `POST https://api.stepfun.com/step_plan/v1/audio/asr/sse` |

两条路径参数相同，但计费归属不同。**NEVER** 在其中一条失败后自动回退另一条；这会让费用落到用户未选择的账户体系。Step Plan 当前只支持 HTTP + SSE 方式调用 `stepaudio-2.5-asr`。

凭据使用 `--asr-api-key`、`STEPFUN_API_KEY` 或 `STEP_API_KEY`。自定义网关可用 `--asr-base-url` 覆盖前缀；覆盖后 `--stepfun-plan` 不再改写该值。

常用专用参数：

```bash
--stepfun-plan          # 使用 Step Plan 路径；缺省为普通 /v1
--stepfun-language zh   # 可选；不传则交由模型自动识别
--stepfun-timeout 45    # 单个 SSE 分片请求超时秒数
```

## 请求合同

- Headers：`Authorization: Bearer ...`、`Content-Type: application/json`、`Accept: text/event-stream`。
- 分片经 ffmpeg 转为 MP3；`audio.data` 只放原始 base64，不加 data URI 前缀。
- `audio.input.transcription.model` 默认为 `stepaudio-2.5-asr`。
- `enable_itn` 固定为 `true`；只有用户明确语言时才传 `--stepfun-language`。
- MP3 的 format 只需 `{"type":"mp3"}`；`rate`、`bits`、`channel` 仅在 PCM 时必填。

```json
{
  "audio": {
    "data": "base64_encoded_audio",
    "input": {
      "transcription": {
        "model": "stepaudio-2.5-asr",
        "enable_itn": true
      },
      "format": {"type": "mp3"}
    }
  }
}
```

## SSE 处理

- `transcript.text.delta`：累计 `delta`，只作为最终事件缺少文本时的回退。
- `transcript.text.done`：以 `text` 作为完整转写结果。
- `error`：使用 `message` 抛错，让外层退避重试；不得把错误事件当空转写。
- 连接未出现 `transcript.text.done` 就结束：视为截断并重试，禁止交付累计 delta。
- 空行、`event:` 行和 `[DONE]` 哨兵可忽略。

## 相关官方文档

- [StepAudio 2.5 ASR 模型](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-2.5-asr)
- [HTTP + SSE 语音识别 API](https://platform.stepfun.com/docs/zh/api-reference/audio/asr-sse)
- [Step Plan 语音模型接入](https://platform.stepfun.com/docs/zh/step-plan/integrations/audio-api)
- [同步音频转写 API](https://platform.stepfun.com/docs/zh/api-reference/audio/transcriptions)（普通开放平台可用；本 skill 为统一普通/订阅行为而固定使用 SSE）

## 变更验证

```bash
python -m unittest tests.test_stepfun_asr -v
python scripts/mimo_podcast_tool.py --self-test
python scripts/mimo_podcast_tool.py --help
```

真实音频 smoke test 必须先用短片段，并明确是否携带 `--stepfun-plan`；不要用自动测试消耗用户额度。
