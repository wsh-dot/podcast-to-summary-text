# 离线 HTML 图文速览合同

## 目录

1. 事实与产物顺序
2. 三条结构化路线
3. Manifest 与证据规则
4. 视频代表帧
5. Reader 与离线约束
6. 失败矩阵
7. Manual 文件布局
8. 视觉与无障碍 QA

## 1. 事实与产物顺序

Markdown 是权威事实产物。visual 阶段只能在校对 transcript 和 timeline report 均通过窗口校验且 Markdown 已写入后开始。

```text
calibrated transcript + validated Markdown
  -> bounded VisualBatch JSON
  -> validated batch records
  -> VisualBriefManifest JSON
  -> manifest/evidence/full-coverage validation
  -> optional real frames
  -> fixed offline renderer
  -> atomic HTML + sibling assets publication
```

visual 失败不得回滚或覆盖 transcript/Markdown。

## 2. 三条结构化路线

- **api-llm**：脚本按 `timeline-batch-size` 调用已选 LLM provider。每个无效 batch 最多单独修复一次；有效 batch 不重跑。全局 synthesis 必须按顺序读取完整校对 transcript；已验证 batch 和 Markdown overview 只作为证据约束，不能替代全文阅读。
- **ide-agent**：手工章节合并并发布 Markdown 后，CLI 自动导出 visual prompts。Agent 按 prompt 生成同一 JSON batch 与 manifest；输出必须保存为指定文件，禁止额外解释，再继续 prepare/render。
- **manual**：用户把外部模型 JSON 放入指定目录；脚本不调用 LLM，只验证并渲染。

三条路线共享 `visual_brief.py` 和 `visual_reader.py`。不得创建路线专属 schema 或 HTML 模板。

## 3. Manifest 与证据规则

顶层必需字段：

```json
{
  "version": 1,
  "overview": {"text": "...", "source_windows": ["00:00-00:30"]},
  "core_insights": [
    {"text": "...", "source_windows": ["00:00-00:30"]}
  ],
  "chapters": []
}
```

`overview`、core insight、章节 `title`/`summary`、visual `title` 和 process/concept item 都使用严格的 `SourcedText`：只含非空 `text` 与非空 `source_windows`。每章必需 `id`、`title`、`summary`、`source_windows`、`evidence`、`visuals`；视频可选 `frame_priority`（0–100）。comparison/relationship 的每个 item 也必须带 `source_windows`；metrics/quote 使用精确 `source_window`。

不可破坏的验证：

- 所有章节窗口合并后必须与 transcript 窗口完全相等：不缺失、不重复、不重叠、不乱序。
- 单章只能包含 transcript 中相邻窗口。
- evidence window 必须属于该章。
- quote 必须逐字存在于指定窗口。
- metrics 的 `source_sentence` 必须逐字存在于指定窗口。
- 只允许 `process`、`comparison`、`relationship`、`metrics`、`concept`、`quote`。
- 没有证据支持视觉时 `visuals: []`；固定 renderer 使用 editorial insight，不制造图表。
- 每条可见 claim、diagram item、edge 和 label 的来源必须落在其章节窗口内；overview/core insight 可引用全文真实窗口。
- 短内容最多 6 个核心 insight、5 个视觉；长内容最多 10 个 insight、8 个视觉。这些是上限，不是配额。
- 超过 60 分钟且校对稿中 CJK 字符不少于 ASCII 拉丁字母时，启用 compact editorial profile：精确 4 个核心 insight、5 个相邻窗口章节、1800–2500 个可见汉字，每章最多 2 个视觉、全文最多 8 个。`process` 按 item 数映射为流程/时间线，`comparison` 映射为对比图，环形 `relationship` 映射为飞轮，其他关系映射为网络图，`metrics` 映射为指标条，`concept` 映射为分层图。

模型字段严格白名单。任何 `html`、`javascript`、`css`、`svg`、绝对路径或 `..` 都应在发布前失败。

## 4. 视频代表帧

compact editorial profile 不调用 frame provider、不接受 `frame_priority`/非空 `frame_assets`、不创建 sibling assets 目录。发布新单文件 HTML 时原子移除旧帧资产；失败时同时恢复旧 HTML 与 assets。

- 不超过 1 小时：最多约 8 个高价值章节帧。
- 超过 1 小时：约 8–12 个，不把 12 当硬配额。
- 按 `frame_priority` 排序；每章最多一张。
- 选择该章真实 source window 的中点，再有限尝试 35%、65%、20% 位置。
- 时间戳不得越出窗口；不得制造 transcript 不具备的秒级事实描述。
- FFmpeg 输出 WebP，最大显示宽度 1280，稳定命名 `001_00-18_00-27.webp`。
- 用 ffprobe 验证可解码尺寸；用低分辨率灰度样本拒绝空、黑或过暗帧。
- 单帧/全部帧失败都回退 infographic/text，不取消 HTML。

Bilibili 视觉源仍只用 BBDown 1.6.3 `--video-only --video-ascending`；不得回退 yt-dlp。其他 URL 可用 yt-dlp 请求不高于 720p 的临时视频源。

## 5. Reader 与离线约束

普通 Reader 包含 overview、core insights、章节导航、证据、六类信息图和可选代表帧。compact editorial Reader 使用约 1080px 单栏编辑式布局、renderer-owned CSS/SVG 图形和来源时间窗，不包含搜索、sticky 侧栏、视频帧、序列化 manifest 或完整 transcript。

- 视觉意图是温暖、自信的现代编辑海报。必须使用语义 token：amber `--color-primary: #CC8800`、burnt orange `--color-secondary: #C55221`、surface `#FFFFFF`、text `#111827`；正文不得直接依赖临时 raw color。
- compact profile 使用奶油色画布和独立 SECTION 分组。每章标题与来源标签在上方，完整摘要按语义和句子边界确定性拆为 3–5 张双列白色内容卡片；卡片正文按原顺序拼接后必须逐字等于原摘要。信息图在卡片网格下方占满宽度，680px 以下内容卡片变为单列。普通 Reader 使用焦橙 hero、奶油网格画布、白色导航/章节卡片。两者必须共享字体、色彩、间距和焦点语言。
- display 字体栈优先 Chakra Petch，mono 优先 JetBrains Mono；不得为了字体发起网络请求，缺失时使用内嵌 CSS 中的系统 fallback。
- 可交互链接、搜索框和 disclosure 的触控高度至少 44px。链接必须具有 default、hover、focus-visible 和 active（适用时）状态；搜索框必须具有 default、hover、focus-visible 状态。
- 所有不可信文本统一 HTML escape。
- 图片路径由 renderer 生成且只指向 sibling assets。
- 图片包含 width/height、稳定 aspect ratio、`loading="lazy"`、`decoding="async"`、alt 与 caption。
- CSS、增强 JavaScript、图标和结构化页面数据内嵌。
- 禁止 CDN、外部字体、analytics、tracking、远程图片或运行时包。
- JavaScript 只增强本地搜索、当前章节、移动章节导航和打印。
- 无 JavaScript 时正文、目录锚点、视觉和图片仍工作。
- 375/768 使用单列和移动章节 disclosure；1024/1440 使用三栏 reader。
- 支持 skip link、可见焦点、顺序标题、reduced motion 和打印展开。
- 禁止低对比度的小号 amber 文本、无焦点轮廓、纯装饰渐变堆叠、圆角胶囊泛滥、不一致卡片间距，以及用 hover 作为唯一信息通道。

## 6. 失败矩阵

| 失败 | 行为 |
|---|---|
| batch JSON 非法/证据不匹配 | 只修该 batch 一次；仍失败则停止 HTML。 |
| synthesis manifest 非法 | 用原 synthesis 输入和校验错误修复一次；仍失败则停止 HTML。 |
| IDE prompt 导出失败 | 一条 visual warning；保留已发布 Markdown。 |
| synthesis manifest 非法 | 不发布 HTML/assets；保留 Markdown。 |
| Bilibili 视觉下载失败 | 一条简洁 warning；无帧 HTML；不使用 yt-dlp。 |
| 其他远程视觉下载失败 | 一条简洁 warning；无帧 HTML。 |
| 单帧空/暗/损坏 | 在同窗口有限 fallback；仍失败则跳过该帧。 |
| renderer/static validation 失败 | 清理 staging；保留上一个完整 reader 和核心产物。 |
| publication 中途失败 | 删除新部分并恢复旧 HTML/assets。 |

错误不得包含密钥、cookie 或 transcript 原文。

## 7. Manual 文件布局

```text
<base>_visual_prompts/
  workflow.json
  batch_prompts/
    001.md
  batch_results/
    001.json
  synthesis_prompt.md
  manifest.json
```

`prepare` 阶段要求 batch 文件名集合与期望完全一致；缺失、额外、重复或 malformed 文件都不得进入 synthesis。`render` 阶段只读取 `manifest.json`，通过共享验证后发布同一 HTML 合同。

## 8. 视觉与无障碍 QA

- [ ] 375、390、768、1024、1440px 均无横向滚动，长标题可换行且不遮挡装饰文字。
- [ ] compact 每章摘要拆为 3–5 张双列内容卡片，680px 以下单列；全部卡片正文按序拼接后逐字等于原摘要，信息图在卡片下方全宽呈现。
- [ ] 六类图表、无图表文字回退、视频帧、导航、搜索和来源链接使用同一语义 token。
- [ ] Tab 可到达 skip link、所有链接、搜索与 disclosure；焦点轮廓至少 3px 且不被裁切。
- [ ] 触控目标至少 44px；`prefers-reduced-motion` 会移除滚动与 hover transition。
- [ ] 打印时移除背景纹理、sticky 导航和脚本，章节不被不必要地拆页。
- [ ] HTML 保持单文件/同级资产合同，不包含外部字体、CDN、远程图片或 tracking。
