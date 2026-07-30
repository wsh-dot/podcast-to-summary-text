import re
from dataclasses import dataclass
from urllib.parse import urlparse


ALLOWED_VISUAL_TYPES = {
    "process",
    "comparison",
    "relationship",
    "metrics",
    "concept",
    "quote",
}
WINDOW_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")
MANIFEST_KEYS = {"version", "overview", "core_insights", "chapters"}
CHAPTER_KEYS = {
    "id", "title", "summary", "source_windows", "evidence", "visuals", "frame_priority"
}
CHAPTER_REQUIRED_KEYS = {"id", "title", "summary", "source_windows", "evidence", "visuals"}
EVIDENCE_KEYS = {"window", "label"}
SOURCED_TEXT_KEYS = {"text", "source_windows"}
VISUAL_KEYS = {
    "process": {"type", "title", "items"},
    "comparison": {"type", "title", "items"},
    "relationship": {"type", "title", "items"},
    "metrics": {"type", "title", "items"},
    "concept": {"type", "title", "items"},
    "quote": {"type", "title", "quote", "source_window"},
}
ITEM_KEYS = {
    "comparison": {"label", "value", "source_windows"},
    "relationship": {"from", "to", "label", "source_windows"},
    "metrics": {"label", "value", "source_window", "source_sentence"},
}


class ManifestValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TranscriptBlock:
    window: str
    text: str


def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise ManifestValidationError(f"{label} must be an object")
    return value


def _require_exact_keys(value, allowed, required, label):
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise ManifestValidationError(f"{label} has unsupported fields: {', '.join(sorted(unknown))}")
    if missing:
        raise ManifestValidationError(f"{label} is missing fields: {', '.join(sorted(missing))}")


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{label} must be non-empty text")
    return value


def _require_list(value, label, allow_empty=False):
    if not isinstance(value, list) or (not value and not allow_empty):
        requirement = "a list" if allow_empty else "a non-empty list"
        raise ManifestValidationError(f"{label} must be {requirement}")
    return value


def _validate_source_windows(value, allowed_windows, label):
    windows = _require_list(value, label)
    for index, window in enumerate(windows):
        _require_text(window, f"{label} {index + 1}")
    if len(set(windows)) != len(windows):
        raise ManifestValidationError(f"{label} has duplicated windows")
    if any(window not in allowed_windows for window in windows):
        raise ManifestValidationError(f"{label} contains an out-of-scope window")
    indices = [allowed_windows.index(window) for window in windows]
    if indices != sorted(indices):
        raise ManifestValidationError(f"{label} must follow transcript order")
    return windows


def _validate_sourced_text(value, allowed_windows, label):
    value = _require_mapping(value, label)
    _require_exact_keys(value, SOURCED_TEXT_KEYS, SOURCED_TEXT_KEYS, label)
    _require_text(value["text"], f"{label} text")
    _validate_source_windows(value["source_windows"], allowed_windows, f"{label} source windows")
    return value


def _window_start(window):
    match = WINDOW_RE.fullmatch(window)
    if not match:
        raise ManifestValidationError(f"invalid source window: {window}")
    start_minute, start_second, end_minute, end_second = map(int, match.groups())
    if start_second > 59 or end_second > 59:
        raise ManifestValidationError(f"invalid source window: {window}")
    start = start_minute * 60 + start_second
    end = end_minute * 60 + end_second
    if start >= end:
        raise ManifestValidationError(f"invalid source window: {window}")
    return start


def _validate_blocks(transcript_blocks):
    _require_list(transcript_blocks, "calibrated transcript")
    blocks = []
    for index, item in enumerate(transcript_blocks):
        item = _require_mapping(item, f"transcript block {index + 1}")
        _require_exact_keys(item, {"window", "text"}, {"window", "text"}, f"transcript block {index + 1}")
        window = _require_text(item["window"], f"transcript block {index + 1} window")
        text = _require_text(item["text"], f"transcript block {index + 1} text")
        blocks.append(TranscriptBlock(window, text))
    starts = [_window_start(block.window) for block in blocks]
    if len(set(block.window for block in blocks)) != len(blocks):
        raise ManifestValidationError("calibrated transcript has duplicated windows")
    if starts != sorted(starts):
        raise ManifestValidationError("calibrated transcript windows are reordered")
    return blocks


def validate_media_source(media_source):
    media_source = _require_mapping(media_source, "media source")
    _require_exact_keys(media_source, {"kind", "url"}, {"kind", "url"}, "media source")
    _require_text(media_source["kind"], "media source kind")
    url = media_source["url"]
    if url is not None:
        _require_text(url, "media source URL")
        if url != url.strip() or any(ord(character) < 32 for character in url):
            raise ManifestValidationError("media source URL contains unsafe whitespace")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ManifestValidationError("media source URL must use http or https")


def _validate_visual(visual, chapter_windows, block_by_window, label):
    visual = _require_mapping(visual, label)
    visual_type = visual.get("type")
    if visual_type not in ALLOWED_VISUAL_TYPES:
        raise ManifestValidationError(f"unsupported visual type: {visual_type}")
    _require_exact_keys(visual, VISUAL_KEYS[visual_type], VISUAL_KEYS[visual_type], label)
    _validate_sourced_text(visual["title"], chapter_windows, f"{label} title")

    if visual_type == "quote":
        quote = _require_text(visual["quote"], f"{label} quote")
        source_window = _require_text(visual["source_window"], f"{label} source window")
        if source_window not in chapter_windows or source_window not in block_by_window:
            raise ManifestValidationError(f"{label} quote has an invalid source window")
        if quote not in block_by_window[source_window].text:
            raise ManifestValidationError(f"{label} quote is not an exact transcript match")
        return

    items = _require_list(visual["items"], f"{label} items")
    if visual_type in {"process", "concept"}:
        for index, item in enumerate(items):
            _validate_sourced_text(item, chapter_windows, f"{label} item {index + 1}")
        return

    for index, item in enumerate(items):
        item_label = f"{label} item {index + 1}"
        item = _require_mapping(item, item_label)
        _require_exact_keys(item, ITEM_KEYS[visual_type], ITEM_KEYS[visual_type], item_label)
        for key, value in item.items():
            if key == "source_windows":
                continue
            _require_text(value, f"{item_label} {key}")
        if visual_type in {"comparison", "relationship"}:
            _validate_source_windows(
                item["source_windows"],
                chapter_windows,
                f"{item_label} source windows",
            )
        if visual_type == "metrics":
            source_window = item["source_window"]
            source_sentence = item["source_sentence"]
            if source_window not in chapter_windows or source_window not in block_by_window:
                raise ManifestValidationError(f"{item_label} has an invalid source window")
            if source_sentence not in block_by_window[source_window].text:
                raise ManifestValidationError(f"{item_label} source sentence is not an exact transcript match")


def validate_visual_brief(transcript_blocks, manifest, media_source):
    blocks = _validate_blocks(transcript_blocks)
    validate_media_source(media_source)
    manifest = _require_mapping(manifest, "manifest")
    _require_exact_keys(manifest, MANIFEST_KEYS, MANIFEST_KEYS, "manifest")
    if manifest["version"] != 1:
        raise ManifestValidationError("manifest version must be 1")
    expected_windows = [block.window for block in blocks]
    _validate_sourced_text(manifest["overview"], expected_windows, "manifest overview")
    for index, insight in enumerate(_require_list(manifest["core_insights"], "core insights")):
        _validate_sourced_text(insight, expected_windows, f"core insight {index + 1}")

    block_by_window = {block.window: block for block in blocks}
    mapped_windows = []
    chapter_ids = set()
    chapters = _require_list(manifest["chapters"], "manifest chapters")
    for chapter_index, chapter in enumerate(chapters):
        label = f"chapter {chapter_index + 1}"
        chapter = _require_mapping(chapter, label)
        _require_exact_keys(chapter, CHAPTER_KEYS, CHAPTER_REQUIRED_KEYS, label)
        chapter_id = _require_text(chapter["id"], f"{label} id")
        if not re.fullmatch(r"[a-z][a-z0-9-]*", chapter_id) or chapter_id in chapter_ids:
            raise ManifestValidationError(f"{label} id must be a unique lowercase slug")
        chapter_ids.add(chapter_id)
        frame_priority = chapter.get("frame_priority", 0)
        if not isinstance(frame_priority, int) or not 0 <= frame_priority <= 100:
            raise ManifestValidationError(f"{label} frame priority must be an integer from 0 to 100")
        chapter_windows = _require_list(chapter["source_windows"], f"{label} source windows")
        for window in chapter_windows:
            _require_text(window, f"{label} source window")
        indices = [expected_windows.index(window) if window in block_by_window else -1 for window in chapter_windows]
        if -1 in indices:
            raise ManifestValidationError(f"{label} has an out-of-range source window")
        if indices != list(range(indices[0], indices[0] + len(indices))):
            raise ManifestValidationError(f"{label} source windows must be adjacent and ordered")
        mapped_windows.extend(chapter_windows)
        _validate_sourced_text(chapter["title"], chapter_windows, f"{label} title")
        _validate_sourced_text(chapter["summary"], chapter_windows, f"{label} summary")

        for evidence_index, evidence in enumerate(_require_list(chapter["evidence"], f"{label} evidence")):
            evidence_label = f"{label} evidence {evidence_index + 1}"
            evidence = _require_mapping(evidence, evidence_label)
            _require_exact_keys(evidence, EVIDENCE_KEYS, EVIDENCE_KEYS, evidence_label)
            if evidence["window"] not in chapter_windows:
                raise ManifestValidationError(f"{evidence_label} has an invalid source window")
            _require_text(evidence["label"], f"{evidence_label} label")

        for visual_index, visual in enumerate(
            _require_list(chapter["visuals"], f"{label} visuals", allow_empty=True)
        ):
            _validate_visual(visual, chapter_windows, block_by_window, f"{label} visual {visual_index + 1}")

    if mapped_windows != expected_windows:
        raise ManifestValidationError(
            "chapter source windows must cover every transcript window exactly once and in order"
        )
    return blocks
