import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_visual_reader import TRANSCRIPT_BLOCKS, load_visual_reader, valid_manifest


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
)


def load_visual_frames():
    path = SCRIPTS_DIR / "visual_frames.py"
    spec = importlib.util.spec_from_file_location("visual_frames", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


class RepresentativeFrameTests(unittest.TestCase):
    def test_sourced_chapter_title_becomes_plain_frame_text(self):
        frames_module = load_visual_frames()
        blocks = [{"window": "00:00-00:30", "text": "Launch evidence."}]
        manifest = {
            "chapters": [
                {
                    "id": "launch",
                    "title": {
                        "text": "Launch review",
                        "source_windows": ["00:00-00:30"],
                    },
                    "source_windows": ["00:00-00:30"],
                    "frame_priority": 1,
                }
            ]
        }

        class Completed:
            returncode = 0

        def run_command(command):
            Path(command[-1]).write_bytes(b"valid webp fixture")
            return Completed()

        with tempfile.TemporaryDirectory() as temp_dir:
            records = frames_module.extract_representative_frames(
                video_path=Path(temp_dir) / "video.mp4",
                calibrated_transcript_blocks=blocks,
                manifest=manifest,
                working_dir=Path(temp_dir) / "frames",
                duration_seconds=30,
                command_runner=run_command,
                frame_inspector=lambda path: {
                    "width": 1280,
                    "height": 720,
                    "mean_luma": 80,
                },
            )

        self.assertEqual(records[0]["alt"], "Launch review")
        self.assertEqual(records[0]["caption"], "Launch review")

    def test_extracts_bounded_in_window_webp_frames_with_fallback(self):
        frames_module = load_visual_frames()
        blocks = []
        chapters = []
        for index in range(14):
            start = index * 30
            end = start + 30
            window = f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"
            blocks.append({"window": window, "text": f"Evidence for chapter {index}."})
            chapters.append(
                {
                    "id": f"chapter-{index}",
                    "title": f"Chapter {index}",
                    "source_windows": [window],
                    "frame_priority": 20 - index,
                }
            )
        manifest = {"chapters": chapters}
        commands = []
        attempts = {}

        class Completed:
            returncode = 0

        def run_command(command):
            commands.append(command)
            output = Path(command[-1])
            key = output.name
            attempts[key] = attempts.get(key, 0) + 1
            if attempts[key] > 1:
                output.write_bytes(b"valid webp fixture")
            return Completed()

        def inspect_frame(path):
            if not path.exists() or not path.stat().st_size:
                return None
            return {"width": 1280, "height": 720, "mean_luma": 80}

        with tempfile.TemporaryDirectory() as temp_dir:
            records = frames_module.extract_representative_frames(
                video_path=Path(temp_dir) / "video.mp4",
                calibrated_transcript_blocks=blocks,
                manifest=manifest,
                working_dir=Path(temp_dir) / "frames",
                duration_seconds=300,
                command_runner=run_command,
                frame_inspector=inspect_frame,
            )
            long_records = frames_module.extract_representative_frames(
                video_path=Path(temp_dir) / "video.mp4",
                calibrated_transcript_blocks=blocks,
                manifest=manifest,
                working_dir=Path(temp_dir) / "long-frames",
                duration_seconds=3601,
                command_runner=run_command,
                frame_inspector=inspect_frame,
            )

        self.assertEqual(len(records), 8)
        self.assertEqual(len(long_records), 12)
        self.assertTrue(all(record["path"].suffix == ".webp" for record in records))
        self.assertEqual(len({record["path"].name for record in records}), 8)
        self.assertTrue(all(record["width"] == 1280 for record in records))
        self.assertGreaterEqual(len(commands), 16)
        for command in commands:
            self.assertIn("-frames:v", command)
            self.assertIn("libwebp", command)
            self.assertIn("scale='min(1280,iw)':-2", command)
        for record in records:
            start, end = frames_module.window_bounds(record["source_window"])
            self.assertGreaterEqual(record["timestamp_seconds"], start)
            self.assertLessEqual(record["timestamp_seconds"], end)

    def test_failed_or_dark_frames_degrade_without_cancelling_reader(self):
        frames_module = load_visual_frames()
        manifest = valid_manifest()
        manifest["chapters"][0]["frame_priority"] = 1

        class Completed:
            returncode = 0

        def run_command(command):
            Path(command[-1]).write_bytes(b"dark frame")
            return Completed()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            records = frames_module.extract_representative_frames(
                video_path=root / "video.mp4",
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                manifest=manifest,
                working_dir=root / "frames",
                duration_seconds=60,
                command_runner=run_command,
                frame_inspector=lambda path: {"width": 1280, "height": 720, "mean_luma": 2},
            )
            self.assertEqual(records, [])
            reader = load_visual_reader()
            result = reader.render_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="validated",
                trusted_metadata={"title": "Video"},
                media_source={"kind": "local-video", "url": None},
                manifest=manifest,
                output_destination=root / "video.html",
                frame_assets=records,
            )
            self.assertTrue(result.html_path.exists())
            self.assertNotIn("<img", result.html_path.read_text(encoding="utf-8"))

    def test_renderer_publishes_successful_frame_with_safe_image_contract(self):
        manifest = valid_manifest()
        manifest["chapters"][0]["frame_priority"] = 1
        reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.webp"
            source.write_bytes(b"fixture webp")
            result = reader.render_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="validated",
                trusted_metadata={"title": "Video"},
                media_source={"kind": "local-video", "url": None},
                manifest=manifest,
                output_destination=root / "video.html",
                frame_assets=[
                    {
                        "chapter_id": "launch",
                        "source_window": "00:00-00:30",
                        "timestamp_seconds": 15,
                        "path": source,
                        "width": 1280,
                        "height": 720,
                        "alt": "Launch evidence",
                        "caption": "Source frame at 00:15",
                    }
                ],
            )
            page = result.html_path.read_text(encoding="utf-8")
            self.assertIn('src="video_assets/frames/001_00-00_00-30.webp"', page)
            self.assertIn('width="1280" height="720"', page)
            self.assertIn('loading="lazy" decoding="async"', page)
            self.assertIn('alt="Launch evidence"', page)
            self.assertIn("Source frame at 00:15", page)
            self.assertTrue((result.assets_dir / "frames" / "001_00-00_00-30.webp").is_file())


if __name__ == "__main__":
    unittest.main()
