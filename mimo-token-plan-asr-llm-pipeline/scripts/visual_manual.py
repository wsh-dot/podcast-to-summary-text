import json
from pathlib import Path

from visual_generation import (
    build_visual_batch_prompt,
    build_visual_synthesis_prompt,
    is_compact_chinese_long_form,
    parse_visual_batch,
    visual_duration_seconds,
)
from visual_brief import validate_visual_brief
from visual_reader import VisualStageError, render_visual_brief


def _batches(blocks, batch_size):
    if not isinstance(batch_size, int) or batch_size < 1:
        raise VisualStageError("visual prompt export failed: batch size must be positive")
    return [blocks[index:index + batch_size] for index in range(0, len(blocks), batch_size)]


def export_visual_prompts(*, calibrated_transcript_blocks, validated_timeline_report,
                          trusted_metadata, output_dir, base_name, batch_size):
    batches = _batches(calibrated_transcript_blocks, batch_size)
    if not batches:
        raise VisualStageError("visual prompt export failed: calibrated transcript is empty")
    prompt_root = Path(output_dir) / f"{base_name}_visual_prompts"
    if prompt_root.exists():
        raise VisualStageError(f"visual prompt export directory already exists: {prompt_root}")
    prompt_dir = prompt_root / "batch_prompts"
    result_dir = prompt_root / "batch_results"
    prompt_dir.mkdir(parents=True)
    result_dir.mkdir()
    expected_results = []
    for index, blocks in enumerate(batches, start=1):
        result_name = f"{index:03d}.json"
        expected_results.append(result_name)
        prompt = (
            f"Save the response as batch_results/{result_name}. Return JSON only; do not "
            "include unexplained prose, HTML, CSS, JavaScript, or SVG.\n\n"
            f"{build_visual_batch_prompt(blocks)}"
        )
        (prompt_dir / f"{index:03d}.md").write_text(prompt, encoding="utf-8")
    workflow = {
        "version": 1,
        "expected_batch_results": expected_results,
        "synthesis_prompt": "synthesis_prompt.md",
        "manifest_result": "manifest.json",
    }
    (prompt_root / "workflow.json").write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return prompt_root


def _load_expected_results(prompt_root, batches):
    result_dir = prompt_root / "batch_results"
    expected_names = [f"{index:03d}.json" for index in range(1, len(batches) + 1)]
    actual_names = sorted(path.name for path in result_dir.glob("*.json")) if result_dir.is_dir() else []
    missing = sorted(set(expected_names) - set(actual_names))
    extra = sorted(set(actual_names) - set(expected_names))
    if missing or extra:
        raise VisualStageError(
            f"manual visual batches mismatch; missing={missing}, extra={extra}"
        )
    validated = []
    for name, blocks in zip(expected_names, batches):
        path = result_dir / name
        try:
            validated.append(parse_visual_batch(path.read_text(encoding="utf-8"), blocks, name))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise VisualStageError(f"manual visual batch {name} is invalid: {exc}") from exc
    return expected_names, validated


def prepare_visual_synthesis(*, calibrated_transcript_blocks, validated_timeline_report,
                             trusted_metadata, media_source, prompt_root, batch_size):
    prompt_root = Path(prompt_root)
    batches = _batches(calibrated_transcript_blocks, batch_size)
    expected_names, validated = _load_expected_results(prompt_root, batches)
    prompt = build_visual_synthesis_prompt(
        validated,
        validated_timeline_report,
        trusted_metadata,
        visual_duration_seconds(calibrated_transcript_blocks, trusted_metadata),
        calibrated_transcript_blocks,
        media_source=media_source,
    )
    instructions = (
        "Validated batch inputs: " + ", ".join(expected_names) + ".\n"
        "Save the JSON-only response as manifest.json. Do not include HTML, CSS, "
        "JavaScript, SVG, Markdown fences, or unexplained prose.\n\n"
    )
    synthesis_path = prompt_root / "synthesis_prompt.md"
    synthesis_path.write_text(instructions + prompt, encoding="utf-8")
    return synthesis_path


def render_manual_visual_brief(*, calibrated_transcript_blocks, validated_timeline_report,
                               trusted_metadata, media_source, prompt_root,
                               output_destination, frame_provider=None):
    manifest_path = Path(prompt_root) / "manifest.json"
    if not manifest_path.is_file():
        raise VisualStageError(f"manual visual manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VisualStageError(f"manual visual manifest is invalid: {exc}") from exc
    validate_visual_brief(calibrated_transcript_blocks, manifest, media_source)
    frame_assets = []
    duration_seconds = visual_duration_seconds(calibrated_transcript_blocks, trusted_metadata)
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
