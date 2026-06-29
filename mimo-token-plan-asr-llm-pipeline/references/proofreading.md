# ASR 校对参考

[English version](proofreading.en.md)

当你修改 ASR 校对 prompt、排查校对质量，或决定是否跳过校对时，阅读本文档。

## 目标

ASR 原始文本常见问题：

- 没有标点或标点密度极低
- 错别字、同音词、错分词多
- 英文术语、产品名、公司名大小写和拼写混乱
- 人名、嘉宾名、机构名被识别错
- 长句不断句，段落结构不可读
- 多人对话的称呼和上下文混乱

默认质量链路必须是：

```text
ASR 原始窗口转写 -> LLM 校对窗口文本 -> LLM 总结/报告
```

校对阶段的职责是提升 transcript 可读性和专有名词准确度，不是摘要。

## 不变量

- 保持所有 `[HH:MM-HH:MM]` 窗口标签不变。
- 每个输入窗口必须输出且只输出一个对应窗口。
- 不得跨窗口移动内容。
- 不得合并相邻窗口。
- 不得新增 transcript 中不存在的时间窗口。
- 不得删除实质内容、压缩观点或提前总结。

如果 LLM 校对结果缺窗口、额外造窗口或明显过短，脚本应重试缺失窗口；仍失败时保留该窗口原始 ASR 文本。

## 允许修改

- 补充中文/英文标点。
- 按语义断句和轻度分段。
- 修正明显错别字、同音词和错分词。
- 修正英文术语大小写和常见拼写，例如 `Chat GPT` -> `ChatGPT`。
- 根据标题、上下文和 `--terminology` / `--terminology-file` 修正人名、公司名、产品名。
- 删除极少量无意义重复词，但不能删除观点、数字、限定条件或事实。

## 禁止修改

- 不要总结、缩写或大段改写。
- 不要新增嘉宾、主播、公司、产品、数据或引用。
- 不要把不确定的专有名词强行改成看起来更合理的词。
- 不要翻译原文语言。
- 不要把校对后的 transcript 变成报告章节。

## 路线规则

### `ide-agent`

这是无 LLM API 时的默认路线。

1. 脚本只做 ASR，保存 `{base_name}_转写.txt`。
2. Agent 使用当前 IDE 模型逐窗口校对，保持窗口标签，必要时保存 `{base_name}_校对.txt`。
3. Agent 基于校对稿生成 `batch_*.md` 时间章节。
4. 脚本用 `--manual-sections-dir` 合并和校验最终报告。

Agent 不要直接基于明显脏的 ASR 原文总结。

### `api-llm`

脚本默认使用 `--proofread-mode separate`：每个 timeline 批次完成校对后立即进入摘要，并保存校对稿；独立批次默认最多 2 路并发。

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --llm-provider kimi --llm-api-key "sk-..."
```

它会保存：

```text
{base_name}_校对.txt
```

如果只需要最终报告，可以把校对合并到摘要调用中，不生成独立校对稿：

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --proofread-mode inline --llm-provider kimi --llm-api-key "sk-..."
```

若 provider 出现 429 或限流，使用 `--llm-concurrency 1`；默认并发数是 2。

只生成校对稿：

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --proofread-only --llm-provider kimi --llm-api-key "sk-..."
```

输入文件名以 `_校对.txt` 或 `_calibrated.txt` 结尾时，脚本会自动复用并跳过重复校对。只有 transcript 已经人工校正或来自可靠字幕时，才对其它文件使用：

```bash
--no-proofread
```

`--no-proofread` 等价于 `--proofread-mode skip`。显式传入 `--proofread-mode separate` 可以强制重新校对已有校对稿。

### `manual`

导出的 prompt 必须要求模型先在每个窗口内部校对，再输出章节摘要。若用户需要单独的校对稿，应先走 `--proofread-only`，或让 Agent 生成 `{base_name}_校对.txt` 后再导出 summary prompts。

## 术语输入

当标题或上下文不足以修正专有名词时，提供术语参考：

```bash
--terminology "OpenAI, ChatGPT, GitHub, Bilibili"
--terminology "戴雨森, Harness, Stanley Druckenmiller"
--terminology-file terms.txt
```

`terms.txt` 可以是一行一个词，也可以是简单对照：

```text
哈尼斯 -> Harness
斯坦利 德鲁肯米勒 -> Stanley Druckenmiller
open ai -> OpenAI
```

## 校验

校对后必须检查：

- `{base_name}_校对.txt` 窗口数等于 `{base_name}_转写.txt`。
- 窗口标签顺序完全一致。
- 单个窗口校对结果没有异常缩短。
- 后续报告章节数仍等于 transcript 窗口数。

