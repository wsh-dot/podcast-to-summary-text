# StepFun StepAudio ASR Reference

[中文版本](stepfun-asr.md)

Read this file only when selecting StepFun ASR, choosing standard versus Step Plan routing, debugging SSE events, or changing the provider.

## Routing Decision

| User authorization | CLI | Endpoint |
|---|---|---|
| Standard platform billing | `--asr-provider stepfun` | `POST https://api.stepfun.com/v1/audio/asr/sse` |
| Step Plan subscription credits | `--asr-provider stepfun --stepfun-plan` | `POST https://api.stepfun.com/step_plan/v1/audio/asr/sse` |

The request contract is the same, but billing ownership differs. **NEVER** fall back from one path to the other after failure; that could charge an account the user did not select. Step Plan currently exposes `stepaudio-2.5-asr` only through HTTP + SSE.

Credentials come from `--asr-api-key`, `STEPFUN_API_KEY`, or `STEP_API_KEY`. Use `--asr-base-url` for a custom gateway; when supplied, it takes precedence over `--stepfun-plan` routing.

Provider-specific options:

```bash
--stepfun-plan          # use the Step Plan path; default is standard /v1
--stepfun-language zh   # optional; omit for model language detection
--stepfun-timeout 45    # per-chunk SSE request timeout in seconds
```

## Request Contract

- Headers: `Authorization: Bearer ...`, `Content-Type: application/json`, and `Accept: text/event-stream`.
- ffmpeg produces MP3 chunks; put raw base64 in `audio.data`, without a data-URI prefix.
- `audio.input.transcription.model` defaults to `stepaudio-2.5-asr`.
- `enable_itn` is always `true`; send `--stepfun-language` only when the user specifies a language.
- MP3 needs only `{"type":"mp3"}`. `rate`, `bits`, and `channel` are required only for PCM.

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

## SSE Handling

- `transcript.text.delta`: accumulate `delta`, only as fallback when the final event has no text.
- `transcript.text.done`: use `text` as the complete transcript.
- `error`: raise with `message` so the outer retry policy handles it; never convert an error event into an empty transcript.
- If the connection ends without `transcript.text.done`, treat it as truncated and retry; never deliver accumulated deltas.
- Ignore blank lines, `event:` lines, and a `[DONE]` sentinel.

## Official Documentation

- [StepAudio 2.5 ASR model](https://platform.stepfun.com/docs/zh/guides/models/stepaudio-2.5-asr)
- [HTTP + SSE ASR API](https://platform.stepfun.com/docs/zh/api-reference/audio/asr-sse)
- [Step Plan audio integration](https://platform.stepfun.com/docs/zh/step-plan/integrations/audio-api)
- [Synchronous audio transcription API](https://platform.stepfun.com/docs/zh/api-reference/audio/transcriptions) (available on the standard platform; this skill uses SSE for consistent standard/subscription behavior)

## Change Validation

```bash
python -m unittest tests.test_stepfun_asr -v
python scripts/mimo_podcast_tool.py --self-test
python scripts/mimo_podcast_tool.py --help
```

Use a short clip for a real smoke test and explicitly decide whether `--stepfun-plan` is present. Automated tests must not consume user credits.
