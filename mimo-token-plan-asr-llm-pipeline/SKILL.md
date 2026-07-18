---
name: mimo-token-plan-asr-llm-pipeline
description: 将本地音频/视频、Bilibili/B站、小宇宙、YouTube 等 URL 或已有 `[HH:MM-HH:MM]` transcript 转为经校对的逐窗口 Markdown 时间线和完全离线 HTML 图文速览，支持真实视频代表帧、证据校验及 IDE/Agent、manual、API LLM 三条总结路线。Use when asked for 播客总结、视频解析/转写、B站总结、小宇宙笔记、带时间点摘要、离线图文报告，或 MiMo Token Plan、阿里 Qwen、StepFun/StepAudio 2.5（普通 API / Step Plan）、腾讯 ASR；B站下载固定使用 BBDown 1.6.3，其他 URL 使用 yt-dlp。
---

# 时间线转写、摘要与离线图文速览

使用 `scripts/mimo_podcast_tool.py`。把 Markdown 视为事实主产物；HTML 是在校对稿和已验证 Markdown 之后生成的可降级增强产物。

```text
媒体 -> 窗口化 ASR -> 逐窗口校对 -> 已验证 Markdown
     -> 结构化视觉 batch -> 已验证 manifest -> 真实代表帧（可选） -> 离线 HTML/assets
```

## 决策门

在执行下载或外部 API 前依次确定两件事。用户已提供的信息直接采用，不重复询问。

1. **ASR 来源**：MiMo、阿里 Qwen、StepFun 普通 API、Step Plan、腾讯，或已有 transcript。
2. **总结路线**：`ide-agent`（默认）、`api-llm`，或 `manual`。

每轮最多询问一个选择。StepFun 必须明确普通计费还是 Step Plan；两者不得自动互相回退。用户只提供 ASR key 时不得推断其同意 LLM API，总结路线使用 `ide-agent`。

## 输入路由

| 输入 | 路由 |
|---|---|
| 本地音频 | 选定 ASR 后直接窗口化转写。 |
| 本地视频 | 保留原视频供 Markdown 后置帧提取；音轨仍先由 FFmpeg 提取后进入 ASR。 |
| Bilibili 子域或 `b23.tv` | 音频和 best-effort 视觉源都只用 BBDown 1.6.3；需要登录态时传 cookie。 |
| 其他 HTTP/HTTPS URL | 音频用 yt-dlp；视频视觉源 best-effort 请求不高于 720p。 |
| 窗口化 `.txt` | `--transcript-input`，跳过下载和 ASR；`*_校对.txt` / `*_calibrated.txt` 默认不重复校对。 |

B站必须按 `urlparse(...).hostname` 判定。`evil-bilibili.com` 或查询参数里出现 `bilibili.com` 都不是 B站。

## ASR 命令

MiMo Token Plan：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --api-key "tp-..."
```

StepFun 普通 API：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider stepfun --asr-api-key "..."
```

只有用户明确使用 Step Plan 订阅额度时添加：

```bash
python scripts/mimo_podcast_tool.py input.mp3 --transcribe-only --asr-provider stepfun --stepfun-plan --asr-api-key "..."
```

凭据只通过参数或环境变量传入。不要写进 prompt 文件、报告、示例、日志或仓库。

长音频转写会在输出目录维护与最终转写同名的 ASR checkpoint，并在每个完整窗口后原子写入。重跑相同输入、分片时长和媒体时长时自动跳过已完成的连续前缀；最终转写发布成功后删除 checkpoint。HTTP 429 会遵循 `Retry-After` 并扩大退避预算；StepFun 持续返回 `risk blocked` 时，只在原 3 分钟窗口内部拆成 1 分钟子片段，合并结果仍保留原窗口标签。

## 总结路线

### `ide-agent`（默认）

1. 运行 `--transcribe-only` 保存原始窗口稿。
2. 当前 Agent 逐窗口校对，保持全部标签和内容归属，保存 `<base>_校对.txt`。
3. 每 6 个窗口写入 `<base>_agent_sections/batch_*.md`。
4. 合并并校验 Markdown：

   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_校对.txt --manual-sections-dir input_agent_sections
   ```

5. 合并成功后 CLI 自动导出 visual batch prompts。当前 Agent 生成 JSON-only 结果，再按下方 prepare/render 阶段生成同一 HTML 合同；prompt 阶段失败只保留警告和 Markdown。

### `api-llm`

只有用户明确选择 LLM provider 或提供 LLM 凭据时使用。脚本在 Markdown 发布后自动执行受限 visual map-reduce，并尝试 HTML：

```bash
python scripts/mimo_podcast_tool.py input.mp3 \
  --asr-provider mimo --api-key "tp-..." \
  --llm-provider kimi --llm-api-key "sk-..."
```

默认 `--proofread-mode separate` 保存校对稿；限流时用 `--llm-concurrency 1`。`inline` 不产生独立校对稿；`skip` 只用于可靠的既有校对稿。

### `manual` 视觉三阶段

必须先有校对 transcript 和已验证 timeline Markdown。禁止让模型生成 HTML/CSS/JavaScript/SVG。

1. 导出精确窗口 batch prompts：

   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_校对.txt \
     --visual-report-input input_逐窗口深度解读.md --export-visual-prompts
   ```

2. 把 JSON-only batch 结果保存到 `batch_results/`，验证后生成 synthesis prompt：

   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_校对.txt \
     --visual-report-input input_逐窗口深度解读.md --prepare-visual-synthesis \
     --visual-prompts-dir input_visual_prompts
   ```

3. 把最终 JSON 保存为 `manifest.json`，再渲染：

   ```bash
   python scripts/mimo_podcast_tool.py --transcript-input input_校对.txt \
     --visual-report-input input_逐窗口深度解读.md \
     --manual-visual-dir input_visual_prompts --output-dir output
   ```

   视频可额外提供 `--visual-source-url` 或 `--visual-video-input`。视觉下载/帧失败只降级为 infographic-and-text HTML。

## 不可破坏的约束

- **绝不把 MiMo `tp-` key 发到标准 MiMo 域名或 `/audio/transcriptions`**：会分别产生 401/404；Token Plan ASR 必须走 `.../v1/chat/completions` 的 `input_audio`。
- **绝不在 StepFun 普通 API 与 Step Plan 间自动回退**：两条 endpoint 对应不同计费归属。
- **绝不整段提交长媒体**：先分片才能控制请求大小并保留可信时间窗口。
- **绝不手工拼接部分转写或删除有效 checkpoint**：恢复必须校验输入标识、分片时长、媒体时长和连续窗口前缀；不匹配时重新开始。
- **绝不让 B站回退到 yt-dlp**：这会破坏固定下载器、登录态和可重复性合同。
- **绝不改变窗口标签、顺序或内容归属**：校对失败时保留该窗口原文，不跨窗口搬运句子。
- **绝不发布缺失、重复、额外或乱序的 timeline 章节**：只修复缺失窗口，最终仍不完整则停止 Markdown。
- **绝不接受模型 HTML、CSS、JavaScript、SVG 或路径**：模型只产生 JSON；固定 renderer 负责转义、路径和离线资产。
- **绝不把帧当作机械配额**：只为高优先级章节从真实所属窗口提取，黑暗/空/损坏帧直接跳过。
- **绝不因 visual 阶段失败删除 Markdown 或校对稿**：警告必须指明保留的 Markdown；不得打印密钥或 transcript 内容。

## 输出合同

成功的 timeline 总结至少保留：

```text
<base>_校对.txt                 # separate/已有校对稿路线
<base>_逐窗口深度解读.md        # 权威事实产物
<base>_图文速览.html            # visual 成功时
<base>_图文速览_assets/
  frames/*.webp                 # 仅可用视频代表帧
```

全局 synthesis 必须先按顺序读完完整校对 transcript；批次结果只约束证据，不能代替全文阅读。超过 60 分钟且中文占主导的内容使用 compact editorial profile：约 1800–2500 个可见汉字、4 个核心结论、5 个主题、最多 8 张 renderer-owned CSS/SVG 信息图；不得调用 frame provider、不得输出视频截图或完整 transcript，最终只发布单个 HTML。其他语言和短内容保留原密度合同。页面必须完全离线、响应式、键盘可用。

## 按需加载

只读任务所需语言版本：中文读无 `.en` 后缀，英文读 `.en.md`。必须完整读取命中的 reference；不要预加载未命中的文件。

| 场景 | 必须读取 | 不要读取 |
|---|---|---|
| MiMo endpoint、payload、401/404/413/429 | `references/api-reference*.md` 对应语言 | 与当前 provider 无关的 StepFun 文档 |
| StepFun/StepAudio/SSE/Step Plan | `references/stepfun-asr*.md` 对应语言 | MiMo payload 文档 |
| provider/model/base URL/环境变量 | `references/providers*.md` 对应语言 | 未使用 provider 的详细 API 文档 |
| B站、BBDown、cookie、音频/视觉下载 | `references/bilibili-download.md` | yt-dlp 作为 B站 fallback 的任何方案 |
| 校对质量、术语或跳过校对 | `references/proofreading*.md` 对应语言 | visual schema 文档 |
| timeline 格式、窗口/batch 修复 | `references/timeline-report-format*.md` 对应语言 | provider 文档 |
| HTML、manifest、三路线、帧、离线/失败合同 | `references/visual-html-report*.md` 对应语言 | 未涉及视觉时不要加载 |

## 验证门

```bash
python -m unittest discover -s tests -v
python scripts/mimo_podcast_tool.py --self-test
python -m py_compile scripts/*.py
python scripts/mimo_podcast_tool.py --help
```

交付前逐项核对：transcript 与报告窗口一一对应；Markdown 已先落盘；HTML/assets 同名且可移动；帧来自所属窗口；页面在 375/768/1024/1440px 无横向溢出；控制台无相关错误；网络禁用时无外部资源请求。
