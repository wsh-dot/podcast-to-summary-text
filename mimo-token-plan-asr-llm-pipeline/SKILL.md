---
name: mimo-token-plan-asr-llm-pipeline
description: 将本地音频/视频、Bilibili/B站、小宇宙等 URL 或已有带时间窗口 transcript 转为经校对的逐窗口时间线播客摘要。支持 MiMo Token Plan、阿里 Qwen、阶跃星辰 StepAudio 2.5（普通 API / Step Plan）和腾讯 ASR，以及 IDE/Agent 或多种 LLM API 总结；B站固定使用 BBDown 1.6.3，其他 URL 使用 yt-dlp。Use for podcast/video transcription, StepFun/StepAudio ASR, Step Plan speech API, ASR proofreading, timeline notes, Bilibili downloads, MiMo `tp-` credentials, `[HH:MM-HH:MM]` transcripts, or 播客总结、视频转写、B站总结、小宇宙笔记、带时间点摘要。
---

# 时间线播客转写与摘要

使用 `scripts/mimo_podcast_tool.py` 执行确定性下载、ASR、校对、分批总结、合并和校验。默认质量链为：

```text
媒体 -> [HH:MM-HH:MM] 原始转写 -> 逐窗口校对 -> 逐窗口时间线报告
```

## 工作流

1. 识别输入：本地媒体、B站 URL、其他 URL，或已有窗口化 transcript。
2. 依次确定 ASR 来源和总结方式。用户已经明确的信息直接记录，不重复询问。
3. 在两个选择都确定后执行相应路由；不得提前下载媒体、调用 ASR 或 LLM。
4. 校验 transcript 窗口、报告章节和速览表一一对应后再交付。

### 串行选择门

每轮最多询问一个选择：

1. **ASR 来源**：MiMo ASR、阿里 Qwen ASR、阶跃星辰普通 API、阶跃星辰 Step Plan、腾讯 ASR、已有 transcript。媒体或 URL 输入必须同时取得相应凭据；已有 transcript 直接记为已确定。选择阶跃星辰时必须明确普通计费还是 Step Plan 订阅额度。
2. **总结方式**：当前 IDE/Agent 模型（推荐）、指定 LLM API、仅导出 prompts。只有收到或推断出第一个答案后才能询问第二个。

用户未回答总结方式时使用 `ide-agent`。MiMo `--api-key` 默认只代表 ASR 授权，不代表用户同意调用 MiMo LLM。凭据只通过 CLI 参数或环境变量传给脚本，不写入报告、日志示例或仓库文件。

## 输入路由

| 输入 | 必须执行的路由 |
|---|---|
| 本地音频/视频 | 要求 ASR 凭据；视频先由 ffmpeg 提取音频。 |
| `bilibili.com`、其子域名、`b23.tv` | 仅用 BBDown；缺失时安装并校验固定版 1.6.3。需要登录态时使用 `--bilibili-cookie`、cookie 文件或 `BILIBILI_COOKIE`。 |
| 小宇宙或其他 HTTP/HTTPS URL | 使用 `yt-dlp`，然后进入 ASR。 |
| 带 `[HH:MM-HH:MM]` 窗口的 `.txt` | 使用 `--transcript-input`，跳过下载和 ASR。`*_校对.txt` / `*_calibrated.txt` 默认跳过重复校对。 |

B站判断必须基于 `urllib.parse.urlparse()` 得到的真实 hostname。不得用字符串包含判断；`evil-bilibili.com` 或仅在查询参数出现 `bilibili.com` 的 URL 不是 B站。

阶跃星辰使用 `--asr-provider stepfun`。普通开放平台走默认 `/v1`；只有用户明确使用 Step Plan 订阅时才加 `--stepfun-plan`，走 `/step_plan/v1`：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only \
  --asr-provider stepfun --stepfun-plan --asr-api-key "..."
```

## 总结路由

### `ide-agent`（默认）

1. 只执行转写并保存原始窗口：

   ```bash
   python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-xxxx"
   ```

2. 逐窗口校对并保持标签不变，保存为 `<base_name>_校对.txt`。
3. 每 6 个窗口生成一个 `<base_name>_agent_sections/batch_*.md`。
4. 合并并校验：

   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_校对.txt --manual-sections-dir input_agent_sections
   ```

### `api-llm`

仅当用户明确选择 LLM provider 或提供 `--llm-provider` / `--llm-api-key` 时使用：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --asr-provider mimo --api-key "tp-xxxx" --llm-provider kimi --llm-api-key "sk-xxxx"
```

默认 `--proofread-mode separate`：每批执行“校对 -> 立即总结”，保存校对稿，最多并发 2 批。provider 限流时使用 `--llm-concurrency 1`。只需最终报告时使用 `--proofread-mode inline`；只需校对稿时使用 `--proofread-only`；只有已有可靠校对稿时才使用 `--proofread-mode skip` 或 `--no-proofread`。

### `manual`

仅在用户要求导出 prompts 或手动粘贴结果时使用：

```bash
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --export-ide-prompts
python scripts/mimo_podcast_tool.py --transcript-input input_转写.txt --manual-sections-dir input_ide_prompts/sections
```

导出的 prompt 必须要求模型先在窗口内校对，再写对应章节。

## 不可破坏的约束

- MiMo Token Plan ASR 必须调用 `https://token-plan-sgp.xiaomimimo.com/v1/chat/completions`，并把 base64 音频放入 `input_audio`；`tp-` key 用在标准 MiMo 域名或 `/audio/transcriptions` 会分别导致 401/404。
- 阶跃星辰 Step Plan ASR 必须调用 `https://api.stepfun.com/step_plan/v1/audio/asr/sse`；普通开放平台使用 `/v1/audio/asr/sse`。两条路径计费归属不同，不得自动互相回退。模型固定默认 `stepaudio-2.5-asr`，并从 `transcript.text.done.text` 读取最终文本；`error` 事件必须失败退出。
- 长媒体必须先分片；整段 base64 请求容易超限，并会失去可靠时间窗口。
- B站只能调用 BBDown。BBDown 下载、校验或执行失败时直接报错；回退到 `yt-dlp` 会违反路由和登录态约束。
- 校对必须保持全部 `[HH:MM-HH:MM]` 标签、顺序和实质内容；不得跨窗口移动、合并、删除或新增内容。校对结果不合格时保留该窗口原文。
- 每个 transcript 窗口必须且只能生成一个同名 `## HH:MM-HH:MM 主题` 章节。忽略额外窗口，只重试缺失窗口；仍缺失或重复时禁止写出最终报告。
- 不得生成 transcript 中没有的时间精度、嘉宾、主播、元数据、观点或直接引用。不确定原话时使用转述。

## 输出合同

最终 Markdown 必须包含标题、转写说明、逐窗口时间章节和 `## 核心观点速览` 表。章节数必须等于 transcript 窗口数；安静、过短、拒识或噪声窗口也要保留并标注限制。启用独立校对时同时保存 `<base_name>_校对.txt`，其窗口标签必须与 `<base_name>_转写.txt` 完全一致。

## 按需加载资源

中文任务读取无 `.en` 后缀的版本；英文任务读取 `.en.md`。同一主题只读一种语言，禁止同时加载两份。

| 触发条件 | 读取 |
|---|---|
| MiMo endpoint、payload、认证、401/404/413/429 | `references/api-reference.md` 或 `references/api-reference.en.md` |
| 阶跃星辰、StepAudio、Step Plan、SSE 事件或 `/audio/asr/sse` | `references/stepfun-asr.md` 或 `references/stepfun-asr.en.md` |
| B站域名判断、BBDown 安装/校验、cookie、故障 | `references/bilibili-download.md` |
| provider 切换、模型/base URL、凭据变量 | `references/providers.md` 或 `references/providers.en.md` |
| 校对 prompt、术语、质量下降、是否可跳过校对 | `references/proofreading.md` 或 `references/proofreading.en.md` |
| 报告格式、窗口规则、batch 输出或修复 | `references/timeline-report-format.md` 或 `references/timeline-report-format.en.md` |
| 修改实现 | 先读对应 reference，再检查 `scripts/mimo_podcast_tool.py` |

正常执行时不要预先读取所有 references；直接运行脚本。只有切换 provider 或修改 provider 默认值时才读取 provider reference。

## 验证

修改 skill 或脚本后运行：

```bash
python -m unittest discover -s tests -v
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/mimo_podcast_tool.py
python scripts/mimo_podcast_tool.py --help
```

交付前确认原始稿与校对稿窗口标签相同、报告时间章节数量相同，并存在一一对应的核心观点表。
