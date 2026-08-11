import json
import re

from visual_brief import ManifestValidationError, validate_visual_brief
from visual_reader import VisualStageError, render_visual_brief


BATCH_KEYS = {"version", "windows", "records"}
RECORD_KEYS = {
    "window",
    "claim",
    "evidence",
    "candidate_visual",
    "quote",
    "numbers",
    "grouping_signal",
}
QUOTE_KEYS = {"text", "source_window"}
NUMBER_KEYS = {"label", "value", "source_sentence", "source_window"}
WINDOW_HEADING_RE = re.compile(r"^##\s+\d{2}:\d{2}-\d{2}:\d{2}\b", re.MULTILINE)


def _strict_keys(value, expected, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        raise ValueError(
            f"{label} fields mismatch; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _json_object(raw, label):
    if not isinstance(raw, str):
        raise ValueError(f"{label} response must be text")
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{label} response must contain one JSON object")
    return value


def _batch_prompt(blocks, repair_error=None):
    windows = [block["window"] for block in blocks]
    payload = [{"window": block["window"], "text": block["text"]} for block in blocks]
    repair = ""
    if repair_error:
        repair = f"\nRepair the previous invalid batch. Validation error: {repair_error}\n"
    return f"""VISUAL_BATCH_REQUEST
Analyze exactly these source windows, in this order: {json.dumps(windows, ensure_ascii=False)}.
Return JSON only with exactly this schema:
{{"version":1,"windows":[...],"records":[{{"window":"...","claim":"...","evidence":"exact source sentence","candidate_visual":null or {{"type":"process|comparison|relationship|metrics|concept|quote","reason":"..."}},"quote":null or {{"text":"exact quote","source_window":"..."}},"numbers":[{{"label":"...","value":"...","source_sentence":"exact source sentence","source_window":"..."}}],"grouping_signal":"continue|break"}}]}}
There must be exactly one record per named window. Evidence, quotes, and numeric source sentences must match the supplied calibrated transcript exactly. Use candidate_visual null when evidence does not support a diagram. Do not return HTML, JavaScript, CSS, SVG, Markdown, or prose outside JSON.{repair}
CALIBRATED_WINDOWS_JSON:
{json.dumps(payload, ensure_ascii=False)}"""


def _validate_batch(value, blocks):
    _strict_keys(value, BATCH_KEYS, "visual batch")
    if value["version"] != 1:
        raise ValueError("visual batch version must be 1")
    expected_windows = [block["window"] for block in blocks]
    if value["windows"] != expected_windows:
        raise ValueError("visual batch windows must exactly match the requested windows")
    records = value["records"]
    if not isinstance(records, list) or len(records) != len(blocks):
        raise ValueError("visual batch must contain one record per requested window")
    block_by_window = {block["window"]: block for block in blocks}
    for index, record in enumerate(records):
        label = f"visual batch record {index + 1}"
        _strict_keys(record, RECORD_KEYS, label)
        window = record["window"]
        if window != expected_windows[index]:
            raise ValueError("visual batch records must preserve requested window order")
        source_text = block_by_window[window]["text"]
        _text(record["claim"], f"{label} claim")
        evidence = _text(record["evidence"], f"{label} evidence")
        if evidence not in source_text:
            raise ValueError(f"{label} evidence is not an exact source match")
        candidate = record["candidate_visual"]
        if candidate is not None:
            _strict_keys(candidate, {"type", "reason"}, f"{label} candidate visual")
            if candidate["type"] not in {
                "process", "comparison", "relationship", "metrics", "concept", "quote"
            }:
                raise ValueError(f"{label} candidate visual type is unsupported")
            _text(candidate["reason"], f"{label} candidate visual reason")
        quote = record["quote"]
        if quote is not None:
            _strict_keys(quote, QUOTE_KEYS, f"{label} quote")
            if quote["source_window"] != window or _text(quote["text"], f"{label} quote") not in source_text:
                raise ValueError(f"{label} quote is not an exact source match")
        numbers = record["numbers"]
        if not isinstance(numbers, list):
            raise ValueError(f"{label} numbers must be a list")
        for number_index, number in enumerate(numbers):
            number_label = f"{label} number {number_index + 1}"
            _strict_keys(number, NUMBER_KEYS, number_label)
            for key in NUMBER_KEYS:
                _text(number[key], f"{number_label} {key}")
            if number["source_window"] != window or number["source_sentence"] not in source_text:
                raise ValueError(f"{number_label} source sentence is not an exact source match")
        if record["grouping_signal"] not in {"continue", "break"}:
            raise ValueError(f"{label} grouping signal is invalid")
    return value


def _markdown_overview(report):
    match = WINDOW_HEADING_RE.search(report)
    overview = report[:match.start()] if match else report
    return overview.strip()


def _duration_seconds(blocks, metadata):
    value = metadata.get("duration_seconds")
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    end = blocks[-1]["window"].split("-", 1)[1]
    minute, second = map(int, end.split(":"))
    return minute * 60 + second


def is_compact_chinese_long_form(blocks, duration_seconds):
    text = "".join(block.get("text", "") for block in blocks)
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    return duration_seconds > 3600 and cjk_count > 0 and cjk_count >= latin_count


def _visible_manifest_strings(manifest):
    def sourced_text(value):
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            yield value["text"]

    yield from sourced_text(manifest.get("overview"))
    yield from sourced_text(manifest.get("one_line_overview"))
    for insight in manifest.get("core_insights", []):
        yield from sourced_text(insight)
    for field in ("developer_takeaways", "critical_thinking", "further_questions"):
        for item in manifest.get(field, []):
            if isinstance(item, dict):
                if isinstance(item.get("title"), str):
                    yield item["title"]
                if isinstance(item.get("text"), str):
                    yield item["text"]
    for chapter in manifest.get("chapters", []):
        yield from sourced_text(chapter.get("title"))
        yield from sourced_text(chapter.get("summary"))
        for card in chapter.get("summary_cards", []):
            if isinstance(card, dict):
                yield from sourced_text(card.get("title"))
        for evidence in chapter.get("evidence", []):
            if isinstance(evidence, dict) and isinstance(evidence.get("label"), str):
                yield evidence["label"]
        for visual in chapter.get("visuals", []):
            yield from sourced_text(visual.get("title"))
            visual_type = visual.get("type")
            for item in visual.get("items", []):
                if visual_type in {"process", "concept"}:
                    yield from sourced_text(item)
                elif isinstance(item, dict):
                    keys = {
                        "comparison": ("label", "value"),
                        "relationship": ("from", "to", "label"),
                        "metrics": ("label", "value"),
                    }.get(visual_type, ())
                    for key in keys:
                        if isinstance(item.get(key), str):
                            yield item[key]
            if visual_type == "quote" and isinstance(visual.get("quote"), str):
                yield visual["quote"]


def visible_manifest_cjk_count(manifest):
    return len(re.findall(r"[\u4e00-\u9fff]", "".join(_visible_manifest_strings(manifest))))


def _synthesis_prompt(validated_batches, report, metadata, duration_seconds,
                      calibrated_transcript_blocks, media_source=None):
    compact = is_compact_chinese_long_form(
        calibrated_transcript_blocks,
        duration_seconds,
    )
    if compact:
        density = (
            "Target a 7-10 minute editorial read with 2600-3800 visible CJK characters, "
            "exactly 4 core insights, exactly 5 chapters, and a target of 6-8 visuals "
            "with at most 2 per chapter. Do not emit quote visuals or frame_priority. "
            "Each chapter must include 3-5 summary_cards. Each card has a sourced title and "
            "a sourced text body; titles must be 4-24 characters, state the takeaway or "
            "contrast, and must not repeat or truncate the body's opening. Card bodies in "
            "order must concatenate exactly to the chapter summary text. Produce four "
            "developer_takeaways covering RAG/context engineering, model training/data, "
            "Agent construction/reliability, and an ordered Agent-development learning path. "
            "Each takeaway must explain what it is, why it matters, and how to apply it. Also "
            "produce 2-4 evidence-based critical_thinking items and 2-4 actionable "
            "further_questions."
        )
    elif duration_seconds <= 3600:
        density = "Target a 5-10 minute read, at most 6 core insights and 5 visuals."
    else:
        density = "Target a 15-20 minute read, at most 10 core insights and 8 visuals."
    source_kind = (media_source or {}).get("kind", "unknown")
    transcript_payload = [
        {"window": block["window"], "text": block["text"]}
        for block in calibrated_transcript_blocks
    ]
    return f"""VISUAL_SYNTHESIS_REQUEST
Create one version 2 VisualBriefManifest JSON object for the fixed offline renderer. {density}
Read the complete calibrated transcript before global interpretation. Use the validated batches as evidence constraints, not as a substitute for reading the full transcript.
Group only adjacent windows and cover every source window exactly once, in order. Use only process, comparison, relationship, metrics, concept, and verified quote visuals. When evidence supports none, return an empty visuals list for that chapter so the renderer uses an editorial insight presentation. Do not return HTML, JavaScript, CSS, SVG, Markdown, or prose outside JSON.
The required manifest keys are version, one_line_overview, overview, core_insights, developer_takeaways, critical_thinking, further_questions, and chapters. `one_line_overview` is a sourced conclusion of at most 50 characters, not "this content introduces...". Interpretive list items contain exactly title, text, and source_windows. Critical items must identify a specific assumption or evidence limit without inventing a rebuttal; further questions must point to a concrete experiment, metric, or implementation decision. Each chapter requires id, title, summary, source_windows, evidence, and visuals; compact chapters also require summary_cards. Source kind: {source_kind}.
Every overview, core-insight, chapter title, chapter summary, visual title, process item, and concept item must be an object with exactly `text` and non-empty `source_windows`. Every comparison and relationship item must include non-empty `source_windows`. Metrics and quotes retain their exact `source_window`. All references must belong to the containing chapter (or the full transcript for overview/core insights), and every visible claim or label must carry evidence references.
TRUSTED_METADATA_JSON:
{json.dumps(metadata, ensure_ascii=False)}
VALIDATED_MARKDOWN_OVERVIEW:
{_markdown_overview(report)}
CALIBRATED_TRANSCRIPT_JSON:
{json.dumps(transcript_payload, ensure_ascii=False)}
VALIDATED_VISUAL_BATCHES_JSON:
{json.dumps(validated_batches, ensure_ascii=False)}"""


def _validate_density(manifest, duration_seconds, calibrated_transcript_blocks=None):
    if not isinstance(manifest, dict):
        raise ValueError("visual synthesis must return an object")
    insights = manifest.get("core_insights")
    chapters = manifest.get("chapters")
    if not isinstance(insights, list) or not isinstance(chapters, list):
        return
    visual_counts = [
        len(chapter.get("visuals", []))
        for chapter in chapters
        if isinstance(chapter, dict) and isinstance(chapter.get("visuals", []), list)
    ]
    visual_count = sum(visual_counts)
    compact = is_compact_chinese_long_form(
        calibrated_transcript_blocks or [],
        duration_seconds,
    )
    if compact:
        cjk_count = visible_manifest_cjk_count(manifest)
        cjk_minimum, cjk_maximum = (
            (2600, 3800) if manifest.get("version") == 2 else (1800, 2500)
        )
        has_quote = any(
            visual.get("type") == "quote"
            for chapter in chapters
            for visual in chapter.get("visuals", [])
            if isinstance(visual, dict)
        )
        has_frame_priority = any("frame_priority" in chapter for chapter in chapters)
        evidence_too_long = any(
            len(re.findall(r"[\u4e00-\u9fff]", evidence.get("label", ""))) > 40
            for chapter in chapters
            for evidence in chapter.get("evidence", [])
            if isinstance(evidence, dict)
        )
        if (
            len(insights) != 4
            or len(chapters) != 5
            or not cjk_minimum <= cjk_count <= cjk_maximum
            or visual_count > 8
            or any(count > 2 for count in visual_counts)
            or has_quote
            or has_frame_priority
            or evidence_too_long
        ):
            raise ValueError(
                f"compact density requires 4 insights, 5 chapters, {cjk_minimum}-{cjk_maximum} visible "
                f"CJK characters, at most 8 visuals and 2 per chapter; got "
                f"insights={len(insights)}, chapters={len(chapters)}, cjk={cjk_count}, "
                f"visuals={visual_count}"
            )
        return
    insight_limit, visual_limit = (6, 5) if duration_seconds <= 3600 else (10, 8)
    if len(insights) > insight_limit or visual_count > visual_limit:
        raise ValueError(
            f"visual synthesis exceeds density limits: insights {len(insights)}/{insight_limit}, "
            f"visuals {visual_count}/{visual_limit}"
        )


def build_visual_batch_prompt(blocks, repair_error=None):
    return _batch_prompt(blocks, repair_error=repair_error)


def parse_visual_batch(raw, blocks, label="visual batch"):
    return _validate_batch(_json_object(raw, label), blocks)


def build_visual_synthesis_prompt(validated_batches, report, metadata, duration_seconds,
                                  calibrated_transcript_blocks, media_source=None):
    return _synthesis_prompt(
        validated_batches,
        report,
        metadata,
        duration_seconds,
        calibrated_transcript_blocks,
        media_source=media_source,
    )


def visual_duration_seconds(blocks, metadata):
    return _duration_seconds(blocks, metadata)


def generate_api_visual_brief(*, calibrated_transcript_blocks, validated_timeline_report,
                              trusted_metadata, media_source, output_destination, complete,
                              parallel_map, batch_size, concurrency, frame_provider=None):
    if not calibrated_transcript_blocks:
        raise VisualStageError("visual generation failed: calibrated transcript is empty")
    if not isinstance(batch_size, int) or batch_size < 1:
        raise VisualStageError("visual generation failed: batch size must be positive")
    if not isinstance(concurrency, int) or concurrency < 1:
        raise VisualStageError("visual generation failed: concurrency must be positive")
    batches = [
        calibrated_transcript_blocks[index:index + batch_size]
        for index in range(0, len(calibrated_transcript_blocks), batch_size)
    ]

    def generate_batch(item):
        index, blocks = item
        label = f"visual batch {index + 1}/{len(batches)}"
        raw = complete(
            [{"role": "system", "content": "Return evidence-grounded JSON only."},
             {"role": "user", "content": build_visual_batch_prompt(blocks)}],
            4000,
            label,
        )
        try:
            return parse_visual_batch(raw, blocks, label)
        except (json.JSONDecodeError, ValueError) as exc:
            repair_label = f"{label} repair"
            repaired_raw = complete(
                [{"role": "system", "content": "Repair the JSON to satisfy the evidence schema."},
                 {"role": "user", "content": build_visual_batch_prompt(blocks, repair_error=str(exc))}],
                4000,
                repair_label,
            )
            try:
                return parse_visual_batch(repaired_raw, blocks, repair_label)
            except (json.JSONDecodeError, ValueError) as repair_exc:
                raise VisualStageError(
                    f"visual batch validation failed after bounded repair: {repair_exc}"
                ) from repair_exc

    try:
        validated_batches = parallel_map(
            generate_batch,
            list(enumerate(batches)),
            max_workers=concurrency,
        )
        duration_seconds = visual_duration_seconds(calibrated_transcript_blocks, trusted_metadata)
        synthesis_prompt = build_visual_synthesis_prompt(
            validated_batches,
            validated_timeline_report,
            trusted_metadata,
            duration_seconds,
            calibrated_transcript_blocks,
            media_source=media_source,
        )
        raw_manifest = complete(
            [{"role": "system", "content": "Return one schema-constrained JSON object only."},
             {"role": "user", "content": synthesis_prompt}],
            8000,
            "visual synthesis",
        )

        def parse_manifest(raw, label):
            value = _json_object(raw, label)
            _validate_density(value, duration_seconds, calibrated_transcript_blocks)
            validate_visual_brief(calibrated_transcript_blocks, value, media_source)
            return value

        try:
            manifest = parse_manifest(raw_manifest, "visual synthesis")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            repair_prompt = (
                f"{synthesis_prompt}\n\nValidation error: {exc}\n"
                "Repair the manifest and return the complete JSON object only."
            )
            repaired_raw = complete(
                [{"role": "system", "content": "Repair the manifest to satisfy the evidence schema."},
                 {"role": "user", "content": repair_prompt}],
                8000,
                "visual synthesis repair",
            )
            try:
                manifest = parse_manifest(repaired_raw, "visual synthesis repair")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as repair_exc:
                raise VisualStageError(
                    f"visual synthesis validation failed after bounded repair: {repair_exc}"
                ) from repair_exc
        frame_assets = []
        if frame_provider is not None and not is_compact_chinese_long_form(
            calibrated_transcript_blocks,
            duration_seconds,
        ):
            try:
                frame_assets = frame_provider(
                    calibrated_transcript_blocks,
                    manifest,
                    duration_seconds,
                )
            except Exception:
                frame_assets = []
        return render_visual_brief(
            calibrated_transcript_blocks=calibrated_transcript_blocks,
            validated_timeline_report=validated_timeline_report,
            trusted_metadata=trusted_metadata,
            media_source=media_source,
            manifest=manifest,
            output_destination=output_destination,
            frame_assets=frame_assets,
        )
    except VisualStageError:
        raise
    except (
        ManifestValidationError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        RuntimeError,
    ) as exc:
        raise VisualStageError(f"visual generation failed: {exc}") from exc
