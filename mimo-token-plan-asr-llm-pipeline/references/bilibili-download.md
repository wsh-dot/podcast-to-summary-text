# Bilibili URL 下载实现记录

本文记录对 `zj1123581321/VideoTranscriptAPI` 的 B 站下载实现分析，并说明本 skill 的改造策略。

## 参考仓库版本

- `zj1123581321/VideoTranscriptAPI`: `8f05ab2`
- 重点文件：`src/video_transcript_api/downloaders/bilibili.py`
- 相关配置：`config/config.example.jsonc` 的 `bbdown` 段
- 相关文档：`docs/development/bilibili_metadata_enhancement.md`、`docs/guides/api/bbdown_guide.md`

## VideoTranscriptAPI 的处理链路

1. 下载器工厂 `create_downloader(url)` 会在 URL 命中 `bilibili.com` 或 `b23.tv` 时返回 `BilibiliDownloader`。
2. `BilibiliDownloader.can_handle()` 只做域名判断；`_extract_video_id()` 负责从长链接提取 BV 号，短链会先通过 `resolve_short_url()` 跟随跳转。
3. 元数据阶段调用 B 站官方接口：
   `https://api.bilibili.com/x/web-interface/view?bvid=<BV>`
   请求头伪装浏览器，并设置 `Referer`。
4. 官方元数据接口的 cookie 策略：
   - 如果 `config.bbdown.bilibili_cookie` 非空，放入请求头 `Cookie`。
   - 否则生成随机 `buvid3=<UUID>infoc`，降低完全无 cookie 时的 `-412/-799/-509` 风控概率。
   - 对网络异常和这些 body code 做最多 3 次指数退避重试。
5. 下载阶段按 `config.bbdown.use_bbdown` 分支：
   - `true`：调用本地 BBDown 可执行文件下载，默认 `--audio-only`。
   - `false`：调用 TikHub API 获取 `cid` 和 `dash.audio[0].baseUrl`，再用通用下载器请求这个音频 URL。
6. BBDown 模式下，`get_download_info()` 会实际下载音频到临时目录，然后返回 `DownloadInfo(local_file=..., downloaded=True)`。主流程看到 `downloaded=True` 后直接把本地文件交给转录器。
7. 主流程会跳过 B 站平台字幕，因为 `get_subtitle()` 固定返回 `None`，所以 B 站始终走“下载音视频 -> ASR 转写”。

## 关键设计点

- 元数据和下载必须解耦。VideoTranscriptAPI 曾经在元数据阶段触发 BBDown 下载，BBDown 超时会连带导致标题/作者丢失；当前修复是在 BBDown 模式下元数据阶段只调用官方 API。
- 对 B 站不能只依赖裸 `yt-dlp`。公开视频可能可用，但受限内容、登录可见内容或服务器 IP 风控经常需要 cookie。
- BBDown 是 B 站专用路径，命令行支持：
  - `--audio-only`：只下载音频，适合 ASR。
  - `-p <page>`：选择分 P。
  - `-c "<cookie>"` / `--cookie "<cookie>"`：传入网页 cookie。
  - `-F downloaded`：固定输出文件名，便于脚本找到下载产物。

## 注意：上游实现的 cookie 差异

VideoTranscriptAPI 的 `bilibili_cookie` 当前用于官方元数据 API；在所分析版本中，它没有被追加到 BBDown 命令。BBDown 自身支持 `-c/--cookie`，所以本 skill 改造时直接把 `--bilibili-cookie` / `BILIBILI_COOKIE` 接到 BBDown `-c`，并在 `yt-dlp` fallback 中用 `--add-headers Cookie:<cookie>`。

## 本 skill 的实现策略

脚本 `scripts/mimo_podcast_tool.py` 对 B 站 URL 使用以下策略：

1. `is_bilibili_url()` 判断 `bilibili.com` / `b23.tv`。
2. `--bilibili-downloader auto` 默认优先 BBDown。
3. BBDown 命令形态：
   ```bash
   BBDown "https://www.bilibili.com/video/BV..." --audio-only -F downloaded -c "SESSDATA=..."
   ```
4. 如果 `auto` 模式下 BBDown 不存在或失败，回退到 `yt-dlp -x --audio-format mp3`。
5. 如果用户指定 `--bilibili-downloader bbdown`，BBDown 失败就直接报错，不静默回退。
6. cookie 来源：
   - `--bilibili-cookie "SESSDATA=..."`
   - `--bilibili-cookie-file cookie.txt`
   - 环境变量 `BILIBILI_COOKIE`
7. BBDown 可执行文件来源：
   - `--bbdown-path`
   - 环境变量 `BBDOWN_PATH`
   - PATH 中的 `BBDown`
   - 当前目录或 skill 根目录下的 `BBDown/BBDown(.exe)`

## 推荐用户提示

当用户给 B 站链接且下载失败时，优先让用户提供 B 站网页 cookie 字符串，至少包含 `SESSDATA`。不要要求用户把账号密码交给脚本。

示例：

```bash
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." \
  --transcribe-only \
  --api-key "tp-xxxx" \
  --bilibili-cookie "SESSDATA=...; bili_jct=...; DedeUserID=..."
```

如果不想把 cookie 放进命令历史：

```bash
$env:BILIBILI_COOKIE = "SESSDATA=...; bili_jct=...; DedeUserID=..."
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-xxxx"
```
