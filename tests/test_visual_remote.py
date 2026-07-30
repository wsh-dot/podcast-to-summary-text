import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_visual_reader import TRANSCRIPT_BLOCKS, load_visual_reader, valid_manifest


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
)


def load_module(name):
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(SCRIPTS_DIR))
    return module


class RemoteVisualRoutingTests(unittest.TestCase):
    def test_bilibili_visual_download_uses_bbdown_only_and_reuses_cookie(self):
        tool = load_module("mimo_podcast_tool")
        commands = []

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        def run(command, **kwargs):
            commands.append((command, kwargs))
            (Path(kwargs["cwd"]) / "visual.mp4").write_bytes(b"video")
            return Completed()

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            tool, "resolve_bbdown_path", return_value="BBDown"
        ), patch.object(tool.subprocess, "run", side_effect=run), patch.object(
            tool, "download_remote_video", side_effect=AssertionError("yt-dlp fallback")
        ):
            result = tool.download_bilibili_video(
                "https://www.bilibili.com/video/BV123",
                Path(temp_dir),
                cookie="SESSDATA=fixture",
                auto_install=False,
            )

        self.assertEqual(result.name, "visual.mp4")
        command = commands[0][0]
        self.assertIn("--video-only", command)
        self.assertIn("--video-ascending", command)
        self.assertIn("-c", command)
        self.assertIn("SESSDATA=fixture", command)
        self.assertNotIn("yt-dlp", command)

    def test_other_remote_video_uses_bounded_ytdlp_format(self):
        tool = load_module("mimo_podcast_tool")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        def run(command, **kwargs):
            (Path(temp_dir) / "visual.webm").write_bytes(b"video")
            self.assertEqual(command[0], "yt-dlp")
            self.assertIn("height<=720", " ".join(command))
            self.assertIn("--no-playlist", command)
            return Completed()

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            tool.subprocess, "run", side_effect=run
        ):
            result = tool.download_remote_video(
                "https://example.com/video",
                Path(temp_dir),
            )
        self.assertEqual(result.name, "visual.webm")

    def test_time_links_are_platform_specific_and_never_fabricated(self):
        remote = load_module("visual_remote")
        self.assertIn(
            "t=75",
            remote.source_time_url("https://www.bilibili.com/video/BV123?spm_id=x", 75),
        )
        self.assertIn("t=75", remote.source_time_url("https://youtu.be/abc", 75))
        self.assertEqual(
            remote.source_time_url("https://example.com/watch/abc", 75),
            "https://example.com/watch/abc",
        )
        self.assertIsNone(remote.source_time_url(None, 75))

    def test_reader_uses_verified_chapter_time_links(self):
        reader = load_visual_reader()
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "video.html"
            reader.render_visual_brief(
                calibrated_transcript_blocks=TRANSCRIPT_BLOCKS,
                validated_timeline_report="validated",
                trusted_metadata={"title": "Video"},
                media_source={
                    "kind": "remote-video",
                    "url": "https://www.bilibili.com/video/BV123?spm_id=x",
                },
                manifest=valid_manifest(),
                output_destination=destination,
            )
            page = destination.read_text(encoding="utf-8")
            self.assertIn("Open source at 00:00", page)
            self.assertIn("t=0", page)


if __name__ == "__main__":
    unittest.main()
