import importlib.util
import hashlib
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "mimo-token-plan-asr-llm-pipeline"
    / "scripts"
    / "mimo_podcast_tool.py"
)
SPEC = importlib.util.spec_from_file_location(
    "mimo_podcast_tool_bilibili_tests",
    SCRIPT_PATH,
)
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


def url_args(url):
    return SimpleNamespace(
        input=url,
        bilibili_cookie=None,
        bilibili_cookie_file=None,
        bbdown_path=None,
        bbdown_timeout=300,
        bbdown_auto_install=False,
        ytdlp_cookies=None,
        ytdlp_cookies_from_browser=None,
    )


class BilibiliUrlTests(unittest.TestCase):
    def test_recognizes_only_real_bilibili_hosts(self):
        self.assertTrue(tool.is_bilibili_url("https://www.bilibili.com/video/BV123"))
        self.assertTrue(tool.is_bilibili_url("https://m.bilibili.com/video/BV123"))
        self.assertTrue(tool.is_bilibili_url("https://bilibili.com/video/BV123"))
        self.assertTrue(tool.is_bilibili_url("https://b23.tv/abc123"))
        self.assertFalse(tool.is_bilibili_url("https://evil-bilibili.com/video/BV123"))
        self.assertFalse(tool.is_bilibili_url("https://bilibili.com.evil.example/video/BV123"))
        self.assertFalse(tool.is_bilibili_url("https://example.com/?next=bilibili.com"))
        self.assertFalse(tool.is_bilibili_url("https://www.xiaoyuzhoufm.com/episode/123"))


class BilibiliRoutingTests(unittest.TestCase):
    def test_bilibili_failure_never_falls_back_to_ytdlp(self):
        args = url_args("https://www.bilibili.com/video/BV123")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                tool,
                "download_bilibili_audio",
                side_effect=RuntimeError("BBDown failed"),
            ) as bbdown, patch.object(tool, "download_audio") as ytdlp:
                with self.assertRaisesRegex(RuntimeError, "BBDown failed"):
                    tool.resolve_input_audio(args, Path(tmp))

        bbdown.assert_called_once()
        ytdlp.assert_not_called()

    def test_bilibili_cookie_is_passed_to_bbdown(self):
        args = url_args("https://b23.tv/abc123")
        args.bilibili_cookie = "SESSDATA=secret"
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "downloaded.m4a"
            with patch.object(
                tool,
                "download_bilibili_audio",
                return_value=audio_path,
            ) as bbdown, patch.object(tool, "download_audio") as ytdlp:
                result = tool.resolve_input_audio(args, Path(tmp))

        self.assertEqual(result, audio_path)
        self.assertEqual(bbdown.call_args.kwargs["cookie"], "SESSDATA=secret")
        ytdlp.assert_not_called()

    def test_non_bilibili_url_still_uses_ytdlp(self):
        args = url_args("https://www.xiaoyuzhoufm.com/episode/123")
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "downloaded.mp3"
            with patch.object(tool, "check_yt_dlp", return_value=True), patch.object(
                tool,
                "download_audio",
                return_value=audio_path,
            ) as ytdlp, patch.object(tool, "download_bilibili_audio") as bbdown:
                result = tool.resolve_input_audio(args, Path(tmp))

        self.assertEqual(result, audio_path)
        ytdlp.assert_called_once()
        bbdown.assert_not_called()


class BilibiliCliTests(unittest.TestCase):
    def test_removed_bilibili_downloader_option_is_rejected(self):
        argv = [
            str(SCRIPT_PATH),
            "https://www.bilibili.com/video/BV123",
            "--bilibili-downloader",
            "auto",
        ]
        with patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit):
                tool.parse_args()

    def test_bbdown_auto_install_is_enabled_by_default_and_can_be_disabled(self):
        with patch.object(sys, "argv", [str(SCRIPT_PATH), "--self-test"]):
            default_args = tool.parse_args()
        with patch.object(
            sys,
            "argv",
            [str(SCRIPT_PATH), "--self-test", "--no-bbdown-auto-install"],
        ):
            disabled_args = tool.parse_args()

        self.assertTrue(default_args.bbdown_auto_install)
        self.assertFalse(disabled_args.bbdown_auto_install)


class BbdownPlatformTests(unittest.TestCase):
    def test_maps_all_supported_operating_system_and_architecture_pairs(self):
        cases = {
            ("Windows", "AMD64"): "win-x64",
            ("Windows", "ARM64"): "win-arm64",
            ("Linux", "x86_64"): "linux-x64",
            ("Linux", "aarch64"): "linux-arm64",
            ("Darwin", "x86_64"): "osx-x64",
            ("Darwin", "arm64"): "osx-arm64",
        }

        for (system_name, machine), expected in cases.items():
            with self.subTest(system=system_name, machine=machine):
                asset = tool.bbdown_asset_for_platform(system_name, machine)
                self.assertEqual(asset["platform"], expected)

    def test_rejects_unsupported_platform(self):
        with self.assertRaisesRegex(RuntimeError, "不支持自动安装"):
            tool.bbdown_asset_for_platform("Windows", "x86")


class FakeResponse(io.BytesIO):
    def __init__(self, data, content_length=None):
        super().__init__(data)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)


def bbdown_zip(binary_name="BBDown.exe", binary=b"fixture-bbdown"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(binary_name, binary)
    return buffer.getvalue()


class BbdownInstallerTests(unittest.TestCase):
    def fixture_asset(self, archive_bytes, binary="BBDown.exe"):
        return {
            "platform": "win-x64",
            "asset": "fixture.zip",
            "sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "binary": binary,
        }

    def test_installs_verified_archive_and_reuses_cached_executable(self):
        archive_bytes = bbdown_zip()
        asset = self.fixture_asset(archive_bytes)
        requests = []

        def opener(request, timeout):
            requests.append((request.full_url, timeout))
            return FakeResponse(archive_bytes, len(archive_bytes))

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            installed = tool.install_bbdown(
                cache_root=Path(tmp),
                system_name="Windows",
                machine="AMD64",
                opener=opener,
            )
            reused = tool.install_bbdown(
                cache_root=Path(tmp),
                system_name="Windows",
                machine="AMD64",
                opener=lambda *_args, **_kwargs: self.fail("cache miss"),
            )

            self.assertEqual(installed.read_bytes(), b"fixture-bbdown")
            self.assertEqual(reused, installed)
            self.assertEqual(len(requests), 1)
            self.assertTrue(requests[0][0].endswith("/1.6.3/fixture.zip"))
            self.assertFalse(list(Path(tmp).rglob("*.part*")))

    def test_rejects_checksum_mismatch_and_cleans_partials(self):
        archive_bytes = bbdown_zip()
        asset = self.fixture_asset(archive_bytes)
        asset["sha256"] = "0" * 64

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                tool.install_bbdown(
                    cache_root=Path(tmp),
                    system_name="Windows",
                    machine="AMD64",
                    opener=lambda *_args, **_kwargs: FakeResponse(archive_bytes),
                )

            self.assertFalse(list(Path(tmp).rglob("BBDown.exe")))
            self.assertFalse(list(Path(tmp).rglob("*.part*")))

    def test_rejects_archive_without_expected_root_executable(self):
        archive_bytes = bbdown_zip(binary_name="nested/BBDown.exe")
        asset = self.fixture_asset(archive_bytes)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            with self.assertRaisesRegex(RuntimeError, "根目录"):
                tool.install_bbdown(
                    cache_root=Path(tmp),
                    system_name="Windows",
                    machine="AMD64",
                    opener=lambda *_args, **_kwargs: FakeResponse(archive_bytes),
                )

    def test_rejects_corrupt_zip_archive(self):
        archive_bytes = b"not-a-zip"
        asset = self.fixture_asset(archive_bytes)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            with self.assertRaisesRegex(RuntimeError, "ZIP"):
                tool.install_bbdown(
                    cache_root=Path(tmp),
                    system_name="Windows",
                    machine="AMD64",
                    opener=lambda *_args, **_kwargs: FakeResponse(archive_bytes),
                )

    def test_reports_download_failure_and_cleans_partials(self):
        archive_bytes = bbdown_zip()
        asset = self.fixture_asset(archive_bytes)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            with self.assertRaisesRegex(RuntimeError, "下载失败"):
                tool.install_bbdown(
                    cache_root=Path(tmp),
                    system_name="Windows",
                    machine="AMD64",
                    opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                        OSError("network down")
                    ),
                )

            self.assertFalse(list(Path(tmp).rglob("*.part*")))

    def test_rejects_download_larger_than_limit(self):
        archive_bytes = bbdown_zip()
        asset = self.fixture_asset(archive_bytes)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(
            tool.BBDOWN_ASSETS,
            {"win-x64": asset},
        ):
            with self.assertRaisesRegex(RuntimeError, "32 MiB"):
                tool.install_bbdown(
                    cache_root=Path(tmp),
                    system_name="Windows",
                    machine="AMD64",
                    opener=lambda *_args, **_kwargs: FakeResponse(
                        archive_bytes,
                        tool.BBDOWN_MAX_DOWNLOAD_BYTES + 1,
                    ),
                )

    def test_disabled_auto_install_fails_without_using_network(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            tool.shutil,
            "which",
            return_value=None,
        ), patch.dict(tool.os.environ, {"BBDOWN_PATH": ""}, clear=False):
            with self.assertRaisesRegex(FileNotFoundError, "自动安装已关闭"):
                tool.resolve_bbdown_path(
                    auto_install=False,
                    cache_root=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()
