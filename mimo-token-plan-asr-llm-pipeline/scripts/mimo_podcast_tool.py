#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio/video transcription and timeline podcast report generator.

Default behavior:
  1. Split audio into 3-minute ASR windows.
  2. Transcribe each window with the configured ASR provider.
  3. Save a timestamp-window transcript when --save-transcript is set.
  4. Pipeline proofreading -> summary per batch, proofread inline, or reuse calibrated input.
  5. Generate batches with bounded LLM concurrency, or export IDE prompts for manual summary.
  6. Validate that every transcript window has exactly one report section.
"""

import argparse
import base64
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


# ============================================================
# Configuration
# ============================================================

DEFAULT_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
DEFAULT_ASR_MODEL = "mimo-v2.5-asr"
DEFAULT_LLM_MODEL = "mimo-v2.5-pro"
STEPFUN_BASE_URL = "https://api.stepfun.com/v1"
STEPFUN_PLAN_BASE_URL = "https://api.stepfun.com/step_plan/v1"

ASR_PROVIDER_DEFAULTS = {
    "mimo": {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_ASR_MODEL,
        "api_envs": ("MIMO_API_KEY",),
    },
    "aliyun-qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-asr-flash",
        "api_envs": ("DASHSCOPE_API_KEY", "ALIYUN_API_KEY"),
    },
    "stepfun": {
        "base_url": STEPFUN_BASE_URL,
        "plan_base_url": STEPFUN_PLAN_BASE_URL,
        "model": "stepaudio-2.5-asr",
        "api_envs": ("STEPFUN_API_KEY", "STEP_API_KEY"),
    },
    "tencent": {
        "engine_model_type": "16k_zh",
        "region": "ap-guangzhou",
        "secret_id_envs": ("TENCENTCLOUD_SECRET_ID", "TENCENT_SECRET_ID"),
        "secret_key_envs": ("TENCENTCLOUD_SECRET_KEY", "TENCENT_SECRET_KEY"),
    },
}

LLM_PROVIDER_DEFAULTS = {
    "mimo": {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_LLM_MODEL,
        "api_envs": ("MIMO_API_KEY",),
    },
    "aliyun": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "api_envs": ("DASHSCOPE_API_KEY", "ALIYUN_API_KEY"),
    },
    "tencent": {
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "model": "hunyuan-turbos-latest",
        "api_envs": ("HUNYUAN_API_KEY", "TENCENT_HUNYUAN_API_KEY"),
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-5.2",
        "api_envs": ("ZAI_API_KEY", "ZHIPUAI_API_KEY", "BIGMODEL_API_KEY"),
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.6",
        "api_envs": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    },
    "minimax": {
        "base_url": "https://api.minimax.io/v1",
        "model": "MiniMax-M3",
        "api_envs": ("MINIMAX_API_KEY",),
    },
    "openai-compatible": {
        "base_url": "",
        "model": "",
        "api_envs": ("LLM_API_KEY",),
    },
}

DEFAULT_SEGMENT_MINUTES = 3
DEFAULT_TIMELINE_BATCH_SIZE = 6
DEFAULT_PROOFREAD_BATCH_SIZE = 6
DEFAULT_PROOFREAD_MIN_RATIO = 0.55
DEFAULT_LLM_CONCURRENCY = 2

BBDOWN_VERSION = "1.6.3"
BBDOWN_RELEASE_BASE_URL = "https://github.com/nilaoda/BBDown/releases/download"
BBDOWN_MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
BBDOWN_DOWNLOAD_TIMEOUT = 60
BBDOWN_ASSETS = {
    "win-x64": {
        "platform": "win-x64",
        "asset": "BBDown_1.6.3_20240814_win-x64.zip",
        "sha256": "40f1e2af0d4e74df765c6f93d2e931f9bea201d5168d0bc62dc35a54b7e0ec02",
        "binary": "BBDown.exe",
    },
    "win-arm64": {
        "platform": "win-arm64",
        "asset": "BBDown_1.6.3_20240814_win-arm64.zip",
        "sha256": "da8fc9cbf1031f4c4ca97af82d98bbfd1bbc55bd8ea49602da8d3d1613c190ff",
        "binary": "BBDown.exe",
    },
    "linux-x64": {
        "platform": "linux-x64",
        "asset": "BBDown_1.6.3_20240814_linux-x64.zip",
        "sha256": "ec233b7d8d40b1cc4447dac05be343f53a757dc605743a8808abaa8e97e5d10e",
        "binary": "BBDown",
    },
    "linux-arm64": {
        "platform": "linux-arm64",
        "asset": "BBDown_1.6.3_20240814_linux-arm64.zip",
        "sha256": "f58e0a18df1a589375428a0af27ea61f5ce96ffaf67d115f335d5f9bee9a34dc",
        "binary": "BBDown",
    },
    "osx-x64": {
        "platform": "osx-x64",
        "asset": "BBDown_1.6.3_20240814_osx-x64.zip",
        "sha256": "262c15ca7890898560d00e5ffd5ada1864fbd9d0d58ac4ee492c9f3e73f3ae5f",
        "binary": "BBDown",
    },
    "osx-arm64": {
        "platform": "osx-arm64",
        "asset": "BBDown_1.6.3_20240814_osx-arm64.zip",
        "sha256": "4df84014d818bd6dff2b365b847645340e8955c4450fe965688f41af89a38baa",
        "binary": "BBDown",
    },
}

LLM_MAX_TOKENS_STANDARD = 4096
LLM_MAX_TOKENS_PROOFREAD_BATCH = 8192
LLM_MAX_TOKENS_TIMELINE_BATCH = 8192
LLM_MAX_TOKENS_FINAL_TABLE = 4096

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}
BILIBILI_AUDIO_EXTENSIONS = AUDIO_EXTENSIONS | {".m4s"}
BILIBILI_MEDIA_EXTENSIONS = BILIBILI_AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

WINDOW_RE = re.compile(r"^\[(\d{2}:\d{2}-\d{2}:\d{2})\]\s*$", re.MULTILINE)
SECTION_RE = re.compile(
    r"(?ms)^##\s+(\d{2}:\d{2}-\d{2}:\d{2})\s+.*?"
    r"(?=^##\s+(?:\d{2}:\d{2}-\d{2}:\d{2}\s+|核心观点速览\b)|\Z)"
)
SECTION_HEADING_RE = re.compile(r"^##\s+(\d{2}:\d{2}-\d{2}:\d{2})\b", re.MULTILINE)


# ============================================================
# Formatting helpers
# ============================================================

def positive_int(value):
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def positive_float(value):
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def select_proofread_mode(requested_mode, no_proofread, transcript_path):
    """Resolve the effective proofreading mode without reprocessing calibrated input."""
    if no_proofread:
        return "skip"
    if requested_mode:
        return requested_mode
    if transcript_path and Path(transcript_path).stem.endswith(("_校对", "_calibrated")):
        return "skip"
    return "separate"


def ordered_parallel_map(worker, items, max_workers):
    """Run independent jobs with bounded concurrency and preserve input order."""
    items = list(items)
    if not items:
        return []
    if max_workers <= 1:
        return [worker(item) for item in items]

    results = [None] * len(items)
    worker_count = min(max_workers, len(items))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = {
            pool.submit(worker, item): index
            for index, item in enumerate(items)
        }
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def format_timecode(seconds, round_up=False):
    """Format elapsed audio time as HH:MM for podcast section anchors."""
    seconds = max(0, float(seconds or 0))
    total_minutes = int(math.ceil(seconds / 60.0)) if round_up else int(seconds // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"


def format_duration(seconds):
    if seconds is None:
        return None
    total_minutes = max(1, int(math.ceil(float(seconds) / 60.0)))
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours and minutes:
        return f"约 {hours} 小时 {minutes} 分钟"
    if hours:
        return f"约 {hours} 小时"
    return f"约 {minutes} 分钟"


def time_window_for_chunk(index, segment_minutes, duration_seconds=None):
    segment_seconds = segment_minutes * 60
    start_seconds = index * segment_seconds
    end_seconds = start_seconds + segment_seconds
    if duration_seconds is not None:
        end_seconds = min(end_seconds, float(duration_seconds))
        if end_seconds <= start_seconds:
            end_seconds = start_seconds + segment_seconds
    return (
        format_timecode(start_seconds),
        format_timecode(end_seconds, round_up=True),
    )


def safe_stem(value, default="podcast"):
    invalid = '<>:"/\\|?*'
    cleaned = "".join("_" if char in invalid else char for char in (value or "").strip())
    cleaned = "_".join(cleaned.split())
    return cleaned[:80] or default


def strip_known_suffixes(stem):
    for suffix in ("_转写", "_校对", "_transcript", "_calibrated", "_报告", "_深度报告", "_逐窗口深度解读"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def chunk_list(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def is_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def is_bilibili_url(url):
    if not is_url(url):
        return False
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    return (
        hostname == "bilibili.com"
        or hostname.endswith(".bilibili.com")
        or hostname == "b23.tv"
        or hostname.endswith(".b23.tv")
    )


def extract_bilibili_bvid(url):
    match = re.search(r"BV[0-9A-Za-z]+", url or "")
    return match.group(0) if match else None


# ============================================================
# Media helpers
# ============================================================

def get_audio_duration(audio_path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"警告: 无法获取音频时长: {result.stderr}")
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def check_ffmpeg():
    return shutil.which("ffmpeg") is not None


def check_yt_dlp():
    return shutil.which("yt-dlp") is not None


def bbdown_asset_for_platform(system_name=None, machine=None):
    system_key = (system_name or platform.system()).strip().lower()
    machine_key = (machine or platform.machine()).strip().lower()

    if machine_key in {"amd64", "x86_64", "x64"}:
        architecture = "x64"
    elif machine_key in {"arm64", "aarch64"}:
        architecture = "arm64"
    else:
        architecture = machine_key

    system_prefix = {
        "windows": "win",
        "linux": "linux",
        "darwin": "osx",
    }.get(system_key)
    platform_key = f"{system_prefix}-{architecture}" if system_prefix else ""
    if platform_key not in BBDOWN_ASSETS:
        raise RuntimeError(
            f"当前平台不支持自动安装 BBDown: {system_name or platform.system()} "
            f"{machine or platform.machine()}。请通过 --bbdown-path 或 BBDOWN_PATH 指定可执行文件。"
        )
    return BBDOWN_ASSETS[platform_key]


def default_bbdown_cache_root(system_name=None):
    system_key = (system_name or platform.system()).strip().lower()
    if system_key == "windows":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    elif system_key == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    return base / "podcast-to-summary-text" / "bbdown"


def bbdown_cached_executable(cache_root=None, system_name=None, machine=None):
    asset = bbdown_asset_for_platform(system_name, machine)
    root = Path(cache_root) if cache_root else default_bbdown_cache_root(system_name)
    return root / BBDOWN_VERSION / asset["platform"] / asset["binary"]


def install_bbdown(cache_root=None, system_name=None, machine=None, opener=None):
    asset = bbdown_asset_for_platform(system_name, machine)
    executable = bbdown_cached_executable(
        cache_root=cache_root,
        system_name=system_name,
        machine=machine,
    )
    if executable.is_file():
        print(f"复用已缓存 BBDown {BBDOWN_VERSION}: {executable}")
        return executable

    executable.parent.mkdir(parents=True, exist_ok=True)
    download_url = f"{BBDOWN_RELEASE_BASE_URL}/{BBDOWN_VERSION}/{asset['asset']}"
    archive_handle = tempfile.NamedTemporaryFile(
        prefix=f"{asset['asset']}.",
        suffix=".part",
        dir=executable.parent,
        delete=False,
    )
    archive_path = Path(archive_handle.name)
    archive_handle.close()
    binary_handle = tempfile.NamedTemporaryFile(
        prefix=f"{asset['binary']}.",
        suffix=".part",
        dir=executable.parent,
        delete=False,
    )
    binary_path = Path(binary_handle.name)
    binary_handle.close()

    print(f"未找到 BBDown，下载固定版本 {BBDOWN_VERSION}: {asset['asset']}")
    request = Request(download_url, headers={"User-Agent": "podcast-to-summary-text/1"})
    open_url = opener or urlopen
    try:
        try:
            response_context = open_url(request, timeout=BBDOWN_DOWNLOAD_TIMEOUT)
            with response_context as response, archive_path.open("wb") as output:
                declared_size = response.headers.get("Content-Length")
                if declared_size and int(declared_size) > BBDOWN_MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("BBDown 下载超过安全上限 32 MiB。")

                digest = hashlib.sha256()
                downloaded_size = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded_size += len(chunk)
                    if downloaded_size > BBDOWN_MAX_DOWNLOAD_BYTES:
                        raise RuntimeError("BBDown 下载超过安全上限 32 MiB。")
                    digest.update(chunk)
                    output.write(chunk)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"BBDown 下载失败: {exc}") from exc

        actual_hash = digest.hexdigest()
        if actual_hash.lower() != asset["sha256"].lower():
            raise RuntimeError(
                "BBDown ZIP SHA-256 校验失败: "
                f"expected {asset['sha256']}, got {actual_hash}"
            )

        try:
            with zipfile.ZipFile(archive_path) as archive:
                if asset["binary"] not in archive.namelist():
                    raise RuntimeError(
                        f"BBDown ZIP 根目录缺少预期可执行文件: {asset['binary']}"
                    )
                with archive.open(asset["binary"]) as source, binary_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
        except RuntimeError:
            raise
        except zipfile.BadZipFile as exc:
            raise RuntimeError(f"BBDown ZIP 文件损坏: {exc}") from exc

        if (system_name or platform.system()).strip().lower() != "windows":
            os.chmod(binary_path, 0o755)
        os.replace(binary_path, executable)
        print(f"BBDown {BBDOWN_VERSION} 已安装并通过 SHA-256 校验: {executable}")
        return executable
    finally:
        archive_path.unlink(missing_ok=True)
        binary_path.unlink(missing_ok=True)


def resolve_bbdown_path(preferred_path=None, auto_install=True, cache_root=None):
    if preferred_path:
        preferred = Path(preferred_path).expanduser()
        if not preferred.is_file():
            raise FileNotFoundError(f"--bbdown-path 指定的文件不存在: {preferred}")
        return str(preferred)

    environment_path = os.environ.get("BBDOWN_PATH", "").strip()
    if environment_path:
        configured = Path(environment_path).expanduser()
        if not configured.is_file():
            raise FileNotFoundError(f"BBDOWN_PATH 指定的文件不存在: {configured}")
        return str(configured)

    executable_names = ["BBDown.exe", "BBDown"] if os.name == "nt" else ["BBDown_Mac", "BBDown"] if sys.platform == "darwin" else ["BBDown"]
    for name in executable_names:
        found = shutil.which(name)
        if found:
            return found

    skill_root = Path(__file__).resolve().parents[1]
    for base_dir in (Path.cwd(), skill_root):
        for name in executable_names:
            candidate = base_dir / "BBDown" / name
            if candidate.is_file():
                return str(candidate)

    cached = bbdown_cached_executable(cache_root=cache_root)
    if cached.is_file():
        return str(cached)
    if auto_install:
        return str(install_bbdown(cache_root=cache_root))

    raise FileNotFoundError(
        "未找到 BBDown，且自动安装已关闭。请安装 BBDown，或通过 "
        "--bbdown-path / BBDOWN_PATH 指定可执行文件。"
    )


def resolve_bilibili_cookie(args):
    if getattr(args, "bilibili_cookie", None):
        return args.bilibili_cookie.strip()
    cookie_file = getattr(args, "bilibili_cookie_file", None)
    if cookie_file:
        path = Path(cookie_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"B站 cookie 文件不存在: {path}")
        return path.read_text(encoding="utf-8").strip()
    return ""


def chunk_audio(audio_path, temp_dir, segment_minutes=DEFAULT_SEGMENT_MINUTES):
    segment_seconds = segment_minutes * 60
    chunk_pattern = str(temp_dir / "chunk_%03d.mp3")

    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-f", "segment", "-segment_time", str(segment_seconds),
            "-c", "copy", chunk_pattern,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("copy 模式失败，尝试重新编码...")
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-f", "segment", "-segment_time", str(segment_seconds),
                "-c:a", "libmp3lame", "-q:a", "2", chunk_pattern,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 分片失败: {result.stderr}")

    chunks = sorted(temp_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg 未生成任何音频分片")
    return chunks


def extract_audio_from_video(video_path, output_path):
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(output_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"从视频提取音频失败: {result.stderr}")
    return output_path


def download_audio(url, output_dir, cookie=None, cookies_file=None, cookies_from_browser=None):
    output_template = str(output_dir / "downloaded.%(ext)s")
    command = [
        "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "-o", output_template,
    ]
    if cookie:
        command.extend(["--add-headers", f"Cookie:{cookie}"])
    if cookies_file:
        command.extend(["--cookies", str(cookies_file)])
    if cookies_from_browser:
        command.extend(["--cookies-from-browser", str(cookies_from_browser)])
    command.append(url)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载失败: {result.stderr}")

    downloaded = list(output_dir.glob("downloaded.*"))
    if not downloaded:
        raise FileNotFoundError("下载完成但未找到音频文件")
    return downloaded[0]


def download_bilibili_audio(
    url,
    output_dir,
    bbdown_path=None,
    cookie=None,
    timeout=300,
    auto_install=True,
):
    executable = resolve_bbdown_path(bbdown_path, auto_install=auto_install)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [executable, url, "--audio-only", "-F", "downloaded"]
    if cookie:
        command.extend(["-c", cookie])

    print(f"使用 BBDown 下载 B站音频: {Path(executable).name}")
    result = subprocess.run(
        command,
        cwd=output_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        details = "\n".join(part for part in (result.stderr, result.stdout) if part)
        raise RuntimeError(f"BBDown 下载失败: {details}")

    downloaded = [
        path for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in BILIBILI_MEDIA_EXTENSIONS
    ]
    if not downloaded:
        raise FileNotFoundError("BBDown 下载完成但未找到音视频文件")
    return max(downloaded, key=lambda path: path.stat().st_mtime)


# ============================================================
# Provider adapters
# ============================================================

def load_openai_client(api_key, base_url):
    try:
        from openai import OpenAI
    except ImportError:
        print("错误: 需要安装 openai SDK。请运行: pip install openai")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url=base_url)


class BaseASRProvider:
    name = "base"

    def transcribe_chunk(self, chunk_path):
        raise NotImplementedError


class MiMoASRProvider(BaseASRProvider):
    name = "mimo"

    def __init__(self, api_key, base_url, model):
        self.client = load_openai_client(api_key, base_url)
        self.model = model

    def transcribe_chunk(self, chunk_path):
        with open(chunk_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:audio/mpeg;base64,{audio_b64}",
                            },
                        }
                    ],
                }
            ],
            extra_body={"asr_options": {"language": "auto"}},
        )
        return response.choices[0].message.content or ""


class AliyunQwenASRProvider(BaseASRProvider):
    name = "aliyun-qwen"

    def __init__(self, api_key, base_url, model):
        self.client = load_openai_client(api_key, base_url)
        self.model = model

    def transcribe_chunk(self, chunk_path):
        with open(chunk_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:audio/mpeg;base64,{audio_b64}",
                                "format": "mp3",
                            },
                        }
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""


class StepFunSSEASRProvider(BaseASRProvider):
    """StepFun HTTP + SSE adapter for standard and Step Plan ASR paths."""

    name = "stepfun"

    def __init__(
        self,
        api_key,
        base_url,
        model,
        language=None,
        timeout=120,
        opener=urlopen,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.timeout = timeout
        self.opener = opener

    def transcribe_chunk(self, chunk_path):
        audio_b64 = base64.b64encode(Path(chunk_path).read_bytes()).decode("ascii")
        transcription = {
            "model": self.model,
            "enable_itn": True,
        }
        if self.language:
            transcription["language"] = self.language
        payload = {
            "audio": {
                "data": audio_b64,
                "input": {
                    "transcription": transcription,
                    "format": {"type": "mp3"},
                },
            }
        }
        request = Request(
            f"{self.base_url}/audio/asr/sse",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )

        deltas = []
        done_text = ""
        seen_done = False
        with self.opener(request, self.timeout) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event = json.loads(data)
                event_type = event.get("type")
                if event_type == "transcript.text.delta":
                    deltas.append(event.get("delta") or "")
                elif event_type == "transcript.text.done":
                    seen_done = True
                    done_text = event.get("text") or ""
                elif event_type == "error":
                    raise RuntimeError(event.get("message") or "StepFun ASR 返回未知错误")

        if not seen_done:
            raise RuntimeError("StepFun ASR SSE 在 transcript.text.done 事件前结束")
        return done_text or "".join(deltas)


class TencentRecordingASRProvider(BaseASRProvider):
    name = "tencent"

    def __init__(
        self,
        secret_id,
        secret_key,
        region="ap-guangzhou",
        engine_model_type="16k_zh",
        res_text_format=0,
        poll_interval=3,
        max_polls=120,
    ):
        try:
            from tencentcloud.common import credential
            from tencentcloud.common.profile.client_profile import ClientProfile
            from tencentcloud.common.profile.http_profile import HttpProfile
            from tencentcloud.asr.v20190614 import asr_client, models
        except ImportError:
            print("错误: 使用腾讯 ASR 需要安装腾讯云 SDK。请运行: pip install tencentcloud-sdk-python")
            sys.exit(1)

        self.models = models
        self.engine_model_type = engine_model_type
        self.res_text_format = res_text_format
        self.poll_interval = poll_interval
        self.max_polls = max_polls

        cred = credential.Credential(secret_id, secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = "asr.tencentcloudapi.com"
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile
        self.client = asr_client.AsrClient(cred, region, client_profile)

    @staticmethod
    def _payload(response):
        return json.loads(response.to_json_string())

    @staticmethod
    def _extract_text(data):
        result = data.get("Result")
        if result:
            return result
        details = data.get("ResultDetail") or []
        parts = []
        for item in details:
            if isinstance(item, dict):
                text = item.get("FinalSentence") or item.get("SliceSentence") or item.get("Words")
                if text:
                    parts.append(str(text))
        return "\n".join(parts)

    def transcribe_chunk(self, chunk_path):
        with open(chunk_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()

        create_req = self.models.CreateRecTaskRequest()
        create_req.from_json_string(json.dumps({
            "EngineModelType": self.engine_model_type,
            "ChannelNum": 1,
            "ResTextFormat": self.res_text_format,
            "SourceType": 1,
            "Data": audio_b64,
        }))
        create_payload = self._payload(self.client.CreateRecTask(create_req))
        task_id = (create_payload.get("Data") or {}).get("TaskId")
        if not task_id:
            raise RuntimeError(f"腾讯 ASR 未返回 TaskId: {create_payload}")

        for _ in range(self.max_polls):
            status_req = self.models.DescribeTaskStatusRequest()
            status_req.from_json_string(json.dumps({"TaskId": task_id}))
            status_payload = self._payload(self.client.DescribeTaskStatus(status_req))
            data = status_payload.get("Data") or {}
            status = data.get("Status")
            status_str = str(data.get("StatusStr") or "").lower()
            if status == 2 or status_str in {"success", "done", "completed"}:
                return self._extract_text(data)
            if status == 3 or status_str in {"failed", "failure", "error"}:
                raise RuntimeError(data.get("ErrorMsg") or f"腾讯 ASR 任务失败: {status_payload}")
            time.sleep(self.poll_interval)

        raise TimeoutError(f"腾讯 ASR 任务超时: {task_id}")


class BaseLLMProvider:
    name = "base"

    def complete(self, messages, max_tokens):
        raise NotImplementedError


class OpenAICompatibleLLMProvider(BaseLLMProvider):
    name = "openai-compatible"

    def __init__(self, api_key, base_url, model, provider_name="openai-compatible"):
        self.client = load_openai_client(api_key, base_url)
        self.model = model
        self.provider_name = provider_name

    def complete(self, messages, max_tokens):
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


def require_value(value, message):
    if not value:
        print(f"错误: {message}")
        sys.exit(1)
    return value


def first_env(env_names):
    for name in env_names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def int_env(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def provider_default(defaults, provider, key, fallback=None):
    return defaults.get(provider, {}).get(key, fallback)


def provider_env(defaults, provider, env_key="api_envs"):
    return first_env(provider_default(defaults, provider, env_key, ()))


def create_asr_provider(args):
    provider = args.asr_provider
    if provider == "mimo":
        api_key = require_value(
            args.asr_api_key or args.api_key or provider_env(ASR_PROVIDER_DEFAULTS, provider),
            "MiMo ASR 需要 --api-key、--asr-api-key 或 MIMO_API_KEY。",
        )
        base_url = args.asr_base_url or args.base_url or provider_default(ASR_PROVIDER_DEFAULTS, provider, "base_url")
        model = args.asr_model or provider_default(ASR_PROVIDER_DEFAULTS, provider, "model")
        if not api_key.startswith("tp-"):
            print("警告: MiMo Token Plan API Key 通常以 'tp-' 开头。")
        return MiMoASRProvider(api_key=api_key, base_url=base_url, model=model)

    if provider == "aliyun-qwen":
        api_key = require_value(
            args.asr_api_key or provider_env(ASR_PROVIDER_DEFAULTS, provider),
            "阿里 Qwen ASR 需要 --asr-api-key、DASHSCOPE_API_KEY 或 ALIYUN_API_KEY。",
        )
        base_url = args.asr_base_url or provider_default(ASR_PROVIDER_DEFAULTS, provider, "base_url")
        model = args.asr_model or provider_default(ASR_PROVIDER_DEFAULTS, provider, "model")
        return AliyunQwenASRProvider(api_key=api_key, base_url=base_url, model=model)

    if provider == "stepfun":
        api_key = require_value(
            args.asr_api_key or provider_env(ASR_PROVIDER_DEFAULTS, provider),
            "阶跃星辰 ASR 需要 --asr-api-key、STEPFUN_API_KEY 或 STEP_API_KEY。",
        )
        defaults = ASR_PROVIDER_DEFAULTS[provider]
        default_base_url = defaults["plan_base_url"] if args.stepfun_plan else defaults["base_url"]
        return StepFunSSEASRProvider(
            api_key=api_key,
            base_url=args.asr_base_url or default_base_url,
            model=args.asr_model or defaults["model"],
            language=args.stepfun_language,
            timeout=args.stepfun_timeout,
        )

    if provider == "tencent":
        secret_id = require_value(
            args.tencent_secret_id or provider_env(ASR_PROVIDER_DEFAULTS, provider, "secret_id_envs"),
            "腾讯 ASR 需要 --tencent-secret-id 或 TENCENTCLOUD_SECRET_ID。",
        )
        secret_key = require_value(
            args.tencent_secret_key or provider_env(ASR_PROVIDER_DEFAULTS, provider, "secret_key_envs"),
            "腾讯 ASR 需要 --tencent-secret-key 或 TENCENTCLOUD_SECRET_KEY。",
        )
        region = args.tencent_region or provider_default(ASR_PROVIDER_DEFAULTS, provider, "region")
        engine_model_type = (
            args.tencent_engine_model_type
            or args.asr_model
            or provider_default(ASR_PROVIDER_DEFAULTS, provider, "engine_model_type")
        )
        return TencentRecordingASRProvider(
            secret_id=secret_id,
            secret_key=secret_key,
            region=region,
            engine_model_type=engine_model_type,
            res_text_format=args.tencent_res_text_format,
            poll_interval=args.tencent_poll_interval,
            max_polls=args.tencent_max_polls,
        )

    raise ValueError(f"暂不支持 ASR provider: {provider}")


def create_llm_provider(args):
    provider = args.llm_provider
    if provider == "mimo":
        api_key = require_value(
            args.llm_api_key or args.api_key or provider_env(LLM_PROVIDER_DEFAULTS, provider),
            "MiMo LLM 需要 --api-key、--llm-api-key 或 MIMO_API_KEY。",
        )
        base_url = args.llm_base_url or args.base_url or provider_default(LLM_PROVIDER_DEFAULTS, provider, "base_url")
        model = args.llm_model or provider_default(LLM_PROVIDER_DEFAULTS, provider, "model")
        if not api_key.startswith("tp-"):
            print("警告: MiMo Token Plan API Key 通常以 'tp-' 开头。")
        return OpenAICompatibleLLMProvider(api_key, base_url, model, provider_name="mimo")

    api_key = require_value(
        args.llm_api_key or provider_env(LLM_PROVIDER_DEFAULTS, provider),
        f"{provider} LLM 需要 --llm-api-key 或对应环境变量。",
    )
    base_url = require_value(
        args.llm_base_url or provider_default(LLM_PROVIDER_DEFAULTS, provider, "base_url"),
        f"{provider} LLM 需要 --llm-base-url。",
    )
    model = require_value(
        args.llm_model or provider_default(LLM_PROVIDER_DEFAULTS, provider, "model"),
        f"{provider} LLM 需要 --llm-model。",
    )
    return OpenAICompatibleLLMProvider(api_key, base_url, model, provider_name=provider)


def validate_provider_defaults():
    required_llm = ("base_url", "model", "api_envs")
    for provider, values in LLM_PROVIDER_DEFAULTS.items():
        if provider == "openai-compatible":
            continue
        for key in required_llm:
            if not values.get(key):
                raise AssertionError(f"LLM provider {provider} missing {key}")

    for provider in ("mimo", "aliyun-qwen"):
        values = ASR_PROVIDER_DEFAULTS[provider]
        for key in ("base_url", "model", "api_envs"):
            if not values.get(key):
                raise AssertionError(f"ASR provider {provider} missing {key}")

    stepfun = ASR_PROVIDER_DEFAULTS["stepfun"]
    for key in ("base_url", "plan_base_url", "model", "api_envs"):
        if not stepfun.get(key):
            raise AssertionError(f"ASR provider stepfun missing {key}")

    tencent = ASR_PROVIDER_DEFAULTS["tencent"]
    for key in ("engine_model_type", "region", "secret_id_envs", "secret_key_envs"):
        if not tencent.get(key):
            raise AssertionError(f"ASR provider tencent missing {key}")


def run_self_test():
    validate_provider_defaults()
    assert format_timecode(0) == "00:00"
    assert format_timecode(61) == "00:01"
    assert time_window_for_chunk(0, 3, 420) == ("00:00", "00:03")
    assert time_window_for_chunk(2, 3, 420) == ("00:06", "00:07")
    assert is_url("https://example.com/audio.mp3")
    assert is_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD")
    assert is_bilibili_url("https://b23.tv/abc123")
    assert not is_bilibili_url("https://example.com/watch?v=1")
    assert extract_bilibili_bvid("https://www.bilibili.com/video/BV1xx411c7mD?p=2") == "BV1xx411c7mD"

    transcript = (
        "[00:00-00:03]\n开场介绍。\n\n"
        "[00:03-00:06]\n讨论核心问题。\n\n"
        "[00:06-00:07]\n收尾总结。"
    )
    blocks = parse_transcript_blocks(transcript)
    assert [block["window"] for block in blocks] == [
        "00:00-00:03",
        "00:03-00:06",
        "00:06-00:07",
    ]

    class FakeLLM:
        def __init__(self):
            self.omitted_once = False

        def complete(self, messages, max_tokens):
            prompt = messages[-1]["content"]
            if "原始 ASR 转写文本：" in prompt:
                windows = re.findall(r"^- (\d{2}:\d{2}-\d{2}:\d{2})$", prompt, flags=re.MULTILINE)
                return "\n\n".join(
                    f"[{window}]\n校对后文本：{window} 内容已经补充标点、修正术语，并保持原意。"
                    for window in windows
                )

            if "逐窗口正文：" in prompt:
                if "force-bad-table" in prompt:
                    return "not a table"
                headings = re.findall(
                    r"^##\s+(\d{2}:\d{2}-\d{2}:\d{2})\s+(.+)$",
                    prompt,
                    flags=re.MULTILINE,
                )
                rows = [
                    "## 核心观点速览",
                    "",
                    "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |",
                    "|------|------|----------|------------------|",
                ]
                for window, title in headings:
                    rows.append(f"| {window} | {title} | 核心观点 | 依据正文 |")
                return "\n".join(rows)

            windows = re.findall(r"^- (\d{2}:\d{2}-\d{2}:\d{2})$", prompt, flags=re.MULTILINE)
            repair = "缺失窗口修复任务" in prompt
            if (not repair) and (not self.omitted_once) and "00:03-00:06" in windows:
                windows = [window for window in windows if window != "00:03-00:06"]
                windows.append("09:99-10:00")
                self.omitted_once = True
            return "\n\n".join(
                f"## {window} 测试主题\n\n这里概括 {window} 窗口的内容、重要性和论据。"
                for window in windows
            )

    metadata = {
        "title": "测试节目",
        "guest": "",
        "host": "",
        "series": "",
        "duration": "",
        "context_note": "",
        "terminology": "OpenAI, GitHub, Bilibili",
        "transcript_stage": "raw_asr",
    }
    calibrated = proofread_transcript(FakeLLM(), transcript, metadata, batch_size=2, min_ratio=0.1)
    assert "[00:00-00:03]" in calibrated
    assert "校对后文本" in calibrated
    assert [block["window"] for block in parse_transcript_blocks(calibrated)] == [
        "00:00-00:03",
        "00:03-00:06",
        "00:06-00:07",
    ]

    metadata["transcript_stage"] = "calibrated"
    report = generate_timeline_report(FakeLLM(), calibrated, metadata, batch_size=2, detailed=False)
    validation = validate_timeline_report(blocks, report)
    assert validation["expected_count"] == 3, validation
    assert validation["found_count"] == 3, validation
    assert not validation["missing"], validation
    assert not validation["extra"], validation
    assert not validation["duplicates"], validation
    assert validation["has_core_table"], validation
    assert "09:99-10:00" not in report
    assert "00:03-00:06 测试主题" in report

    fallback = fallback_core_table(blocks, split_report_sections(report)[0])
    assert "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |" in fallback
    assert "00:06-00:07" in fallback

    with tempfile.TemporaryDirectory(prefix="mimo_selftest_") as tmp:
        tmp_path = Path(tmp)
        prompt_root = export_ide_prompts(
            transcript,
            metadata,
            tmp_path,
            "selftest",
            batch_size=2,
            detailed=False,
            prompt_dir=tmp_path / "ide_prompts",
            transcript_path=tmp_path / "selftest_转写.txt",
        )
        assert (prompt_root / "README.md").exists()
        assert (prompt_root / "manifest.json").exists()
        assert len(list((prompt_root / "prompts").glob("*.prompt.md"))) == 2

        manual_sections = prompt_root / "sections"
        sections_by_window, _duplicates = split_report_sections(report)
        (manual_sections / "batch_001.md").write_text(
            "\n\n".join(sections_by_window[window] for window in ("00:00-00:03", "00:03-00:06")),
            encoding="utf-8",
        )
        (manual_sections / "batch_002.md").write_text(
            sections_by_window["00:06-00:07"],
            encoding="utf-8",
        )
        manual_report = generate_manual_report(transcript, metadata, manual_sections)
        manual_validation = validate_timeline_report(blocks, manual_report)
        assert manual_validation["expected_count"] == 3, manual_validation
        assert manual_validation["found_count"] == 3, manual_validation
        assert manual_validation["has_core_table"], manual_validation

    print("self-test OK")

# ============================================================
# ASR transcription
# ============================================================

def transcribe_chunk_with_retry(asr_provider, chunk_path, chunk_index, total_chunks, window_label):
    for attempt in range(MAX_RETRIES):
        try:
            print(
                f"  转写片段 {chunk_index + 1}/{total_chunks} ({window_label})...",
                end="",
                flush=True,
            )
            result = asr_provider.transcribe_chunk(chunk_path)
            print(f" 完成 ({len(result or '')} 字符)")
            return result or ""
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f" 失败: {e}")
                raise
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f" 失败，{delay}s 后重试... ({e})")
            time.sleep(delay)


def transcribe_audio(asr_provider, audio_path, temp_dir, segment_minutes, duration_seconds=None):
    if duration_seconds is None:
        duration_seconds = get_audio_duration(audio_path)
    if duration_seconds:
        print(f"音频时长: {format_duration(duration_seconds)}")

    print(f"按 {segment_minutes} 分钟/段分片...")
    chunks = chunk_audio(audio_path, temp_dir, segment_minutes)
    print(f"共 {len(chunks)} 个片段")

    transcript_blocks = []
    for i, chunk in enumerate(chunks):
        start_label, end_label = time_window_for_chunk(i, segment_minutes, duration_seconds)
        window_label = f"{start_label}-{end_label}"
        transcript = transcribe_chunk_with_retry(asr_provider, chunk, i, len(chunks), window_label)
        transcript = transcript.strip() or "（此窗口未返回可用转写文本。）"
        transcript_blocks.append(f"[{window_label}]\n{transcript}")

    full_transcript = "\n\n".join(transcript_blocks)
    print(f"\n转写完成，总字数: {len(full_transcript)} 字符")
    return full_transcript


# ============================================================
# Transcript and report validation
# ============================================================

def parse_transcript_blocks(transcript):
    matches = list(WINDOW_RE.finditer(transcript or ""))
    blocks = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(transcript)
        text = transcript[start:end].strip()
        blocks.append({"window": match.group(1), "text": text})
    return blocks


def blocks_to_transcript(blocks):
    return "\n\n".join(f"[{block['window']}]\n{block['text'].strip()}" for block in blocks)


def count_transcript_windows(transcript):
    return len(parse_transcript_blocks(transcript))


def extract_time_sections(markdown):
    return SECTION_HEADING_RE.findall(markdown or "")


def split_report_sections(markdown):
    sections = {}
    duplicates = []
    for match in SECTION_RE.finditer(markdown or ""):
        window = match.group(1)
        section = match.group(0).strip()
        if window in sections:
            duplicates.append(window)
            continue
        sections[window] = section
    return sections, duplicates


def validate_timeline_report(transcript_or_blocks, report):
    blocks = (
        parse_transcript_blocks(transcript_or_blocks)
        if isinstance(transcript_or_blocks, str)
        else transcript_or_blocks
    )
    expected = [block["window"] for block in blocks]
    found = extract_time_sections(report)
    found_set = set(found)
    expected_set = set(expected)
    duplicates = sorted({window for window in found if found.count(window) > 1})
    has_core_table = (
        re.search(r"^##\s+核心观点速览\b", report or "", flags=re.MULTILINE) is not None
        and "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |" in (report or "")
    )
    return {
        "expected_count": len(expected),
        "found_count": len(found),
        "missing": [window for window in expected if window not in found_set],
        "extra": [window for window in found if window not in expected_set],
        "duplicates": duplicates,
        "has_core_table": has_core_table,
    }


def validate_section_map(blocks, sections_by_window):
    expected = [block["window"] for block in blocks]
    found = set(sections_by_window)
    return {
        "expected_count": len(expected),
        "found_count": len(found),
        "missing": [window for window in expected if window not in found],
        "extra": [window for window in found if window not in set(expected)],
    }


def section_title(section):
    first_line = (section or "").splitlines()[0] if section else ""
    match = re.match(r"^##\s+\d{2}:\d{2}-\d{2}:\d{2}\s+(.+)$", first_line)
    return (match.group(1).strip() if match else "窗口摘要").replace("|", " ")


def section_first_claim(section):
    for line in (section or "").splitlines()[1:]:
        line = line.strip()
        if not line or line.startswith(">") or line.startswith("#"):
            continue
        return line.replace("|", " ")[:80]
    return "该窗口内容较少或转写质量有限。"


def fallback_core_table(blocks, sections_by_window):
    rows = [
        "## 核心观点速览",
        "",
        "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |",
        "|------|------|----------|------------------|",
    ]
    for block in blocks:
        window = block["window"]
        section = sections_by_window.get(window, "")
        rows.append(
            f"| {window} | {section_title(section)} | {section_first_claim(section)} | 依据该时间窗口转写整理 |"
        )
    return "\n".join(rows)


# ============================================================
# Report prompts
# ============================================================

def resolve_terminology(args):
    values = []
    if getattr(args, "terminology_file", None):
        path = Path(args.terminology_file)
        if not path.exists():
            raise FileNotFoundError(f"terminology file does not exist: {path}")
        values.append(path.read_text(encoding="utf-8").strip())
    for value in getattr(args, "terminology", None) or []:
        if value:
            values.append(value.strip())
    return "\n".join(value for value in values if value)


def build_metadata(args, base_name, duration_seconds):
    return {
        "title": args.title.strip() if args.title else base_name,
        "guest": args.guest.strip() if args.guest else "",
        "host": args.host.strip() if args.host else "",
        "series": args.series.strip() if args.series else "",
        "duration": format_duration(duration_seconds) or "",
        "context_note": args.context_note.strip() if args.context_note else "",
        "terminology": resolve_terminology(args),
        "transcript_stage": "raw_asr",
    }


def metadata_for_prompt(metadata):
    labels = {
        "title": "标题",
        "guest": "嘉宾",
        "host": "主播",
        "series": "系列",
        "duration": "时长",
        "context_note": "补充说明",
        "terminology": "术语/专有名词参考",
    }
    lines = []
    for key, label in labels.items():
        value = metadata.get(key, "")
        if value:
            lines.append(f"- {label}: {value}")
    return "\n".join(lines) or "- 无额外元信息；只使用文件名、音频时长和转写内容。"


def build_report_header(metadata):
    title = metadata.get("title") or "播客时间线摘要"
    lines = [f"# {title}", ""]

    for key, label in (("guest", "嘉宾"), ("host", "主播"), ("series", "系列"), ("duration", "时长")):
        value = metadata.get(key, "")
        if value:
            lines.append(f"> **{label}**：{value}")
    if metadata.get("context_note"):
        lines.append(f"> **补充说明**：{metadata['context_note']}")
    if len(lines) > 2:
        lines.append("")

    note = (
        "> **转写说明**：本文基于 ASR 分片转写稿经 LLM 校对后整理。"
        "时间点来自分片窗口，非逐句时间戳；校对阶段仅修正标点、断句、明显错别字和专有名词，不做内容压缩。"
    )
    if metadata.get("transcript_stage") == "inline_proofread":
        note = (
            "> **转写说明**：本文基于 ASR 分片转写稿整理，摘要生成时在窗口内部完成 LLM 校对。"
            "时间点来自分片窗口，非逐句时间戳；内联模式不单独生成校对稿。"
        )
    elif metadata.get("transcript_stage") != "calibrated":
        note = (
            "> **转写说明**：本文基于 ASR 分片转写稿整理。"
            "时间点来自分片窗口，非逐句时间戳；正文按每个 transcript 窗口逐段生成并校验，尽量保留原意并对明显转写错误做轻度校正。"
        )

    lines.extend(
        [
            note,
            "",
            "---",
            "",
        ]
    )
    return "\n".join(lines)


def build_proofread_batch_prompt(blocks, metadata, repair=False):
    required_windows = "\n".join(f"- {block['window']}" for block in blocks)
    repair_note = "这是校对缺失窗口修复任务，只输出下面列出的窗口。" if repair else ""

    return f"""请校对以下带时间窗口的 ASR 转写文本，输出校对后的带窗口 transcript。

节目元信息和术语参考（只用于修正专有名词，不要编造内容）：
{metadata_for_prompt(metadata)}

{repair_note}

必须输出的窗口：
{required_windows}

硬性要求：
1. 输出必须保持 `[HH:MM-HH:MM]` 窗口格式，每个窗口一段。
2. 必须严格输出 {len(blocks)} 个窗口，窗口标签必须与“必须输出的窗口”完全一致。
3. 不得合并窗口、跳过窗口、拆分窗口、调换顺序，或新增未列出的窗口。
4. 只能校对窗口内文本：补标点、合理断句、修正明显错别字、英文术语、人名、公司名和 ASR 误识别。
5. 不要总结、不要压缩、不要改写观点、不要新增事实、不要删除实质内容。
6. 多人对话混乱时，只能在文本内部轻度整理称呼和断句；不要凭空添加说话人。
7. 不确定的专有名词保守处理；有术语参考时优先使用参考中的正确写法。
8. 只返回校对后的 transcript，不要解释。

原始 ASR 转写文本：
{blocks_to_transcript(blocks)}
"""


def build_timeline_batch_prompt(blocks, metadata, detailed=False, repair=False, inline_proofread=False):
    required_windows = "\n".join(f"- {block['window']}" for block in blocks)
    detail_instruction = (
        "每节写 2-4 个自然段；如果信息密度高，可写到 5 段。"
        if detailed
        else "每节写 1-3 个自然段。"
    )
    repair_note = "这是缺失窗口修复任务，只输出下面列出的窗口章节。" if repair else ""
    proofread_instruction = (
        "8. 先在每个窗口内部完成校对：修正标点、断句、明显错别字和专有名词；"
        "再基于校对后的含义写摘要，但不要在输出中展示完整校对稿。"
        if inline_proofread
        else "8. 直接基于输入文本生成摘要，不要输出完整 transcript。"
    )

    return f"""请基于以下带时间窗口的 ASR 转写文本，生成逐窗口播客深度解读章节。

节目元信息（只作为背景，不要编造缺失项）：
{metadata_for_prompt(metadata)}

{repair_note}

必须输出的窗口：
{required_windows}

硬性要求：
1. 只输出时间章节正文，不要输出 H1 标题、元信息 blockquote、转写说明或核心观点速览表。
2. 必须严格生成 {len(blocks)} 个二级章节。
3. 每个章节标题必须使用 `## HH:MM-HH:MM 主题`，且 `HH:MM-HH:MM` 必须与“必须输出的窗口”完全一致。
4. 不得合并相邻窗口；不得跳过窗口；不得新增未列出的时间窗口。
5. 如果某个窗口内容很少、噪声多或识别失败，也必须生成对应章节，并说明该窗口限制。
6. 每节概括这一窗口讲了什么、为什么重要、使用了什么例子或论据。{detail_instruction}
7. 只在转写文本支持时使用短引用；不能确定原话时改为转述。
{proofread_instruction}

转写文本：
{blocks_to_transcript(blocks)}
"""


def build_timeline_prompt(transcript, metadata, detailed=False):
    blocks = parse_transcript_blocks(transcript)
    return build_timeline_batch_prompt(blocks, metadata, detailed=detailed)


def build_final_table_prompt(body, metadata):
    return f"""请基于以下已经生成的逐窗口播客解读正文，输出最终的 `## 核心观点速览` 表格。

节目元信息：
{metadata_for_prompt(metadata)}

硬性要求：
1. 只输出 `## 核心观点速览` 和紧随其后的 Markdown 表格，不要输出其他正文。
2. 表头必须完全是：
| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |
|------|------|----------|------------------|
3. 每个 `## HH:MM-HH:MM 主题` 章节对应一行。
4. 时间列必须使用完整窗口，例如 `00:00-00:03`。
5. 核心观点用一句话压缩；关键论据 / 金句只使用正文或转写中支持的信息。

逐窗口正文：
{body}
"""


def build_brief_prompt(transcript, metadata, detailed=False):
    detail_instruction = ""
    if detailed:
        detail_instruction = (
            "请生成深度分析版报告，每个主题展开 300-500 字，"
            "包含核心观点、论证过程、具体数据和案例、嘉宾独特视角四个维度。"
        )

    return f"""请基于以下音频/播客转写文本，生成一份结构化总结报告。

节目元信息：
{metadata_for_prompt(metadata)}

{detail_instruction}

报告结构：
1. **内容摘要**（200-500字）：完整覆盖讨论脉络和核心结论
2. **关键主题深度分析**（每个主题 300-500 字）：包含核心观点、论证过程、数据和案例
3. **核心洞察**（5-7 条）：每条附支撑论据和投资/实践启示
4. **内容时间线**（10-13 个节点）：每个节点带 2-3 句要点说明
5. **精彩引用**（4-7 条）：每条附点评
6. **行动建议**（3 条）：可执行的具体建议
7. **关键词标签**：3-5 个核心关键词

转写文本：
{transcript}
"""


def llm_system_message(report_style):
    if report_style == "proofread":
        return (
            "你是一位专业中文 ASR 转写校对编辑。你只修正标点、断句、错别字、"
            "英文术语、人名和公司名；必须保留原意、事实、数字和时间窗口。"
        )
    if report_style == "brief":
        return "你是一位专业中文播客编辑，擅长生成结构化摘要和可执行洞察。"
    return (
        "你是一位专业中文播客编辑，擅长根据带时间窗口的转写稿生成"
        "可读、可追溯、观点密度高的 Markdown 时间线摘要。"
    )


def complete_with_retry(llm_provider, messages, max_tokens, label):
    for attempt in range(MAX_RETRIES):
        try:
            print(f"{label}...", end="", flush=True)
            text = llm_provider.complete(messages, max_tokens=max_tokens)
            print(f" 完成 ({len(text)} 字符)")
            return text
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                print(f" 失败: {e}")
                raise
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f" 失败，{delay}s 后重试... ({e})")
            time.sleep(delay)


def clean_llm_transcript_output(output):
    text = (output or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def collect_proofread_blocks(output, expected_windows):
    blocks = parse_transcript_blocks(clean_llm_transcript_output(output))
    expected_set = set(expected_windows)
    collected = {}
    duplicates = []
    for block in blocks:
        window = block["window"]
        if window in collected:
            duplicates.append(window)
            continue
        if window in expected_set:
            collected[window] = block["text"].strip()
    extras = [block["window"] for block in blocks if block["window"] not in expected_set]
    return collected, duplicates, extras


def proofread_candidate_ok(original_text, candidate_text, min_ratio):
    original = (original_text or "").strip()
    candidate = (candidate_text or "").strip()
    if not candidate:
        return False
    if re.search(r"^##\s+", candidate, flags=re.MULTILINE):
        return False
    original_len = len(original)
    if original_len >= 80 and len(candidate) < original_len * min_ratio:
        return False
    return True


def generate_proofread_batch(llm_provider, blocks, metadata, min_ratio, repair=False, label="校对转写"):
    prompt = build_proofread_batch_prompt(blocks, metadata, repair=repair)
    messages = [
        {"role": "system", "content": llm_system_message("proofread")},
        {"role": "user", "content": prompt},
    ]
    output = complete_with_retry(
        llm_provider,
        messages,
        max_tokens=LLM_MAX_TOKENS_PROOFREAD_BATCH,
        label=label,
    )
    collected, duplicates, extras = collect_proofread_blocks(
        output,
        [block["window"] for block in blocks],
    )
    invalid = [
        block["window"]
        for block in blocks
        if block["window"] in collected
        and not proofread_candidate_ok(block["text"], collected[block["window"]], min_ratio)
    ]
    for window in invalid:
        collected.pop(window, None)
    return collected, duplicates, extras, invalid


def proofread_blocks_with_repair(llm_provider, blocks, metadata, min_ratio, label="校对转写"):
    """Proofread one independent block group, repairing or falling back per window."""
    collected, duplicates, extras, invalid = generate_proofread_batch(
        llm_provider,
        blocks,
        metadata,
        min_ratio=min_ratio,
        repair=False,
        label=label,
    )
    if duplicates:
        print(f"  警告: {label} 输出重复窗口，已保留首次出现: {', '.join(duplicates)}")
    if extras:
        print(f"  警告: {label} 输出额外窗口，已忽略: {', '.join(extras)}")
    if invalid:
        print(f"  警告: {label} 输出过短或格式异常，将逐窗口修复: {', '.join(invalid)}")

    blocks_by_window = {block["window"]: block for block in blocks}
    repair_windows = [
        block["window"]
        for block in blocks
        if block["window"] not in collected
    ]
    for window in repair_windows:
        repaired, repair_duplicates, repair_extras, repair_invalid = generate_proofread_batch(
            llm_provider,
            [blocks_by_window[window]],
            metadata,
            min_ratio=min_ratio,
            repair=True,
            label=f"{label} 修复 {window}",
        )
        if repair_duplicates:
            print(f"  警告: 修复窗口 {window} 输出重复窗口: {', '.join(repair_duplicates)}")
        if repair_extras:
            print(f"  警告: 修复窗口 {window} 输出额外窗口，已忽略: {', '.join(repair_extras)}")
        if window in repaired and window not in repair_invalid:
            collected[window] = repaired[window]

    final_blocks = []
    fallback_windows = []
    for block in blocks:
        window = block["window"]
        candidate = collected.get(window, "")
        if not proofread_candidate_ok(block["text"], candidate, min_ratio):
            fallback_windows.append(window)
            candidate = block["text"]
        final_blocks.append({"window": window, "text": candidate.strip() or block["text"].strip()})

    if fallback_windows:
        print("警告: 以下窗口校对失败，已保留原始 ASR 文本: " + ", ".join(fallback_windows))
    return final_blocks


def proofread_transcript(
    llm_provider,
    transcript,
    metadata,
    batch_size=DEFAULT_PROOFREAD_BATCH_SIZE,
    min_ratio=DEFAULT_PROOFREAD_MIN_RATIO,
    concurrency=1,
):
    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("校对需要带 `[HH:MM-HH:MM]` 的 transcript。")

    print(f"检测到 {len(blocks)} 个 transcript 窗口；按每批 {batch_size} 个窗口校对。")
    batches = list(chunk_list(blocks, batch_size))
    total_batches = len(batches)

    def proofread_batch(job):
        batch_index, batch = job
        first_window = batch[0]["window"]
        last_window = batch[-1]["window"]
        return proofread_blocks_with_repair(
            llm_provider,
            batch,
            metadata,
            min_ratio=min_ratio,
            label=f"校对转写批次 {batch_index}/{total_batches} ({first_window} 到 {last_window})",
        )

    jobs = list(enumerate(batches, start=1))
    batch_results = ordered_parallel_map(proofread_batch, jobs, max_workers=concurrency)
    final_blocks = [block for batch in batch_results for block in batch]

    calibrated = blocks_to_transcript(final_blocks)
    expected_windows = [block["window"] for block in blocks]
    final_windows = [block["window"] for block in parse_transcript_blocks(calibrated)]
    if final_windows != expected_windows:
        raise RuntimeError("校对后 transcript 窗口校验失败。")

    print(f"校对完成: {len(blocks)} 个窗口，输出 {len(calibrated)} 字符。")
    return calibrated


def generate_brief_report(llm_provider, transcript, metadata, detailed=False):
    prompt = build_brief_prompt(transcript, metadata, detailed)
    messages = [
        {"role": "system", "content": llm_system_message("brief")},
        {"role": "user", "content": prompt},
    ]
    return complete_with_retry(
        llm_provider,
        messages,
        max_tokens=LLM_MAX_TOKENS_STANDARD if not detailed else LLM_MAX_TOKENS_TIMELINE_BATCH,
        label="生成 brief 报告",
    )


def collect_sections_from_output(output, expected_windows):
    sections, duplicates = split_report_sections(output)
    expected_set = set(expected_windows)
    collected = {
        window: section
        for window, section in sections.items()
        if window in expected_set
    }
    extras = [window for window in sections if window not in expected_set]
    return collected, duplicates, extras


def generate_timeline_batch(
    llm_provider,
    blocks,
    metadata,
    detailed=False,
    repair=False,
    label="生成时间章节",
    inline_proofread=False,
):
    prompt = build_timeline_batch_prompt(
        blocks,
        metadata,
        detailed=detailed,
        repair=repair,
        inline_proofread=inline_proofread,
    )
    messages = [
        {"role": "system", "content": llm_system_message("timeline")},
        {"role": "user", "content": prompt},
    ]
    output = complete_with_retry(
        llm_provider,
        messages,
        max_tokens=LLM_MAX_TOKENS_TIMELINE_BATCH,
        label=label,
    )
    return collect_sections_from_output(output, [block["window"] for block in blocks])


def repair_missing_sections(
    llm_provider,
    missing_windows,
    blocks_by_window,
    metadata,
    detailed=False,
    inline_proofread=False,
):
    repaired = {}
    for window in missing_windows:
        block = blocks_by_window[window]
        sections, duplicates, extras = generate_timeline_batch(
            llm_provider,
            [block],
            metadata,
            detailed=detailed,
            repair=True,
            label=f"修复缺失窗口 {window}",
            inline_proofread=inline_proofread,
        )
        if duplicates:
            print(f"  警告: 修复窗口 {window} 输出重复章节: {', '.join(duplicates)}")
        if extras:
            print(f"  警告: 修复窗口 {window} 输出额外章节，已忽略: {', '.join(extras)}")
        if window in sections:
            repaired[window] = sections[window]
    return repaired


def generate_timeline_sections(
    llm_provider,
    blocks,
    metadata,
    batch_size,
    detailed=False,
    concurrency=1,
    inline_proofread=False,
):
    sections_by_window = {}
    batches = list(chunk_list(blocks, batch_size))
    total_batches = len(batches)

    def generate_batch(job):
        batch_index, batch = job
        first_window = batch[0]["window"]
        last_window = batch[-1]["window"]
        sections, duplicates, extras = generate_timeline_batch(
            llm_provider,
            batch,
            metadata,
            detailed=detailed,
            repair=False,
            label=f"生成时间章节批次 {batch_index}/{total_batches} ({first_window} 到 {last_window})",
            inline_proofread=inline_proofread,
        )
        if duplicates:
            print(f"  警告: 批次 {batch_index} 输出重复章节，已保留首次出现: {', '.join(duplicates)}")
        if extras:
            print(f"  警告: 批次 {batch_index} 输出额外章节，已忽略: {', '.join(extras)}")
        return sections

    jobs = list(enumerate(batches, start=1))
    batch_results = ordered_parallel_map(generate_batch, jobs, max_workers=concurrency)
    for sections in batch_results:
        sections_by_window.update(sections)

    validation = validate_section_map(blocks, sections_by_window)
    if validation["missing"]:
        print(f"发现缺失窗口 {len(validation['missing'])} 个，开始只重跑缺失窗口。")
        blocks_by_window = {block["window"]: block for block in blocks}
        repaired = repair_missing_sections(
            llm_provider,
            validation["missing"],
            blocks_by_window,
            metadata,
            detailed=detailed,
            inline_proofread=inline_proofread,
        )
        sections_by_window.update(repaired)

    final_validation = validate_section_map(blocks, sections_by_window)
    if final_validation["missing"]:
        raise RuntimeError(
            "报告章节校验失败，仍缺失窗口: "
            + ", ".join(final_validation["missing"])
        )

    ordered_sections = [sections_by_window[block["window"]].strip() for block in blocks]
    return "\n\n".join(ordered_sections), sections_by_window


def generate_core_table(llm_provider, body, blocks, sections_by_window, metadata):
    prompt = build_final_table_prompt(body, metadata)
    messages = [
        {"role": "system", "content": llm_system_message("timeline")},
        {"role": "user", "content": prompt},
    ]
    table = complete_with_retry(
        llm_provider,
        messages,
        max_tokens=LLM_MAX_TOKENS_FINAL_TABLE,
        label="生成核心观点速览表",
    ).strip()

    if (
        re.search(r"^##\s+核心观点速览\b", table, flags=re.MULTILINE) is None
        or "| 时间 | 章节 | 核心观点 | 关键论据 / 金句 |" not in table
    ):
        print("警告: LLM 未返回合格的核心观点表，改用本地兜底表格。")
        return fallback_core_table(blocks, sections_by_window)
    return table


def build_timeline_report_from_sections(llm_provider, blocks, sections_by_window, metadata):
    section_validation = validate_section_map(blocks, sections_by_window)
    if section_validation["missing"]:
        raise RuntimeError(
            "报告章节校验失败，仍缺失窗口: "
            + ", ".join(section_validation["missing"])
        )

    body = "\n\n".join(
        sections_by_window[block["window"]].strip()
        for block in blocks
    )
    table = generate_core_table(llm_provider, body, blocks, sections_by_window, metadata)
    report = "\n".join([build_report_header(metadata).rstrip(), body.rstrip(), "", table.rstrip(), ""])

    validation = validate_timeline_report(blocks, report)
    if validation["missing"] or validation["extra"] or validation["duplicates"] or not validation["has_core_table"]:
        details = []
        if validation["missing"]:
            details.append("缺失窗口: " + ", ".join(validation["missing"]))
        if validation["extra"]:
            details.append("额外窗口: " + ", ".join(validation["extra"]))
        if validation["duplicates"]:
            details.append("重复窗口: " + ", ".join(validation["duplicates"]))
        if not validation["has_core_table"]:
            details.append("缺少核心观点速览表")
        raise RuntimeError("报告校验失败: " + "；".join(details))

    print(
        f"报告校验通过: transcript 窗口 {validation['expected_count']} 个，"
        f"报告时间章节 {validation['found_count']} 个。"
    )
    return report


def generate_timeline_report(
    llm_provider,
    transcript,
    metadata,
    batch_size,
    detailed=False,
    concurrency=1,
    inline_proofread=False,
):
    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("timeline 报告需要带 `[HH:MM-HH:MM]` 的 transcript。")

    print(f"检测到 {len(blocks)} 个 transcript 窗口；按每批 {batch_size} 个窗口生成。")
    _body, sections_by_window = generate_timeline_sections(
        llm_provider,
        blocks,
        metadata,
        batch_size=batch_size,
        detailed=detailed,
        concurrency=concurrency,
        inline_proofread=inline_proofread,
    )
    return build_timeline_report_from_sections(
        llm_provider,
        blocks,
        sections_by_window,
        metadata,
    )


def generate_timeline_outputs(
    llm_provider,
    transcript,
    metadata,
    proofread_mode,
    proofread_batch_size,
    proofread_min_ratio,
    timeline_batch_size,
    detailed=False,
    concurrency=1,
):
    """Generate timeline outputs using separate pipelined, inline, or skip mode."""
    if proofread_mode not in {"separate", "inline", "skip"}:
        raise ValueError(f"不支持的校对模式: {proofread_mode}")

    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("timeline 报告需要带 `[HH:MM-HH:MM]` 的 transcript。")

    report_metadata = dict(metadata)
    if proofread_mode != "separate":
        if proofread_mode == "inline":
            report_metadata["transcript_stage"] = "inline_proofread"
        elif report_metadata.get("transcript_stage") != "calibrated":
            report_metadata["transcript_stage"] = "raw_asr"
        report = generate_timeline_report(
            llm_provider,
            transcript,
            report_metadata,
            batch_size=timeline_batch_size,
            detailed=detailed,
            concurrency=concurrency,
            inline_proofread=(proofread_mode == "inline"),
        )
        return None, report

    report_metadata["transcript_stage"] = "calibrated"
    timeline_batches = list(chunk_list(blocks, timeline_batch_size))
    total_batches = len(timeline_batches)
    print(
        f"检测到 {len(blocks)} 个 transcript 窗口；"
        f"启动校对→摘要流水线，每批 {timeline_batch_size} 个窗口，并发 {min(concurrency, total_batches)}。"
    )

    def generate_pipeline_batch(job):
        batch_index, batch = job
        calibrated_batch = []
        proofread_batches = list(chunk_list(batch, proofread_batch_size))
        for proofread_index, proofread_batch in enumerate(proofread_batches, start=1):
            calibrated_batch.extend(
                proofread_blocks_with_repair(
                    llm_provider,
                    proofread_batch,
                    report_metadata,
                    min_ratio=proofread_min_ratio,
                    label=(
                        f"流水线批次 {batch_index}/{total_batches} 校对 "
                        f"{proofread_index}/{len(proofread_batches)}"
                    ),
                )
            )

        first_window = calibrated_batch[0]["window"]
        last_window = calibrated_batch[-1]["window"]
        sections, duplicates, extras = generate_timeline_batch(
            llm_provider,
            calibrated_batch,
            report_metadata,
            detailed=detailed,
            repair=False,
            label=(
                f"流水线批次 {batch_index}/{total_batches} 生成时间章节 "
                f"({first_window} 到 {last_window})"
            ),
        )
        if duplicates:
            print(f"  警告: 流水线批次 {batch_index} 输出重复章节，已保留首次出现: {', '.join(duplicates)}")
        if extras:
            print(f"  警告: 流水线批次 {batch_index} 输出额外章节，已忽略: {', '.join(extras)}")

        validation = validate_section_map(calibrated_batch, sections)
        if validation["missing"]:
            blocks_by_window = {block["window"]: block for block in calibrated_batch}
            sections.update(
                repair_missing_sections(
                    llm_provider,
                    validation["missing"],
                    blocks_by_window,
                    report_metadata,
                    detailed=detailed,
                )
            )
        final_validation = validate_section_map(calibrated_batch, sections)
        if final_validation["missing"]:
            raise RuntimeError(
                "报告章节校验失败，仍缺失窗口: "
                + ", ".join(final_validation["missing"])
            )
        return calibrated_batch, sections

    jobs = list(enumerate(timeline_batches, start=1))
    pipeline_results = ordered_parallel_map(
        generate_pipeline_batch,
        jobs,
        max_workers=concurrency,
    )
    calibrated_blocks = []
    sections_by_window = {}
    for calibrated_batch, sections in pipeline_results:
        calibrated_blocks.extend(calibrated_batch)
        sections_by_window.update(sections)

    expected_windows = [block["window"] for block in blocks]
    calibrated_windows = [block["window"] for block in calibrated_blocks]
    if calibrated_windows != expected_windows:
        raise RuntimeError("校对后 transcript 窗口校验失败。")

    calibrated_transcript = blocks_to_transcript(calibrated_blocks)
    report = build_timeline_report_from_sections(
        llm_provider,
        calibrated_blocks,
        sections_by_window,
        report_metadata,
    )
    return calibrated_transcript, report


def generate_report(llm_provider, transcript, metadata, report_style="timeline", detailed=False, batch_size=DEFAULT_TIMELINE_BATCH_SIZE, concurrency=1):
    if report_style == "brief":
        return generate_brief_report(llm_provider, transcript, metadata, detailed=detailed)
    return generate_timeline_report(
        llm_provider,
        transcript,
        metadata,
        batch_size=batch_size,
        detailed=detailed,
        concurrency=concurrency,
    )


# ============================================================
# IDE/manual summary workflow
# ============================================================

def prompt_filename(index, batch):
    first_window = batch[0]["window"].replace(":", "-")
    last_window = batch[-1]["window"].replace(":", "-")
    return f"batch_{index:03d}_{first_window}_{last_window}.prompt.md"


def section_filename(index, batch):
    first_window = batch[0]["window"].replace(":", "-")
    last_window = batch[-1]["window"].replace(":", "-")
    return f"batch_{index:03d}_{first_window}_{last_window}.md"


def export_ide_prompts(
    transcript,
    metadata,
    output_dir,
    base_name,
    batch_size,
    detailed=False,
    prompt_dir=None,
    transcript_path=None,
):
    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("导出 IDE prompts 需要带 `[HH:MM-HH:MM]` 的 transcript。")

    root = Path(prompt_dir) if prompt_dir else Path(output_dir) / f"{base_name}_ide_prompts"
    prompts_dir = root / "prompts"
    sections_dir = root / "sections"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(parents=True, exist_ok=True)

    batches = list(chunk_list(blocks, batch_size))
    manifest = {
        "version": 1,
        "base_name": base_name,
        "batch_size": batch_size,
        "window_count": len(blocks),
        "transcript_input": str(transcript_path) if transcript_path else None,
        "batches": [],
    }

    for index, batch in enumerate(batches, start=1):
        prompt_name = prompt_filename(index, batch)
        section_name = section_filename(index, batch)
        prompt_text = build_timeline_batch_prompt(
            batch,
            metadata,
            detailed=detailed,
            repair=False,
            inline_proofread=True,
        )
        full_prompt = (
            "# IDE Timeline Batch Prompt\n\n"
            f"- Batch: {index}/{len(batches)}\n"
            f"- Required output file: `sections/{section_name}`\n"
            "- Paste the prompt below into the current IDE model.\n"
            "- First proofread each ASR window internally, then summarize from the proofread meaning.\n"
            "- Save only the model's Markdown section output into the required output file.\n"
            "- Do not add H1 title, metadata, transcription note, or core table.\n\n"
            "---\n\n"
            f"{prompt_text}"
        )
        (prompts_dir / prompt_name).write_text(full_prompt, encoding="utf-8")
        manifest["batches"].append({
            "index": index,
            "windows": [block["window"] for block in batch],
            "prompt": f"prompts/{prompt_name}",
            "section_output": f"sections/{section_name}",
        })

    merge_transcript = str(transcript_path) if transcript_path else f"{base_name}_转写.txt"
    readme = f"""# IDE Manual Summary Workflow

This directory contains batched prompts for using the current IDE model as the summarizer.

## Steps

1. Open each file in `prompts/`.
2. Paste the prompt into the current IDE model. The prompt requires the model to proofread each ASR window internally before summarizing.
3. Save the model output to the matching file path under `sections/`.
4. Merge and validate the final report with:

```bash
python scripts/mimo_podcast_tool.py --transcript-input "{merge_transcript}" --manual-sections-dir "{sections_dir}" --output-dir "{output_dir}"
```

## Contract

- Each prompt lists exact required windows.
- Each prompt must proofread ASR text inside each window before producing the section summary.
- Each output file must contain only `## HH:MM-HH:MM 主题` sections.
- Do not merge, skip, or invent windows.
- The script will ignore extra windows, reject missing windows, add the report header, add a fallback core table, and validate before writing.
"""
    (root / "README.md").write_text(readme, encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def load_manual_sections(sections_dir, expected_windows):
    sections_dir = Path(sections_dir)
    if not sections_dir.exists():
        raise FileNotFoundError(f"manual sections directory does not exist: {sections_dir}")

    files = sorted(
        path for path in sections_dir.glob("*.md")
        if not path.name.lower().endswith(".prompt.md")
    )
    if not files:
        raise FileNotFoundError(f"manual sections directory has no .md outputs: {sections_dir}")

    combined = "\n\n".join(path.read_text(encoding="utf-8") for path in files)
    sections_by_window, duplicates = split_report_sections(combined)
    expected_set = set(expected_windows)
    extras = [window for window in sections_by_window if window not in expected_set]
    for window in extras:
        sections_by_window.pop(window, None)
    return sections_by_window, duplicates, extras, files


def generate_manual_report(transcript, metadata, sections_dir):
    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("manual merge 需要带 `[HH:MM-HH:MM]` 的 transcript。")

    expected_windows = [block["window"] for block in blocks]
    sections_by_window, duplicates, extras, files = load_manual_sections(sections_dir, expected_windows)
    if duplicates:
        raise RuntimeError("手动章节输出包含重复窗口: " + ", ".join(duplicates))
    if extras:
        print("警告: 手动章节输出包含 transcript 不存在的窗口，已忽略: " + ", ".join(extras))

    validation = validate_section_map(blocks, sections_by_window)
    if validation["missing"]:
        raise RuntimeError(
            "手动章节输出缺失窗口: "
            + ", ".join(validation["missing"])
            + f"。请补齐后重新运行。已读取 {len(files)} 个文件。"
        )

    body = "\n\n".join(sections_by_window[block["window"]].strip() for block in blocks)
    table = fallback_core_table(blocks, sections_by_window)
    report = "\n".join([build_report_header(metadata).rstrip(), body.rstrip(), "", table.rstrip(), ""])

    final_validation = validate_timeline_report(blocks, report)
    if final_validation["missing"] or final_validation["extra"] or final_validation["duplicates"] or not final_validation["has_core_table"]:
        raise RuntimeError(f"手动报告校验失败: {final_validation}")

    print(
        f"手动报告校验通过: transcript 窗口 {final_validation['expected_count']} 个，"
        f"报告时间章节 {final_validation['found_count']} 个。"
    )
    return report


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="音频转写与时间线播客摘要工具（ASR API 必需或使用已有 transcript；LLM API 可选）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # MiMo ASR 转写，后续由当前 IDE/Agent 模型总结
  python mimo_podcast_tool.py podcast.mp3 --transcribe-only --api-key "tp-xxxx"

  # 阿里 Qwen ASR 转写，后续由当前 IDE/Agent 模型总结
  python mimo_podcast_tool.py podcast.mp3 --transcribe-only --asr-provider aliyun-qwen --asr-api-key "sk-..."

  # 阶跃星辰 Step Plan ASR 转写（订阅额度使用专属 /step_plan/v1 路径）
  python mimo_podcast_tool.py podcast.mp3 --transcribe-only --asr-provider stepfun --stepfun-plan --asr-api-key "..."

  # B站 URL：优先用 BBDown 下载音频；受限内容可提供 B站 cookie
  python mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-..." --bilibili-cookie "SESSDATA=..."

  # 已有 transcript，合并 Agent 生成的章节
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --manual-sections-dir podcast_agent_sections

  # 明确使用 API LLM 总结：默认先 LLM 校对 transcript，再生成报告
  python mimo_podcast_tool.py podcast.mp3 --asr-provider mimo --api-key "tp-xxxx" --llm-provider kimi --llm-api-key "sk-..."
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --llm-provider openai-compatible --llm-base-url "https://..." --llm-model "model" --llm-api-key "sk-..."

  # 只生成校对稿，不生成总结报告
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --proofread-only --llm-provider kimi --llm-api-key "sk-..."

  # 手动 fallback：导出 prompts 后再合并 sections
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --export-ide-prompts
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --manual-sections-dir podcast_ide_prompts/sections
        """,
    )
    parser.add_argument("input", nargs="?", help="音频/视频文件路径或 URL；使用 --transcript-input 时可省略")
    parser.add_argument("--self-test", action="store_true", help="运行本地纯函数自检，不调用任何外部 API")
    parser.add_argument(
        "--transcribe-only",
        action="store_true",
        help="只转写并保存带时间窗口 transcript，不调用 LLM 生成报告",
    )
    parser.add_argument(
        "--proofread-only",
        action="store_true",
        help="只用 LLM 校对带时间窗口 transcript 并保存 `_校对.txt`，不生成总结报告",
    )
    parser.add_argument(
        "--no-proofread",
        action="store_true",
        help="兼容参数，等价于 --proofread-mode skip",
    )
    parser.add_argument(
        "--proofread-mode",
        choices=["separate", "inline", "skip"],
        help=(
            "校对模式：separate=分批校对后立即摘要并保存校对稿；"
            "inline=在摘要调用内校对且不保存校对稿；skip=跳过校对。"
            "默认对原始稿使用 separate，对 `_校对`/`_calibrated` 输入使用 skip"
        ),
    )
    parser.add_argument(
        "--transcript-input",
        help="读取已有带 `[HH:MM-HH:MM]` 窗口的转写文本并跳过 ASR",
    )
    parser.add_argument(
        "--export-ide-prompts",
        action="store_true",
        help="导出逐窗口分批 prompts，供当前 IDE 模型生成章节；不调用 LLM API",
    )
    parser.add_argument(
        "--ide-prompts-dir",
        help="导出 IDE prompts 的目录；默认写入 output-dir 下的 `{base_name}_ide_prompts`",
    )
    parser.add_argument(
        "--manual-sections-dir",
        help="读取 IDE 模型已生成的分批章节 .md 文件，合并并校验成最终 timeline 报告；不调用 LLM API",
    )
    parser.add_argument("--bbdown-path", default=os.environ.get("BBDOWN_PATH"), help="BBDown 可执行文件路径，也可用 BBDOWN_PATH")
    parser.add_argument("--bbdown-timeout", type=positive_int, default=int_env("BBDOWN_TIMEOUT", 300), help="BBDown 下载超时秒数（默认: 300）")
    parser.add_argument(
        "--bbdown-auto-install",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="缺少 BBDown 时自动下载并校验固定版本 1.6.3（默认开启）",
    )
    parser.add_argument("--bilibili-cookie", default=os.environ.get("BILIBILI_COOKIE"), help="B站 Cookie 字符串，例如 SESSDATA=...；通过 BBDown -c 传入")
    parser.add_argument("--bilibili-cookie-file", default=os.environ.get("BILIBILI_COOKIE_FILE"), help="包含一整行 B站 Cookie 字符串的文本文件")
    parser.add_argument("--ytdlp-cookies", default=os.environ.get("YTDLP_COOKIES"), help="yt-dlp Netscape cookies 文件路径")
    parser.add_argument("--ytdlp-cookies-from-browser", default=os.environ.get("YTDLP_COOKIES_FROM_BROWSER"), help="传给 yt-dlp --cookies-from-browser 的浏览器说明，例如 chrome")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MIMO_API_KEY"),
        help="MiMo Token Plan API Key（默认读取 MIMO_API_KEY 环境变量）",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"MiMo API Base URL（默认: {DEFAULT_BASE_URL}）",
    )
    parser.add_argument(
        "--asr-provider",
        choices=["mimo", "aliyun-qwen", "stepfun", "tencent"],
        default="mimo",
        help="ASR provider（默认: mimo；可选 aliyun-qwen、stepfun、tencent）",
    )
    parser.add_argument("--asr-api-key", default=os.environ.get("ASR_API_KEY"), help="ASR provider API Key")
    parser.add_argument("--asr-base-url", default=os.environ.get("ASR_BASE_URL"), help="ASR provider Base URL")
    parser.add_argument(
        "--asr-model",
        help="ASR 模型或腾讯 EngineModelType；未提供时按 provider 默认值",
    )
    parser.add_argument(
        "--stepfun-plan",
        action="store_true",
        help="阶跃星辰 ASR 使用 Step Plan 专属 /step_plan/v1 路径；未指定时使用普通 /v1 路径",
    )
    parser.add_argument(
        "--stepfun-language",
        help="阶跃星辰 ASR language，例如 zh；未提供时交由模型自动识别",
    )
    parser.add_argument(
        "--stepfun-timeout",
        type=positive_int,
        default=int_env("STEPFUN_ASR_TIMEOUT", 120),
        help="阶跃星辰 SSE ASR 单片请求超时秒数（默认: 120）",
    )
    parser.add_argument("--tencent-secret-id", default=os.environ.get("TENCENTCLOUD_SECRET_ID"), help="腾讯云 SecretId")
    parser.add_argument("--tencent-secret-key", default=os.environ.get("TENCENTCLOUD_SECRET_KEY"), help="腾讯云 SecretKey")
    parser.add_argument("--tencent-region", default=os.environ.get("TENCENTCLOUD_REGION"), help="腾讯云 ASR region")
    parser.add_argument("--tencent-engine-model-type", help="腾讯云 ASR EngineModelType，例如 16k_zh")
    parser.add_argument("--tencent-res-text-format", type=int, default=0, help="腾讯云 ASR ResTextFormat（默认: 0）")
    parser.add_argument("--tencent-poll-interval", type=positive_int, default=3, help="腾讯云 ASR 轮询间隔秒数（默认: 3）")
    parser.add_argument("--tencent-max-polls", type=positive_int, default=120, help="腾讯云 ASR 最大轮询次数（默认: 120）")
    parser.add_argument(
        "--llm-provider",
        choices=["mimo", "openai-compatible", "aliyun", "tencent", "zhipu", "kimi", "minimax"],
        default="mimo",
        help="LLM provider。非 mimo provider 按 OpenAI-compatible 方式调用，并需要 --llm-base-url/--llm-model/--llm-api-key。",
    )
    parser.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY"), help="LLM provider API Key")
    parser.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"), help="LLM provider Base URL")
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"), help="LLM 模型名")
    parser.add_argument(
        "--segment-minutes",
        type=positive_int,
        default=DEFAULT_SEGMENT_MINUTES,
        help=f"ASR 分片分钟数，也决定报告时间窗口精度（默认: {DEFAULT_SEGMENT_MINUTES}）",
    )
    parser.add_argument(
        "--timeline-batch-size",
        type=positive_int,
        default=DEFAULT_TIMELINE_BATCH_SIZE,
        help=f"timeline 报告每批生成的窗口数（默认: {DEFAULT_TIMELINE_BATCH_SIZE}）",
    )
    parser.add_argument(
        "--proofread-batch-size",
        type=positive_int,
        default=DEFAULT_PROOFREAD_BATCH_SIZE,
        help=f"LLM 校对每批处理的 transcript 窗口数（默认: {DEFAULT_PROOFREAD_BATCH_SIZE}）",
    )
    parser.add_argument(
        "--proofread-min-ratio",
        type=positive_float,
        default=DEFAULT_PROOFREAD_MIN_RATIO,
        help=f"校对文本最小长度比例，过短会重试或回退原文（默认: {DEFAULT_PROOFREAD_MIN_RATIO}）",
    )
    parser.add_argument(
        "--llm-concurrency",
        type=positive_int,
        default=int_env("LLM_CONCURRENCY", DEFAULT_LLM_CONCURRENCY),
        help=f"LLM 批次最大并发数；遇到限流可设为 1（默认: {DEFAULT_LLM_CONCURRENCY}）",
    )
    parser.add_argument(
        "--report-style",
        choices=["timeline", "brief"],
        default="timeline",
        help="报告风格：timeline=逐窗口时间线报告，brief=旧版结构化摘要（默认: timeline）",
    )
    parser.add_argument("--save-transcript", action="store_true", help="保存带时间窗口的转写文本")
    parser.add_argument("--detailed", action="store_true", help="生成更长、更细的分析报告")
    parser.add_argument("--output-dir", default=".", help="输出目录（默认: 当前目录）")
    parser.add_argument("--title", help="报告标题/节目标题")
    parser.add_argument("--guest", help="嘉宾信息")
    parser.add_argument("--host", help="主播信息")
    parser.add_argument("--series", help="节目系列信息")
    parser.add_argument("--context-note", help="额外背景说明，会写入 prompt 但不强制输出为事实")
    parser.add_argument(
        "--terminology",
        action="append",
        help="提供术语、人名、公司名等正确写法；可重复传入，用于 LLM 校对",
    )
    parser.add_argument(
        "--terminology-file",
        help="术语/专有名词参考文件，UTF-8 文本；用于 LLM 校对",
    )
    return parser.parse_args()


def resolve_input_audio(args, temp_dir):
    input_path = args.input
    if is_url(input_path):
        bilibili_cookie = resolve_bilibili_cookie(args) if is_bilibili_url(input_path) else None
        if is_bilibili_url(input_path):
            audio_path = download_bilibili_audio(
                input_path,
                temp_dir,
                bbdown_path=args.bbdown_path,
                cookie=bilibili_cookie,
                timeout=args.bbdown_timeout,
                auto_install=args.bbdown_auto_install,
            )
            print(f"BBDown 下载完成: {audio_path.name}")
        else:
            if not check_yt_dlp():
                print("错误: 从 URL 下载需要 yt-dlp。请安装: pip install yt-dlp")
                sys.exit(1)
            print(f"下载音频: {input_path}")
            audio_path = download_audio(
                input_path,
                temp_dir,
                cookie=bilibili_cookie,
                cookies_file=args.ytdlp_cookies,
                cookies_from_browser=args.ytdlp_cookies_from_browser,
            )
            print(f"下载完成: {audio_path.name}")
    else:
        audio_path = Path(input_path)
        if not audio_path.exists():
            print(f"错误: 文件不存在: {audio_path}")
            sys.exit(1)

    if audio_path.suffix.lower() in VIDEO_EXTENSIONS:
        print("从视频提取音轨...")
        audio_mp3 = temp_dir / "audio.mp3"
        extract_audio_from_video(audio_path, audio_mp3)
        audio_path = audio_mp3
        print("音轨提取完成")

    return audio_path


def output_base_name(args):
    if args.title:
        return safe_stem(args.title, "podcast")
    if args.transcript_input:
        return safe_stem(strip_known_suffixes(Path(args.transcript_input).stem), "podcast")
    if args.input and is_bilibili_url(args.input):
        return safe_stem(extract_bilibili_bvid(args.input) or "bilibili", "bilibili")
    if args.input and is_url(args.input):
        return "podcast"
    return safe_stem(Path(args.input).stem, "podcast")


def load_transcript_from_file(path):
    transcript_path = Path(path)
    if not transcript_path.exists():
        print(f"错误: transcript 文件不存在: {transcript_path}")
        sys.exit(1)
    transcript = transcript_path.read_text(encoding="utf-8")
    if not parse_transcript_blocks(transcript):
        print("错误: transcript 文件不包含 `[HH:MM-HH:MM]` 时间窗口。")
        sys.exit(1)
    print(f"读取已有 transcript: {transcript_path} ({count_transcript_windows(transcript)} 个窗口)")
    return transcript


def main():
    args = parse_args()

    if args.self_test:
        run_self_test()
        return

    if not args.input and not args.transcript_input:
        print("错误: 缺少输入音频/视频文件路径、URL，或 --transcript-input。")
        sys.exit(2)

    if (args.export_ide_prompts or args.manual_sections_dir) and args.report_style != "timeline":
        print("错误: IDE/manual 工作流只支持 --report-style timeline。")
        sys.exit(2)
    if args.transcribe_only and args.proofread_only:
        print("错误: --transcribe-only 和 --proofread-only 不能同时使用。")
        sys.exit(2)
    if args.no_proofread and args.proofread_mode not in (None, "skip"):
        print("错误: --no-proofread 只能与 --proofread-mode skip 同时使用。")
        sys.exit(2)
    if args.proofread_only and (args.no_proofread or args.proofread_mode in ("inline", "skip")):
        print("错误: --proofread-only 需要 separate 校对模式。")
        sys.exit(2)
    if args.proofread_only and (args.export_ide_prompts or args.manual_sections_dir):
        print("错误: --proofread-only 不能与 --export-ide-prompts 或 --manual-sections-dir 同时使用。")
        sys.exit(2)
    if args.proofread_mode == "inline" and args.report_style != "timeline":
        print("错误: --proofread-mode inline 只支持 --report-style timeline。")
        sys.exit(2)

    proofread_mode = select_proofread_mode(
        "separate" if args.proofread_only else args.proofread_mode,
        args.no_proofread,
        args.transcript_input,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="mimo_asr_"))

    try:
        start_time = time.time()
        base_name = output_base_name(args)
        duration_seconds = None
        transcript_path = Path(args.transcript_input) if args.transcript_input else None

        if args.transcript_input:
            transcript = load_transcript_from_file(args.transcript_input)
        else:
            if not check_ffmpeg():
                print("错误: 未找到 ffmpeg。请安装 ffmpeg 后重试。")
                sys.exit(1)

            asr_provider = create_asr_provider(args)
            audio_path = resolve_input_audio(args, temp_dir)
            duration_seconds = get_audio_duration(audio_path)
            print("\n=== ASR 转写 ===")
            transcript = transcribe_audio(
                asr_provider,
                audio_path,
                temp_dir,
                segment_minutes=args.segment_minutes,
                duration_seconds=duration_seconds,
            )

            if args.save_transcript or args.transcribe_only or args.export_ide_prompts:
                transcript_path = output_dir / f"{base_name}_转写.txt"
                transcript_path.write_text(transcript, encoding="utf-8")
                print(f"转写文本已保存: {transcript_path}")

        metadata = build_metadata(args, base_name, duration_seconds)
        input_is_calibrated = bool(
            args.transcript_input
            and Path(args.transcript_input).stem.endswith(("_校对", "_calibrated"))
        )
        metadata["transcript_stage"] = "calibrated" if input_is_calibrated else "raw_asr"

        if args.transcribe_only:
            print("\n=== 完成 ===")
            print("已按时间窗口完成转写，跳过 LLM 总结。")
            if transcript_path:
                print(f"转写文本: {transcript_path}")
            print(f"窗口数: {count_transcript_windows(transcript)}")
            return

        if input_is_calibrated and args.proofread_mode is None and not args.no_proofread:
            print("检测到已校对 transcript，自动跳过重复校对；可用 --proofread-mode separate 强制重跑。")

        if args.proofread_only:
            if transcript_path is None:
                transcript_path = output_dir / f"{base_name}_转写.txt"
                transcript_path.write_text(transcript, encoding="utf-8")
                print(f"原始转写文本已保存: {transcript_path}")

            print("\n=== LLM 校对 ===")
            llm_provider = create_llm_provider(args)
            transcript = proofread_transcript(
                llm_provider,
                transcript,
                metadata,
                batch_size=args.proofread_batch_size,
                min_ratio=args.proofread_min_ratio,
                concurrency=args.llm_concurrency,
            )
            metadata["transcript_stage"] = "calibrated"
            calibrated_path = output_dir / f"{base_name}_校对.txt"
            calibrated_path.write_text(transcript, encoding="utf-8")
            transcript_path = calibrated_path
            print(f"校对文本已保存: {calibrated_path}")
            print("\n=== 完成 ===")
            print("已完成 LLM 校对，跳过总结报告。")
            print(f"校对文本: {transcript_path}")
            print(f"窗口数: {count_transcript_windows(transcript)}")
            return

        if args.export_ide_prompts:
            print("\n=== 导出 IDE prompts ===")
            prompt_root = export_ide_prompts(
                transcript,
                metadata,
                output_dir,
                base_name,
                batch_size=args.timeline_batch_size,
                detailed=args.detailed,
                prompt_dir=args.ide_prompts_dir,
                transcript_path=transcript_path,
            )
            print(f"IDE prompts 已导出: {prompt_root}")
            print(f"请把 prompts/ 中每批 prompt 的模型输出保存到: {prompt_root / 'sections'}")
            print("保存完成后用 --manual-sections-dir 合并生成最终报告。")
            return

        if args.manual_sections_dir:
            print("\n=== 合并 IDE 手动章节 ===")
            report = generate_manual_report(transcript, metadata, args.manual_sections_dir)
        else:
            print("\n=== LLM 总结 ===")
            llm_provider = create_llm_provider(args)
            if args.report_style == "timeline":
                if proofread_mode == "separate" and transcript_path is None:
                    transcript_path = output_dir / f"{base_name}_转写.txt"
                    transcript_path.write_text(transcript, encoding="utf-8")
                    print(f"原始转写文本已保存: {transcript_path}")

                calibrated, report = generate_timeline_outputs(
                    llm_provider,
                    transcript,
                    metadata,
                    proofread_mode=proofread_mode,
                    proofread_batch_size=args.proofread_batch_size,
                    proofread_min_ratio=args.proofread_min_ratio,
                    timeline_batch_size=args.timeline_batch_size,
                    detailed=args.detailed,
                    concurrency=args.llm_concurrency,
                )
                if calibrated is not None:
                    transcript = calibrated
                    metadata["transcript_stage"] = "calibrated"
                    calibrated_path = output_dir / f"{base_name}_校对.txt"
                    calibrated_path.write_text(transcript, encoding="utf-8")
                    transcript_path = calibrated_path
                    print(f"校对文本已保存: {calibrated_path}")
            else:
                if proofread_mode == "separate":
                    if transcript_path is None:
                        transcript_path = output_dir / f"{base_name}_转写.txt"
                        transcript_path.write_text(transcript, encoding="utf-8")
                        print(f"原始转写文本已保存: {transcript_path}")
                    transcript = proofread_transcript(
                        llm_provider,
                        transcript,
                        metadata,
                        batch_size=args.proofread_batch_size,
                        min_ratio=args.proofread_min_ratio,
                        concurrency=args.llm_concurrency,
                    )
                    metadata["transcript_stage"] = "calibrated"
                    calibrated_path = output_dir / f"{base_name}_校对.txt"
                    calibrated_path.write_text(transcript, encoding="utf-8")
                    transcript_path = calibrated_path
                    print(f"校对文本已保存: {calibrated_path}")
                report = generate_report(
                    llm_provider,
                    transcript,
                    metadata,
                    report_style=args.report_style,
                    detailed=args.detailed,
                    batch_size=args.timeline_batch_size,
                    concurrency=args.llm_concurrency,
                )

        report_suffix = "逐窗口深度解读" if args.report_style == "timeline" else "报告"
        if args.detailed and args.report_style != "timeline":
            report_suffix = "深度报告"
        report_path = output_dir / f"{base_name}_{report_suffix}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"报告已保存: {report_path}")

        elapsed = time.time() - start_time
        print("\n=== 完成 ===")
        print(f"总耗时: {elapsed:.1f} 秒")
        print(f"转写文本: {len(transcript)} 字符")
        print(f"报告: {len(report)} 字符")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
