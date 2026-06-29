# ASR Proofreading Reference

[中文版本](proofreading.md)

Read this file when changing the ASR proofreading prompt, debugging proofreading quality, or deciding whether proofreading can be skipped.

## Purpose

Raw ASR transcript commonly has these problems:

- missing or sparse punctuation
- typos, homophones, and bad word boundaries
- inconsistent English terms, company names, and product names
- misrecognized names of people, guests, and organizations
- run-on sentences with no readable paragraph structure
- messy context in multi-speaker conversations

The default quality chain is:

```text
raw windowed ASR transcript -> LLM-proofread windowed transcript -> LLM summary/report
```

Proofreading improves readability and proper-noun accuracy. It is not summarization.

## Invariants

- Keep every `[HH:MM-HH:MM]` window label unchanged.
- Each input window must produce exactly one matching output window.
- Do not move content across windows.
- Do not merge adjacent windows.
- Do not create timestamps that are not in the transcript.
- Do not delete substantive content, compress claims, or summarize early.

If an LLM proofreading result misses windows, invents extra windows, or is clearly too short, the script should retry missing windows. If retry still fails, keep the original ASR text for that window.

## Allowed Changes

- Add Chinese/English punctuation.
- Break run-on text into readable sentences and light paragraphs.
- Fix obvious typos, homophones, and bad word boundaries.
- Fix English term spelling and casing, such as `Chat GPT` -> `ChatGPT`.
- Use title, context, `--terminology`, or `--terminology-file` to correct names, company names, and product names.
- Remove tiny meaningless repetitions only when no substantive content is removed.

## Forbidden Changes

- Do not summarize, shorten, or heavily rewrite.
- Do not add guests, hosts, companies, products, data, or quotes.
- Do not force uncertain proper nouns into plausible but unsupported names.
- Do not translate the source language.
- Do not turn the calibrated transcript into report sections.

## Route Rules

### `ide-agent`

Default when no LLM API is selected.

1. The script runs ASR only and saves `{base_name}_转写.txt`.
2. The agent uses the current IDE model to proofread each window while preserving labels, optionally writing `{base_name}_校对.txt`.
3. The agent generates `batch_*.md` timeline sections from the calibrated transcript.
4. The script merges and validates with `--manual-sections-dir`.

The agent should not summarize obviously dirty ASR text directly.

### `api-llm`

The script defaults to `--proofread-mode separate`: each timeline batch is summarized immediately after proofreading, the calibrated transcript is saved, and up to two independent batches run concurrently.

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --llm-provider kimi --llm-api-key "sk-..."
```

It saves:

```text
{base_name}_校对.txt
```

When only the final report is needed, combine proofreading with each summary call and omit the separate calibrated transcript:

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --proofread-mode inline --llm-provider kimi --llm-api-key "sk-..."
```

If the provider returns 429/rate-limit errors, use `--llm-concurrency 1`; the default concurrency is 2.

Proofread only:

```bash
python scripts/mimo_podcast_tool.py --transcript-input raw_转写.txt --proofread-only --llm-provider kimi --llm-api-key "sk-..."
```

Inputs ending in `_校对.txt` or `_calibrated.txt` automatically reuse the calibrated text and skip duplicate proofreading. Use `--no-proofread` for other files only when the transcript was already manually corrected or comes from high-quality subtitles. It is an alias for `--proofread-mode skip`; pass `--proofread-mode separate` to force recalibration.

### `manual`

Exported prompts must tell the model to proofread inside each window before writing the section summary. If the user wants a separate calibrated transcript, run `--proofread-only` first or have the agent write `{base_name}_校对.txt` before exporting summary prompts.

## Terminology Input

When title/context is not enough for proper nouns:

```bash
--terminology "OpenAI, ChatGPT, GitHub, Bilibili"
--terminology "戴雨森, Harness, Stanley Druckenmiller"
--terminology-file terms.txt
```

`terms.txt` may be one term per line or simple mappings:

```text
哈尼斯 -> Harness
斯坦利 德鲁肯米勒 -> Stanley Druckenmiller
open ai -> OpenAI
```

## Validation

After proofreading, verify:

- `{base_name}_校对.txt` has the same window count as `{base_name}_转写.txt`.
- Window labels are in the exact same order.
- No single window output is abnormally short.
- The final report still has one time section per transcript window.

