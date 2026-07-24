<div align="center">

# 🔗 ParseHubBot

**Telegram Multi-Platform Content Parsing Bot**

<p align="center">
  <a href="https://github.com/z-mio/Parse_Hub_Bot/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/z-mio/Parse_Hub_Bot?style=flat-square&color=5D6D7E" alt="License">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://t.me/ParseHubot">
    <img src="https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=flat-square&logo=telegram&logoColor=white" alt="Telegram Bot">
  </a>
  <a href="https://github.com/astral-sh/uv">
    <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json&style=flat-square" alt="uv">
  </a>
</p>

[简体中文](README.md) |
English

[**🤖 Live Demo**](https://t.me/ParseHubot) ·
[**📚 Related Project**](https://github.com/z-mio/ParseHub) ·
[**🐛 Report an Issue**](https://github.com/z-mio/Parse_Hub_Bot/issues)

</div>

---

> Official bot: [@ParseHubot](https://t.me/ParseHubot)

## ✨ Features

- 🎬 **Multi-platform parsing** — Parse content from 16+ major platforms, including Douyin, Bilibili, YouTube,
  Xiaohongshu, and Twitter
- ⚡ **Inline mode** — Parse a link from any chat by typing `@BotUsername <link>`
- 🖼️ **Telegram-ready media** — Automatic transcoding, long-image splitting, and large-video segmentation
- 📦 **Multiple delivery modes** — Online preview, original file, or packaged download
- 🐳 **Docker deployment** — Ready to use out of the box

## 📦 Supported Platforms

| Platform        | Video | Posts |          Other           |
|:----------------|:-----:|:-----:|:------------------------:|
| **Twitter / X** |   ✅   |   ✅   |       📝 Articles        |
| **Instagram**   |   ✅   |   ✅   |                          |
| **YouTube**     |   ✅   |       |         🎵 Music         |
| **Facebook**    |   ✅   |       |                          |
| **Threads**     |   ✅   |   ✅   |                          |
| **Bilibili**    |   ✅   |       |        📝 Updates        |
| **Douyin**      |   ✅   |   ✅   |      ☀️ Daily posts      |
| **TikTok**      |   ✅   |   ✅   |                          |
| **Weibo**       |   ✅   |   ✅   |                          |
| **Xiaohongshu** |   ✅   |   ✅   |                          |
| **Tieba**       |   ✅   |   ✅   |                          |
| **WeChat OA**   |       |   ✅   |                          |
| **Kuaishou**    |   ✅   |       |                          |
| **Coolapk**     |       |   ✅   |                          |
| **Pipixia**     |   ✅   |   ✅   |                          |
| **Zuiyou**      |   ✅   |   ✅   |                          |
| **Xiaoheihe**   |   ✅   |   ✅   |                          |
| **Snapchat**    |   ✅   |       |                          |
| **Zhihu**       |   ✅   |   ✅   | 🐶 Q&A, columns, circles |

> 🔧 More platforms are being added continuously...

## 🚀 Quick Start

### 🐳 Run with Docker (recommended)

```bash
mkdir parse_hub_bot && cd parse_hub_bot

docker run -d \
  --restart=always \
  -e API_ID=YOUR_API_ID \
  -e API_HASH=YOUR_API_HASH \
  -e BOT_TOKEN=YOUR_BOT_TOKEN \
  -v ./logs:/app/logs \
  -v ./data:/app/data \
  --name parse-hub-bot \
  ghcr.io/z-mio/parse_hub_bot:latest
```

### 💻 Run from Source

```bash
uv sync
uv run bot.py
```

---

## ⚙️ Configuration

- **Environment variables:** Required base configuration
- **Platform configuration (optional):** Per-platform proxies and cookies

### 📝 Environment Variables

```dotenv
# ✅ Required
API_ID=        # Telegram API ID; obtain it at https://my.telegram.org
API_HASH=      # Telegram API Hash; obtain it at the same place
BOT_TOKEN=     # Bot token; create one via @BotFather

# 🔲 Optional
BOT_PROXY=     # Proxy for the bot's Telegram connection, e.g. http://127.0.0.1:7890
```

### 🌐 Platform Configuration

Configure **proxies** and **cookies** for each parser platform in `data/config/platform_config.yaml`.

```yaml
# ═══════════════════════ Global default proxies ═══════════════════════
# A platform without an individual proxy configuration uses the global default.
# A proxy may be a single address (string) or a pool of addresses (list, selected at random).

default_parser_proxies: http://127.0.0.1:7890        # Parser proxy (single)
default_downloader_proxies: # Downloader proxy (pool)
  - http://127.0.0.1:7890
  - http://127.0.0.1:7891

# ═══════════════════════ Per-platform configuration ═══════════════════════
platforms:
  <platform_id>: # Platform ID; see the supported-platform list below
    disable_parser_proxy: false          # Disable parser proxy (use direct connection)
    disable_downloader_proxy: false      # Disable downloader proxy (use direct connection)
    parser_proxies: # Dedicated parser proxy pool for this platform
      - http://proxy1:port
    downloader_proxies: # Dedicated downloader proxy pool for this platform
      - http://proxy2:port
    cookies: # Cookie list for this platform (selected at random)
      - "cookie_string_1"
      - "cookie_string_2"
```

### 🔀 Proxy Priority

Parser and downloader proxies each use the same priority order:

```
Disable proxy (disable_*_proxy: true)
  ↓ if not disabled
Platform-specific proxy (parser_proxies / downloader_proxies)
  ↓ if not configured
Global default proxy (default_parser_proxies / default_downloader_proxies)
  ↓ if not configured
Direct connection (no proxy)
```

> 💡 When a proxy pool contains multiple addresses, one is **selected at random** for every request.

### 🔑 Supported Platform IDs

`<platform_id>` must be one of the following valid platform IDs:

| Platform ID | Platform    |
|:------------|:------------|
| `twitter`   | Twitter / X |
| `instagram` | Instagram   |
| `youtube`   | YouTube     |
| `facebook`  | Facebook    |
| `threads`   | Threads     |
| `bilibili`  | Bilibili    |
| `douyin`    | Douyin      |
| `tiktok`    | TikTok      |
| `weibo`     | Weibo       |
| `xhs`       | Xiaohongshu |
| `tieba`     | Baidu Tieba |
| `wechat`    | WeChat OA   |
| `kuaishou`  | Kuaishou    |
| `coolapk`   | Coolapk     |
| `pipixia`   | Pipixia     |
| `zuiyou`    | Zuiyou      |
| `xiaoheihe` | Xiaoheihe   |
| `snapchat`  | Snapchat    |
| `zhihu`     | Zhihu       |

### 🍪 Platforms Supporting Cookies

- `Twitter / X`
- `Instagram`
- `Threads`
- `YouTube`
- `Bilibili`
- `Douyin`
- `TikTok`
- `Kuaishou`
- `Xiaohongshu`
- `Zhihu`

### 📌 Configuration Examples

##### Example 1: Use direct connections for mainland Chinese platforms and a proxy for overseas platforms

```yaml
default_parser_proxies: http://127.0.0.1:7890
default_downloader_proxies: http://127.0.0.1:7890

platforms:
  bilibili:
    disable_parser_proxy: true
    disable_downloader_proxy: true
  douyin:
    disable_parser_proxy: true
    disable_downloader_proxy: true
  xhs:
    disable_parser_proxy: true
    disable_downloader_proxy: true
```

#### Example 2: Configure a Twitter cookie and use the global proxy

```yaml
default_parser_proxies: http://127.0.0.1:7890
default_downloader_proxies: http://127.0.0.1:7890

platforms:
  twitter:
    cookies:
      - "auth_token=your_token_here; ct0=your_ct0_here"
```

#### Example 3: Use a dedicated proxy pool for YouTube

```yaml
platforms:
  youtube:
    parser_proxies:
      - http://proxy-us-1:8080
      - http://proxy-us-2:8080
      - http://proxy-eu-1:8080
    downloader_proxies:
      - http://proxy-us-1:8080
      - http://proxy-eu-1:8080
```

#### Example 4: Rotate Bilibili cookies, parse directly, and use a proxy for downloads

```yaml
platforms:
  bilibili:
    disable_parser_proxy: true
    downloader_proxies:
      - http://127.0.0.1:7890
    cookies:
      - "SESSDATA=xxx; bili_jct=xxx; buvid3=xxx"
      - "SESSDATA=yyy; bili_jct=yyy; buvid3=yyy"
```

## 🤝 Contributing

Pull requests and issues are welcome!

- For core parsing features, please visit [ParseHub](https://github.com/z-mio/ParseHub).
- When reporting a bug, please include the relevant URL and log information.

### Development Guidelines

Before submitting code, run at least:

```bash
ruff format && ruff check --fix && uv run mypy
uv run pytest
```

## 📄 License

This project is released under the [MIT License](LICENSE).

---

<div align="center">

**If this project helps you, please consider giving it a ⭐ Star!**

</div>
