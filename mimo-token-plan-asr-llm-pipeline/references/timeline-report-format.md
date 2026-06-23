# Timeline Report Format

Use this reference when changing the timeline report prompt or reviewing whether output matches the desired podcast-summary style.

## Purpose

Generate a Markdown report that can be read as a detailed podcast note:

- timecode sections that explain what was discussed at each point
- concise but substantive paragraphs under each timecode
- direct quotes only when supported by transcript text
- a final overview table for scanning

The ASR transcript is chunk-window based, not sentence-timestamp based. Treat every timestamp as an approximate window anchor.

The script should not ask one LLM call to produce the full body for long podcasts. Generate timeline sections in batches, then validate and merge them.

## Required Structure

```markdown
# [Program title or file-derived title]

> **嘉宾**：[only if provided or clearly present]
> **主播**：[only if provided or clearly present]
> **系列**：[only if provided]
> **时长**：约 X 小时 Y 分钟

> **转写说明**：本文基于 MiMo ASR 分片转写稿整理。时间点来自 ASR 分片窗口，非逐句时间戳；已尽量保留原意并对明显转写错误做轻度校正。

---

## 00:00-00:03 开场：[topic]

[2-4 short paragraphs explaining the opening.]

> "[short direct quote, only if present in transcript]"

## 00:03-00:06 [topic]

[2-5 paragraphs. Explain the argument, examples, conclusions, and transitions.]

## 00:06-00:09 [topic]

[One section must correspond to exactly one transcript window.]

## 核心观点速览

| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |
|------|------|----------|------------------|
| 00:03 | [section title] | [one concise claim] | [supporting detail or quote] |
```

## Timecode Rules

- Use the `[HH:MM-HH:MM]` windows in the transcript as the only timestamp source.
- Every transcript window must produce exactly one `## HH:MM-HH:MM Topic` section.
- The report body section count must equal the transcript window count.
- Do not merge adjacent windows, even when a topic spans multiple windows.
- Do not skip quiet, short, refused, or noisy windows; create the section and mark the limitation.
- Use `## 00:00-00:03 开场：Topic` for the opening window. Do not use an untimed `## 开场` heading.
- Do not create minute or second precision that is not present in the transcript.
- If one ASR window is missing, refused, or too short to summarize, mention it explicitly:
  `> ⚠️ 本窗口（00:24-00:27）转写内容缺失或不可用，以下只依据相邻片段整理。`

## Batch Generation Rules

- Default batch size should be 6 windows unless the user overrides `--timeline-batch-size`.
- Each batch prompt must list the exact required windows and demand N windows -> N sections.
- Batch outputs must contain only `## HH:MM-HH:MM Topic` sections, not the report H1, metadata block, transcription note, or final table.
- Parse returned sections by heading. Keep only windows that exist in the transcript and ignore any hallucinated extra window.
- If validation finds missing windows, rerun only those missing windows as repair prompts.
- Fail before writing the report if any transcript window is still missing, duplicated, or replaced by a non-transcript time window.
- Generate `## 核心观点速览` after the body is complete, one row per time section.

## Summary Mode Rules

All summary modes must produce the same final structure and pass the same transcript-window validation.

- `ide-agent` is the default when no LLM API is selected. The agent reads the windowed transcript, generates one `batch_*.md` file per 6 windows under `<base_name>_agent_sections/`, then runs `--manual-sections-dir` to merge and validate.
- `api-llm` is used only when the user explicitly selects a LLM API provider or provides `--llm-provider` / `--llm-api-key`. The script generates sections, repairs missing windows, and merges internally.
- `manual` is a fallback only when the user asks to export prompts or paste model outputs manually. Use `--export-ide-prompts`, then `--manual-sections-dir`.
- Each batch output must contain only timed `## HH:MM-HH:MM Topic` sections.
- Do not merge windows, skip windows, or create timestamps outside the transcript in any mode.

## Content Rules

- Produce one timecode section per transcript window. For 47 windows, produce 47 sections.
- Each section should be self-contained: what was said, why it matters, what example or argument supports it.
- Keep direct quotes short and faithful. If wording is uncertain, paraphrase instead of quoting.
- Correct obvious ASR spelling/name errors only when context makes the correction highly likely.
- Do not invent guests, hosts, products, claims, quotes, or missing segment content.
- If metadata is absent, omit that metadata line rather than writing "unknown".

## Brief Style

The `brief` report style is the legacy compact summary. It may include a short content timeline, but it is not required to produce full timecode sections or the final scan table.
