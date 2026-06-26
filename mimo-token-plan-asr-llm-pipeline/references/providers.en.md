# Provider Reference

[中文版本](providers.md)

Use this reference only when switching ASR/LLM providers or changing provider defaults in `scripts/mimo_podcast_tool.py`.

## Provider Boundaries

- **ASR provider**: turns an audio chunk into text. The report engine wraps that text in `[HH:MM-HH:MM]` windows.
- **Proofreading LLM task**: turns raw windowed ASR into a readable `{base_name}_校对.txt` while preserving labels.
- **Summary LLM task**: generates timeline sections and the final table from the calibrated transcript.
- **Report engine**: batches windows, validates section coverage, repairs missing windows, ignores hallucinated extra windows, and writes the final Markdown report.

Do not put vendor-specific request payloads inside the report engine.

## Credential Roles

- At task start, ask the user to choose the ASR source and summary mode before running downloads, ASR, or LLM calls. Ask serially: first ASR source, then after the answer is recorded, ask summary mode. Use an interactive choice UI for the current single question when available; otherwise ask in text and wait.
- **ASR credentials are required** for audio/video/URL input unless the user already provides a windowed transcript.
- **LLM credentials are optional**. They are needed only when the user explicitly selects API LLM proofreading/summary.
- A MiMo `--api-key` may be used for ASR only. Do not infer that the user wants MiMo LLM summary unless they selected API LLM mode.
- If the user has ASR credentials but no LLM credentials, use the agent-assisted IDE proofreading and summary route by default.

ASR credential matrix:

| ASR source | Required credential |
|---|---|
| MiMo ASR | `--api-key`, `--asr-api-key`, or `MIMO_API_KEY` |
| Alibaba Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`, `DASHSCOPE_API_KEY`, or `ALIYUN_API_KEY` |
| Tencent ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key`, or Tencent environment variables |
| Existing transcript | No ASR API credential; use `--transcript-input` |

## ASR Providers

| Provider | CLI | Auth | Default endpoint/model | Notes |
|---|---|---|---|---|
| MiMo Token Plan | `--asr-provider mimo` | `--api-key`, `--asr-api-key`, or `MIMO_API_KEY` | `https://token-plan-sgp.xiaomimimo.com/v1`, `mimo-v2.5-asr` | Uses `/chat/completions` with `input_audio`; never use `/audio/transcriptions`. |
| Alibaba Qwen ASR | `--asr-provider aliyun-qwen` | `--asr-api-key`, `DASHSCOPE_API_KEY`, or `ALIYUN_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1`, `qwen3-asr-flash` | Uses OpenAI-compatible chat with `input_audio`. Verify model availability in the user's region/account. |
| Tencent Cloud ASR | `--asr-provider tencent` | `--tencent-secret-id`, `--tencent-secret-key`, or Tencent env vars | region `ap-guangzhou`, engine `16k_zh` | Uses Tencent Cloud recording-recognition task polling. Requires `tencentcloud-sdk-python`. |

Tencent-specific options:

```bash
--tencent-region ap-guangzhou
--tencent-engine-model-type 16k_zh
--tencent-res-text-format 0
--tencent-poll-interval 3
--tencent-max-polls 120
```

## LLM Providers

All non-MiMo LLM providers use an OpenAI-compatible chat/completions client.

The current IDE model is not a callable script provider unless the IDE exposes an OpenAI-compatible API endpoint. For IDE-model proofreading/summaries without such an endpoint, the agent first proofreads the transcript windows, then generates `batch_*.md` section files and uses `--manual-sections-dir`; do not add a fake `--llm-provider ide` label.

| Provider | CLI | Default base URL | Default model | Env vars |
|---|---|---|---|---|
| MiMo | `--llm-provider mimo` | `https://token-plan-sgp.xiaomimimo.com/v1` | `mimo-v2.5-pro` | `MIMO_API_KEY` |
| Alibaba | `--llm-provider aliyun` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | `DASHSCOPE_API_KEY`, `ALIYUN_API_KEY` |
| Tencent Hunyuan | `--llm-provider tencent` | `https://api.hunyuan.cloud.tencent.com/v1` | `hunyuan-turbos-latest` | `HUNYUAN_API_KEY`, `TENCENT_HUNYUAN_API_KEY` |
| Zhipu / BigModel | `--llm-provider zhipu` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` | `ZAI_API_KEY`, `ZHIPUAI_API_KEY`, `BIGMODEL_API_KEY` |
| Kimi / Moonshot | `--llm-provider kimi` | `https://api.moonshot.ai/v1` | `kimi-k2.6` | `MOONSHOT_API_KEY`, `KIMI_API_KEY` |
| MiniMax | `--llm-provider minimax` | `https://api.minimax.io/v1` | `MiniMax-M3` | `MINIMAX_API_KEY` |
| Custom | `--llm-provider openai-compatible` | user supplied | user supplied | `LLM_API_KEY` |

Override defaults with:

```bash
--llm-base-url "https://provider.example/v1"
--llm-model "model-name"
--llm-api-key "sk-xxxx"
```

## Recommended Combinations

- Default when no LLM API is selected: any supported ASR provider + agent-assisted IDE proofreading and summary.
- API-only path: supported ASR provider + explicit `--llm-provider` / `--llm-api-key`; the script automatically proofreads before summary.
- Lower ASR dependency on MiMo: Alibaba Qwen ASR + any OpenAI-compatible LLM.
- Tencent ASR is useful when a Tencent Cloud account and recording-recognition quota are already available, but it is async and slower per chunk.
- Zhipu, Kimi, MiniMax, Alibaba, Tencent Hunyuan can all proofread and generate the target report if the transcript already has reliable windows; the script's batching/validation matters more than raw context length.

## Provider Change Checklist

- Keep transcript window format unchanged: `[HH:MM-HH:MM]\ntext`.
- The proofreading stage must keep the same window count and order; do not let provider prompts become summary tasks.
- Run `python scripts/mimo_podcast_tool.py --self-test`.
- Run `python -m py_compile scripts/mimo_podcast_tool.py`.
- Do a short real ASR test before a long podcast.
- For real long podcasts, use `--save-transcript`, then iterate reports with `--transcript-input` to avoid repeating ASR cost.
