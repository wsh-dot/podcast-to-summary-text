# Bilibili / BBDown 路由参考

修改 B站 URL 识别、BBDown 查找或自动安装、cookie 传递、下载失败处理时读取本文。B站路径没有下载器选择项，也不允许回退到 `yt-dlp`。

## 域名分类

`is_bilibili_url()` 必须使用 `urllib.parse.urlparse()` 解析 hostname，并只接受：

- `bilibili.com` 及其任意子域名；
- `b23.tv` 及其任意子域名。

host 比较前应转为小写并去掉末尾的点。不要用字符串包含判断，否则 `evil-bilibili.com`、URL path 或查询参数中的 `bilibili.com` 会被误判。小宇宙和其他 HTTP/HTTPS URL 走 `yt-dlp`。

## 下载合同

B站 URL 只执行 BBDown：

```bash
BBDown "https://www.bilibili.com/video/BV..." --audio-only -F downloaded -c "SESSDATA=..."
```

- `--audio-only`：仅下载供 ASR 使用的音频。
- `-F downloaded`：固定输出基名，便于确定性查找产物。
- `-c`：仅在 cookie 非空时追加。
- BBDown 下载、校验或执行失败时直接返回明确错误；不得调用 `yt-dlp` 重试。

不存在 `--bilibili-downloader` 参数，也不读取 `BILIBILI_DOWNLOADER`。旧参数必须由 argparse 拒绝，避免调用方误以为 B站仍可切换下载器。

## Cookie

按以下来源传给 BBDown `-c`：

1. `--bilibili-cookie`；
2. `--bilibili-cookie-file`；
3. `BILIBILI_COOKIE`。

需要登录态或遇到风控时，让用户提供浏览器 cookie 字符串，通常至少包含 `SESSDATA`。不得要求账号密码，也不得把 cookie 写入报告、日志或仓库。

PowerShell 中可避免把 cookie 留在命令历史：

```powershell
$env:BILIBILI_COOKIE = "SESSDATA=...; bili_jct=...; DedeUserID=..."
python scripts/mimo_podcast_tool.py "https://www.bilibili.com/video/BV..." --transcribe-only --api-key "tp-xxxx"
```

## BBDown 查找顺序

使用第一个有效的可执行文件：

1. `--bbdown-path`；
2. `BBDOWN_PATH`；
3. PATH 中的 `BBDown`；
4. 当前目录或 skill 本地目录中的 `BBDown/BBDown(.exe)`；
5. 用户缓存中的已校验 1.6.3；
6. 默认开启的固定版本自动安装。

显式配置的路径无效时应直接报配置错误，不要静默改用另一个二进制。`--no-bbdown-auto-install` 禁用自动安装；此时所有来源都缺失必须返回可操作的错误。

## 固定版本自动安装

只从官方 GitHub Release `nilaoda/BBDown` 的 `1.6.3` 标签下载，不查询 `latest`。下载上限为 32 MiB，边下载边计算 SHA-256，哈希通过后才允许解压。

| 平台 | Release 资产 | SHA-256 |
|---|---|---|
| Windows x64 | `BBDown_1.6.3_20240814_win-x64.zip` | `40f1e2af0d4e74df765c6f93d2e931f9bea201d5168d0bc62dc35a54b7e0ec02` |
| Windows ARM64 | `BBDown_1.6.3_20240814_win-arm64.zip` | `da8fc9cbf1031f4c4ca97af82d98bbfd1bbc55bd8ea49602da8d3d1613c190ff` |
| Linux x64 | `BBDown_1.6.3_20240814_linux-x64.zip` | `ec233b7d8d40b1cc4447dac05be343f53a757dc605743a8808abaa8e97e5d10e` |
| Linux ARM64 | `BBDown_1.6.3_20240814_linux-arm64.zip` | `f58e0a18df1a589375428a0af27ea61f5ce96ffaf67d115f335d5f9bee9a34dc` |
| macOS x64 | `BBDown_1.6.3_20240814_osx-x64.zip` | `262c15ca7890898560d00e5ffd5ada1864fbd9d0d58ac4ee492c9f3e73f3ae5f` |
| macOS ARM64 | `BBDown_1.6.3_20240814_osx-arm64.zip` | `4df84014d818bd6dff2b365b847645340e8955c4450fe965688f41af89a38baa` |

安全约束：

- ZIP 中只接受根目录的 `BBDown.exe` 或 `BBDown`；拒绝目录穿越、嵌套路径和多余候选文件。
- 在同一缓存目录创建临时文件，验证完成后原子替换目标。
- 下载中断、哈希不符、ZIP 损坏或缺少可执行文件时清理临时文件。
- Unix 二进制权限设置为 `0755`。
- 缓存命中时复用已安装文件；校验不通过则删除并重新安装或报错。

## 验证场景

- `www.bilibili.com`、子域名、`b23.tv` 命中 B站；小宇宙、YouTube、`evil-bilibili.com` 和查询参数伪装不命中。
- B站下载始终调用 BBDown；BBDown 缺失或失败时 mock 的 `yt-dlp` 调用次数保持为零。
- 非B站 URL 仍调用 `yt-dlp`。
- `--bilibili-downloader` 被 CLI 拒绝。
- 六个平台映射、缓存复用、哈希失败、损坏 ZIP、缺少可执行文件、下载中断和临时文件清理均有测试。
- cookie 按优先级传入 BBDown，且命令中没有空的 `-c`。
