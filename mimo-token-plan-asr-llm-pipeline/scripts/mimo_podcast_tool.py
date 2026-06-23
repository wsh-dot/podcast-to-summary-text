#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio/video transcription and timeline podcast report generator.

Default behavior:
  1. Split audio into 3-minute ASR windows.
  2. Transcribe each window with the configured ASR provider.
  3. Save a timestamp-window transcript when --save-transcript is set.
  4. Generate a podcast-style Markdown report in batches, or export IDE prompts for manual summary.
  5. Validate that every transcript window has exactly one report section.
"""

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

DEFAULT_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
DEFAULT_ASR_MODEL = "mimo-v2.5-asr"
DEFAULT_LLM_MODEL = "mimo-v2.5-pro"

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

LLM_MAX_TOKENS_STANDARD = 4096
LLM_MAX_TOKENS_TIMELINE_BATCH = 8192
LLM_MAX_TOKENS_FINAL_TABLE = 4096

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"}

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
    for suffix in ("_转写", "_transcript", "_报告", "_深度报告", "_逐窗口深度解读"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def chunk_list(items, size):
    for start in range(0, len(items), size):
        yield items[start:start + size]


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


def download_audio(url, output_dir):
    output_template = str(output_dir / "downloaded.%(ext)s")
    result = subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
            "-o", output_template, url,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载失败: {result.stderr}")

    downloaded = list(output_dir.glob("downloaded.*"))
    if not downloaded:
        raise FileNotFoundError("下载完成但未找到音频文件")
    return downloaded[0]


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

    metadata = {"title": "测试节目", "guest": "", "host": "", "series": "", "duration": "", "context_note": ""}
    report = generate_timeline_report(FakeLLM(), transcript, metadata, batch_size=2, detailed=False)
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

def build_metadata(args, base_name, duration_seconds):
    return {
        "title": args.title.strip() if args.title else base_name,
        "guest": args.guest.strip() if args.guest else "",
        "host": args.host.strip() if args.host else "",
        "series": args.series.strip() if args.series else "",
        "duration": format_duration(duration_seconds) or "",
        "context_note": args.context_note.strip() if args.context_note else "",
    }


def metadata_for_prompt(metadata):
    labels = {
        "title": "标题",
        "guest": "嘉宾",
        "host": "主播",
        "series": "系列",
        "duration": "时长",
        "context_note": "补充说明",
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

    lines.extend(
        [
            "> **转写说明**：本文基于 ASR 分片转写稿整理。时间点来自分片窗口，非逐句时间戳；正文按每个 transcript 窗口逐段生成并校验，尽量保留原意并对明显转写错误做轻度校正。",
            "",
            "---",
            "",
        ]
    )
    return "\n".join(lines)


def build_timeline_batch_prompt(blocks, metadata, detailed=False, repair=False):
    required_windows = "\n".join(f"- {block['window']}" for block in blocks)
    detail_instruction = (
        "每节写 2-4 个自然段；如果信息密度高，可写到 5 段。"
        if detailed
        else "每节写 1-3 个自然段。"
    )
    repair_note = "这是缺失窗口修复任务，只输出下面列出的窗口章节。" if repair else ""

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
8. 对明显 ASR 专有名词错误可以轻度校正，但不要改变观点。

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


def generate_timeline_batch(llm_provider, blocks, metadata, detailed=False, repair=False, label="生成时间章节"):
    prompt = build_timeline_batch_prompt(blocks, metadata, detailed=detailed, repair=repair)
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


def repair_missing_sections(llm_provider, missing_windows, blocks_by_window, metadata, detailed=False):
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
        )
        if duplicates:
            print(f"  警告: 修复窗口 {window} 输出重复章节: {', '.join(duplicates)}")
        if extras:
            print(f"  警告: 修复窗口 {window} 输出额外章节，已忽略: {', '.join(extras)}")
        if window in sections:
            repaired[window] = sections[window]
    return repaired


def generate_timeline_sections(llm_provider, blocks, metadata, batch_size, detailed=False):
    sections_by_window = {}
    total_batches = math.ceil(len(blocks) / batch_size)

    for batch_index, batch in enumerate(chunk_list(blocks, batch_size), start=1):
        first_window = batch[0]["window"]
        last_window = batch[-1]["window"]
        sections, duplicates, extras = generate_timeline_batch(
            llm_provider,
            batch,
            metadata,
            detailed=detailed,
            repair=False,
            label=f"生成时间章节批次 {batch_index}/{total_batches} ({first_window} 到 {last_window})",
        )
        if duplicates:
            print(f"  警告: 批次 {batch_index} 输出重复章节，已保留首次出现: {', '.join(duplicates)}")
        if extras:
            print(f"  警告: 批次 {batch_index} 输出额外章节，已忽略: {', '.join(extras)}")
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


def generate_timeline_report(llm_provider, transcript, metadata, batch_size, detailed=False):
    blocks = parse_transcript_blocks(transcript)
    if not blocks:
        raise RuntimeError("timeline 报告需要带 `[HH:MM-HH:MM]` 的 transcript。")

    print(f"检测到 {len(blocks)} 个 transcript 窗口；按每批 {batch_size} 个窗口生成。")
    body, sections_by_window = generate_timeline_sections(
        llm_provider,
        blocks,
        metadata,
        batch_size=batch_size,
        detailed=detailed,
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


def generate_report(llm_provider, transcript, metadata, report_style="timeline", detailed=False, batch_size=DEFAULT_TIMELINE_BATCH_SIZE):
    if report_style == "brief":
        return generate_brief_report(llm_provider, transcript, metadata, detailed=detailed)
    return generate_timeline_report(
        llm_provider,
        transcript,
        metadata,
        batch_size=batch_size,
        detailed=detailed,
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
        prompt_text = build_timeline_batch_prompt(batch, metadata, detailed=detailed, repair=False)
        full_prompt = (
            "# IDE Timeline Batch Prompt\n\n"
            f"- Batch: {index}/{len(batches)}\n"
            f"- Required output file: `sections/{section_name}`\n"
            "- Paste the prompt below into the current IDE model.\n"
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
2. Paste the prompt into the current IDE model.
3. Save the model output to the matching file path under `sections/`.
4. Merge and validate the final report with:

```bash
python scripts/mimo_podcast_tool.py --transcript-input "{merge_transcript}" --manual-sections-dir "{sections_dir}" --output-dir "{output_dir}"
```

## Contract

- Each prompt lists exact required windows.
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

  # 已有 transcript，合并 Agent 生成的章节
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --manual-sections-dir podcast_agent_sections

  # 明确使用 API LLM 总结
  python mimo_podcast_tool.py podcast.mp3 --asr-provider mimo --api-key "tp-xxxx" --llm-provider kimi --llm-api-key "sk-..."
  python mimo_podcast_tool.py --transcript-input podcast_转写.txt --llm-provider openai-compatible --llm-base-url "https://..." --llm-model "model" --llm-api-key "sk-..."

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
        choices=["mimo", "aliyun-qwen", "tencent"],
        default="mimo",
        help="ASR provider（默认: mimo；可选 aliyun-qwen、tencent）",
    )
    parser.add_argument("--asr-api-key", default=os.environ.get("ASR_API_KEY"), help="ASR provider API Key")
    parser.add_argument("--asr-base-url", default=os.environ.get("ASR_BASE_URL"), help="ASR provider Base URL")
    parser.add_argument(
        "--asr-model",
        help="ASR 模型或腾讯 EngineModelType；未提供时按 provider 默认值",
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
    return parser.parse_args()


def resolve_input_audio(args, temp_dir):
    input_path = args.input
    if input_path.startswith(("http://", "https://")):
        if not check_yt_dlp():
            print("错误: 从 URL 下载需要 yt-dlp。请安装: pip install yt-dlp")
            sys.exit(1)
        print(f"下载音频: {input_path}")
        audio_path = download_audio(input_path, temp_dir)
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
    if args.input and args.input.startswith(("http://", "https://")):
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

        if args.transcribe_only:
            print("\n=== 完成 ===")
            print("已按时间窗口完成转写，跳过 LLM 总结。")
            if transcript_path:
                print(f"转写文本: {transcript_path}")
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
            report = generate_report(
                llm_provider,
                transcript,
                metadata,
                report_style=args.report_style,
                detailed=args.detailed,
                batch_size=args.timeline_batch_size,
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

