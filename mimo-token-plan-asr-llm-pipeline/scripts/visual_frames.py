import json
import subprocess
from pathlib import Path


FRAME_ATTEMPT_FRACTIONS = (0.5, 0.35, 0.65, 0.2)
SHORT_FRAME_LIMIT = 8
LONG_FRAME_LIMIT = 12
MIN_MEAN_LUMA = 8


def _frame_label(chapter):
    title = chapter.get("title")
    if isinstance(title, dict):
        title = title.get("text")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return "Representative source frame"


def window_bounds(window):
    start_label, end_label = window.split("-", 1)

    def seconds(label):
        minute, second = map(int, label.split(":"))
        return minute * 60 + second

    start = seconds(start_label)
    end = seconds(end_label)
    if start >= end:
        raise ValueError(f"invalid transcript window: {window}")
    return start, end


def frame_filename(sequence, source_window):
    start_label, end_label = source_window.split("-", 1)
    return (
        f"{sequence:03d}_{start_label.replace(':', '-')}_"
        f"{end_label.replace(':', '-')}.webp"
    )


def _default_runner(command):
    return subprocess.run(command, capture_output=True, check=False)


def inspect_webp_frame(path):
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "json", str(path),
        ],
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        return None
    try:
        stream = json.loads(probe.stdout.decode("utf-8"))["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, UnicodeError):
        return None
    pixels = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path), "-vf",
            "scale=32:32,format=gray", "-frames:v", "1", "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=False,
    )
    if pixels.returncode != 0 or not pixels.stdout:
        return None
    return {
        "width": width,
        "height": height,
        "mean_luma": sum(pixels.stdout) / len(pixels.stdout),
    }


def _chapter_candidates(blocks, manifest, limit):
    known_windows = {block["window"] for block in blocks}
    candidates = []
    for index, chapter in enumerate(manifest.get("chapters", [])):
        priority = chapter.get("frame_priority", 0)
        windows = chapter.get("source_windows", [])
        if not isinstance(priority, int) or priority <= 0 or not windows:
            continue
        if any(window not in known_windows for window in windows):
            continue
        candidates.append((priority, index, chapter))
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return [chapter for _, _, chapter in candidates[:limit]]


def extract_representative_frames(*, video_path, calibrated_transcript_blocks, manifest,
                                  working_dir, duration_seconds, command_runner=None,
                                  frame_inspector=None):
    command_runner = command_runner or _default_runner
    frame_inspector = frame_inspector or inspect_webp_frame
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    limit = SHORT_FRAME_LIMIT if duration_seconds <= 3600 else LONG_FRAME_LIMIT
    chapters = _chapter_candidates(calibrated_transcript_blocks, manifest, limit)
    records = []
    for sequence, chapter in enumerate(chapters, start=1):
        windows = chapter["source_windows"]
        source_window = windows[len(windows) // 2]
        frame_label = _frame_label(chapter)
        start, end = window_bounds(source_window)
        filename = frame_filename(sequence, source_window)
        output_path = working_dir / filename
        for fraction in FRAME_ATTEMPT_FRACTIONS:
            if output_path.exists():
                output_path.unlink()
            timestamp = start + (end - start) * fraction
            command = [
                "ffmpeg", "-y", "-v", "error", "-ss", f"{timestamp:.3f}",
                "-i", str(video_path), "-frames:v", "1", "-vf",
                "scale='min(1280,iw)':-2", "-c:v", "libwebp", "-quality", "82",
                str(output_path),
            ]
            completed = command_runner(command)
            if completed.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
                continue
            inspection = frame_inspector(output_path)
            if (
                not inspection
                or inspection.get("width", 0) <= 0
                or inspection.get("height", 0) <= 0
                or inspection.get("mean_luma", 0) < MIN_MEAN_LUMA
            ):
                continue
            records.append(
                {
                    "chapter_id": chapter["id"],
                    "source_window": source_window,
                    "timestamp_seconds": timestamp,
                    "path": output_path,
                    "width": inspection["width"],
                    "height": inspection["height"],
                    "alt": frame_label,
                    "caption": frame_label,
                }
            )
            break
    return records
