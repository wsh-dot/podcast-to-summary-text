---
name: mimo-token-plan-asr-llm-pipeline
description: Use when a user needs 播客或长音视频转写、校对、总结或图文解读，输入来自本地媒体、Bilibili/B站、小宇宙、YouTube、URL 或已有 `[HH:MM-HH:MM]` transcript；也适用于 ASR、MiMo Token Plan、阿里 Fun-ASR-Flash/DashScope、Qwen、StepFun/StepAudio、腾讯 ASR、FDE、逐窗口 Markdown 时间线或完全离线 HTML 图文速览请求。
---

# 时间线转写、摘要与离线图文速览

使用 `scripts/mimo_podcast_tool.py`。核心判断是“证据先于表现”：校对 transcript 和已验证 Markdown 是事实产物；HTML 是后置解释层，失败不得反向删除事实产物。

```text
媒体 → 窗口化 ASR → 校对 transcript → 已验证 Markdown
     → 已验证 VisualBrief manifest → 离线 HTML/assets
```

## 先确定产物，不先确定 provider

用户已给出的选择直接采用，不重复询问；每轮最多追问一个真正阻断执行的选择。

| 请求 | 完成条件 |
|---|---|
| 解析、处理、转写音视频 | 默认三产物合同：`<base>_转写.txt`、`<base>_逐窗口深度解读.md`、`<base>_图文速览.html` |
| 明确“只转写/不要总结” | 仅 `<base>_转写.txt`；只有用户明确要求“只转写/不要总结”才缩减合同 |
| Markdown 时间线或总结 | 校对稿、已验证 Markdown、HTML |
| HTML 或图文速览 | 必须先发布 transcript 与已验证 Markdown，再发布 HTML |

任何一个产物缺失都不得报整项完成。视觉失败时保留 TXT/Markdown，但状态必须是“HTML 待修复”，继续处理 manifest、媒体或 renderer 问题。

## 三个决策门

1. **ASR 来源**：已有窗口 transcript，或 MiMo、阿里 Qwen、阿里 Fun-ASR-Flash、StepFun、Step Plan、腾讯。
2. **时间线路线**：无 LLM 凭据时默认 `ide-agent`；只有用户明确选择 LLM provider/凭据才用 `api-llm`；已有 batch 输出才用 manual merge。
3. **视觉路线**：默认生成；用户明确说不要 HTML 才跳过。模型只产 JSON，固定 renderer 产 HTML。

StepFun 普通 API 与 Step Plan 对应不同计费归属，必须明确选择，绝不自动互退。用户只提供 ASR key 不代表授权 LLM API；继续用当前 Agent 完成校对、时间线和视觉。

## 输入路由

| 输入 | 必须行为 |
|---|---|
| 本地音频 | 解析 ASR 凭据后窗口化转写 |
| 本地视频 | 提取音轨做 ASR，并保留视频供后置帧提取 |
| Bilibili 子域或 `b23.tv` | 音频和视觉源均只用固定 BBDown；B站不得回退 yt-dlp |
| 其他 HTTP/HTTPS URL | yt-dlp 获取音频；视觉源 best-effort，不高于 720p |
| 窗口化 `.txt` | `--transcript-input`；`*_校对.txt`/`*_calibrated.txt` 默认不重复校对 |

B站只能按 `urlparse(...).hostname` 判断；域名文本出现在路径、查询参数或 `evil-bilibili.com` 中均不算。

凭据按“显式参数 → 环境变量 → 本机 provider 缓存”解析。首个真实 ASR 分片成功后才保存。仅 401/403 或明确认证失败可删除对应 provider 缓存；429、网络错误、服务端错误不得清除。凭据不得进入回复、报告、prompt、日志示例或仓库。涉及 provider、endpoint、payload、环境变量或重试时，先按“按需加载”读取对应 reference。

## 状态机与恢复动作

| 当前状态 | 下一动作 | 失败恢复 |
|---|---|---|
| 无 transcript | 下载/提取音轨，按窗口 ASR | 429 遵循 `Retry-After`；持续传输或 risk-block 只在原窗口内细分，标签不变 |
| 有原始 transcript | 逐窗口校对 | 校对失败保留该窗原文，不跨窗搬运 |
| 有校对稿 | 每批 6 窗生成 timeline sections | 缺失或证据元数据不合格时只重跑失败窗口 |
| 有完整 sections | 本地合并、生成速览表并严格验证 | 缺失、重复、额外、乱序、错窗证据均停止发布 |
| 有已验证 Markdown | 生成/验证 visual JSON，再固定渲染 | visual 失败保留事实产物并继续修复，不伪报完成 |

ASR checkpoint 必须匹配输入标识、分片时长、媒体时长和连续窗口前缀；只跳过已验证前缀。绝不手工拼接部分转写或删除仍可恢复的有效 checkpoint。

## 时间线证据合同

每个 batch 章节末尾必须恰好包含：

```markdown
> **核心观点**：一句完整、可独立成立且不超过 50 字的结论
> **关键论据 / 金句**：论据：具体支撑 <!--依据：“同窗逐字片段”-->
```

第二行严格四选一：

- `论据：... <!--依据：“同窗逐字片段”-->`：默认；机制、案例、数据、因果链、对比或边界条件。
- `原话：“...”`：仅用于同窗逐字、完整独立、高信息密度且有辨识度的表达。
- `背景：... <!--依据：“同窗逐字片段”-->`：有有效语音，但只有导入、过渡或事实背景。
- `无可用证据（该窗口无有效转写）`：仅用于确无有效语音。

转述与隐藏依据必须共享具体内容；合并器验证逐字依据后保留 HTML 注释供发布校验，GitHub 渲染不显示它。金句必须逐字存在于对应校对窗口，不得跨窗拼接。不得使用统一占位文案，也不得把寒暄、身份介绍、主持人问题、口头填充、逗号残句、无先行词代词句、ASR 重复或机械省略号包装成论据/金句。

合并器直接使用逐窗元数据生成表格并移除正文中的元数据行；不得再用全稿 LLM 二次改写表格。格式、质量门和修复规则见 `references/timeline-report-format*.md`。

## 执行路线

### `ide-agent`（默认）

1. `--transcribe-only` 只完成内部 ASR 阶段，除非用户只要转写，否则不得在这里结束。
2. 当前 Agent 逐窗校对并保存 `<base>_校对.txt`。
3. 每 6 窗生成 `<base>_agent_sections/batch_*.md`，遵守证据合同。
4. 使用校对稿和 `--manual-sections-dir` 合并；成功后继续 visual prompts、JSON 验证与固定渲染。

### `api-llm`

仅在用户明确提供或选择 LLM provider 时使用。默认 `separate` 保存校对稿；`inline` 不生成独立校对稿；`skip` 只用于可靠的既有校对稿。限流或 provider 并发不稳时降为 `--llm-concurrency 1`，不要降低证据门槛。

### Manual visual

必须先有校对 transcript 和已验证 Markdown。依次运行 export prompts → 保存 JSON-only batch → prepare synthesis → 保存 `manifest.json` → fixed render。禁止接受模型生成的 HTML、CSS、JavaScript、SVG 或资产路径。具体命令、schema、密度与失败合同见 `references/visual-html-report*.md`。

## 不可破坏的约束

- **MiMo Token Plan**：绝不把 `tp-` key 发到标准 MiMo 域名或 `/audio/transcriptions`；必须走 Token Plan chat-completions `input_audio` 合同。
- **窗口归属**：绝不修改标签、顺序或内容归属；缺窗只修该窗，最终不完整则停止 Markdown。
- **证据**：绝不发布错窗、幻觉或不可验证的论据；弱原话降为带同窗依据的论据/背景，不强凑金句。
- **视觉安全**：模型只产受限 JSON；固定 renderer 负责转义、路径和离线资产。帧只来自所属窗口，黑暗/空/损坏帧直接跳过。
- **故障隔离**：视觉失败绝不删除 Markdown 或校对稿；警告指出保留文件与待修阶段，不打印密钥或 transcript 内容。

## 输出与交付门

默认媒体请求回复“完成”前必须验证非空：

```text
<base>_转写.txt
<base>_逐窗口深度解读.md
<base>_图文速览.html
```

Markdown 必须逐窗全覆盖且速览表同序、同窗有据。HTML 必须通过 manifest、离线和静态结构验证；assets 可随 HTML 同名目录移动。只导出 prompts、只生成 batch JSON、只得到 Markdown 或出现视觉降级警告都属于中间状态。

VisualBrief v2 必须覆盖 article-interpreter 五层：一句话总览、硬核核心洞察、开发启发、批判性思考、延伸问题；所有条目携带真实 `source_windows`。开发启发覆盖 RAG/上下文工程、模型训练与数据、Agent 构建与可靠性、Agent 开发学习路径。批判性思考标出假设和证据局限；问题指向实验、指标或实现决策。

compact `summary_cards` 标题必须提供正文之外的结论增量；绝不把正文首句、截断首句或正文同义复写当标题。长中文内容的密度、卡片数量和 renderer 约束只在视觉任务中从 visual reference 加载。

## 按需加载

命中场景后完整读取对应语言 reference；中文用无 `.en` 后缀，英文用 `.en.md`。不要预加载未命中的文件。

| 场景 | 必须读取 |
|---|---|
| MiMo endpoint、payload、401/404/413/429 | `references/api-reference*.md` |
| StepFun/StepAudio/SSE/Step Plan | `references/stepfun-asr*.md` |
| provider/model/base URL/凭据缓存 | `references/providers*.md` |
| B站、BBDown、cookie、下载 | `references/bilibili-download.md` |
| 校对质量、术语、是否跳过校对 | `references/proofreading*.md` |
| timeline、证据、窗口/batch 修复 | `references/timeline-report-format*.md` |
| HTML、manifest、帧、离线合同 | `references/visual-html-report*.md` |

## 验证门

安装后的 skill 包必须运行以下安装态验证：

```bash
python scripts/mimo_podcast_tool.py --self-test
python -m compileall -q scripts
python scripts/mimo_podcast_tool.py --help
```

修改源码仓库时还必须从仓库根目录运行完整回归：

```bash
python -m unittest discover -s tests -v
```

Windows 中文环境运行外部 skill 校验器时用 `$env:PYTHONUTF8=1`；Linux/macOS 使用 `PYTHONUTF8=1 python ...`。失败意味着仍处于中间状态：修复后重跑，不得以人工抽查代替确定性验证。
