# Provider 参考文档

[English version](providers.en.md)

仅在切换 ASR / LLM provider，或修改 `scripts/mimo_podcast_tool.py` 中的 provider 默认值时阅读本文档。

## Provider 边界

- **ASR provider**：把音频分片转成文本。报告引擎会把文本包装成 `[HH:MM-HH:MM]` 时间窗口。
- **LLM provider**：根据带时间窗口的 transcript 生成时间线章节和最终表格。
- **报告引擎**：负责窗口分批、校验章节覆盖、修复缺失窗口、忽略幻觉出来的额外窗口，并写出最终 Markdown 报告。

不要把某个厂商特有的请求 payload 放进报告引擎里。

## 凭证职责

- 任务开始时，在下载、ASR 或 LLM 调用之前，先让用户选择 ASR 来源和总结方式。必须串行询问：先问 ASR 来源，收到并记录答案后，再问总结方式。可用交互式选择 UI 时，只展示当前这一个问题；否则用文字询问并等待用户回答。
- 对于音频、视频或 URL 输入，**ASR 凭证是必需的**；除非用户已经提供带时间窗口的 transcript。
- **LLM 凭证是可选的**。只有当用户明确选择 API LLM 总结时才需要。
- MiMo `--api-key` 可能只用于 ASR。不要因为用户提供了 MiMo key，就推断用户也同意用 MiMo LLM 总结；除非用户选择了 API LLM 模式。
- 如果用户有 ASR 凭证但没有 LLM 凭证，默认使用当前 IDE/Agent 模型辅助总结路线。

ASR 凭证矩阵：

| ASR 来源 | 需要的凭证 |
|---|---|
| MiMo ASR | `--api-key`、`--asr-api-key` 或 `MIMO_API_KEY` |
| 阿里 Qwen ASR | `--asr-provider aliyun-qwen --asr-api-key`、`DASHSCOPE_API_KEY` 或 `ALIYUN_API_KEY` |
| 腾讯 ASR | `--asr-provider tencent --tencent-secret-id --tencent-secret-key`，或腾讯环境变量 |
| 已有 transcript | 不需要 ASR API 凭证；使用 `--transcript-input` |

## ASR Providers

| Provider | CLI | 认证 | 默认端点 / 模型 | 说明 |
|---|---|---|---|---|
| MiMo Token Plan | `--asr-provider mimo` | `--api-key`、`--asr-api-key` 或 `MIMO_API_KEY` | `https://token-plan-sgp.xiaomimimo.com/v1`，`mimo-v2.5-asr` | 使用带 `input_audio` 的 `/chat/completions`；不要调用 `/audio/transcriptions`。 |
| 阿里 Qwen ASR | `--asr-provider aliyun-qwen` | `--asr-api-key`、`DASHSCOPE_API_KEY` 或 `ALIYUN_API_KEY` | `https://dashscope.aliyuncs.com/compatible-mode/v1`，`qwen3-asr-flash` | 使用 OpenAI-compatible chat 和 `input_audio`。需要确认用户账号/地域可用该模型。 |
| 腾讯云 ASR | `--asr-provider tencent` | `--tencent-secret-id`、`--tencent-secret-key` 或腾讯环境变量 | region `ap-guangzhou`，engine `16k_zh` | 使用腾讯云录音识别任务轮询。需要 `tencentcloud-sdk-python`。 |

腾讯专用参数：

```bash
--tencent-region ap-guangzhou
--tencent-engine-model-type 16k_zh
--tencent-res-text-format 0
--tencent-poll-interval 3
--tencent-max-polls 120
```

## LLM Providers

除 MiMo 外，所有 LLM provider 都按 OpenAI-compatible `chat/completions` 客户端调用。

当前 IDE 模型不是脚本内可直接调用的 provider，除非该 IDE 暴露了 OpenAI-compatible API 端点。对于没有这种端点的 IDE 模型总结，Agent 需要生成 `batch_*.md` 章节文件，再通过 `--manual-sections-dir` 合并；不要添加假的 `--llm-provider ide` 标签。

| Provider | CLI | 默认 Base URL | 默认模型 | 环境变量 |
|---|---|---|---|---|
| MiMo | `--llm-provider mimo` | `https://token-plan-sgp.xiaomimimo.com/v1` | `mimo-v2.5-pro` | `MIMO_API_KEY` |
| 阿里 | `--llm-provider aliyun` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | `DASHSCOPE_API_KEY`、`ALIYUN_API_KEY` |
| 腾讯混元 | `--llm-provider tencent` | `https://api.hunyuan.cloud.tencent.com/v1` | `hunyuan-turbos-latest` | `HUNYUAN_API_KEY`、`TENCENT_HUNYUAN_API_KEY` |
| 智谱 / BigModel | `--llm-provider zhipu` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` | `ZAI_API_KEY`、`ZHIPUAI_API_KEY`、`BIGMODEL_API_KEY` |
| Kimi / Moonshot | `--llm-provider kimi` | `https://api.moonshot.ai/v1` | `kimi-k2.6` | `MOONSHOT_API_KEY`、`KIMI_API_KEY` |
| MiniMax | `--llm-provider minimax` | `https://api.minimax.io/v1` | `MiniMax-M3` | `MINIMAX_API_KEY` |
| 自定义 | `--llm-provider openai-compatible` | 用户提供 | 用户提供 | `LLM_API_KEY` |

使用以下参数覆盖默认值：

```bash
--llm-base-url "https://provider.example/v1"
--llm-model "model-name"
--llm-api-key "sk-xxxx"
```

## 推荐组合

- 未选择 LLM API 时的默认路线：任意内置 ASR provider + 当前 IDE/Agent 辅助总结。
- 纯 API 路线：内置 ASR provider + 明确指定 `--llm-provider` / `--llm-api-key`。
- 降低对 MiMo ASR 的依赖：阿里 Qwen ASR + 任意 OpenAI-compatible LLM。
- 腾讯 ASR 适合已经有腾讯云账号和录音识别额度的用户，但它是异步任务，每个分片会更慢。
- 智谱、Kimi、MiniMax、阿里、腾讯混元都可以在 transcript 窗口可靠时生成目标报告；脚本的分批和校验机制比单纯上下文长度更关键。

## Provider 变更检查清单

- 保持 transcript 窗口格式不变：`[HH:MM-HH:MM]\ntext`。
- 运行 `python scripts/mimo_podcast_tool.py --self-test`。
- 运行 `python -m py_compile scripts/mimo_podcast_tool.py`。
- 长播客前先做一次短音频真实 ASR 测试。
- 处理真实长播客时，使用 `--save-transcript`，之后用 `--transcript-input` 反复生成/调整报告，避免重复消耗 ASR 成本。
