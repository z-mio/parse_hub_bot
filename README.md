<div align="center">

# 🔗 ParseHubBot

**Telegram 多平台聚合解析机器人**

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

[**🤖 实例演示**](https://t.me/ParseHubot) · [**📚 相关项目**](https://github.com/z-mio/ParseHub) · [**🐛 问题反馈**](https://github.com/z-mio/Parse_Hub_Bot/issues)

</div>

---

> 官方实例：[@ParseHubot](https://t.me/ParseHubot)

## ✨ 功能特性

- 🎬 **多平台解析** — 抖音、B站、YouTube、小红书、Twitter 等 16+ 主流平台一站搞定
- ⚡ **内联模式** — 在任意聊天窗口输入 `@BotUsername <链接>` 即可解析
- 🖼️ **Tg 兼容** — 自动转码、长图切割、大视频分段
- 📦 **多种模式** — 在线预览, 原始文件, 打包下载
- 🐳 **Docker 部署** — 开箱即用

## 📦 支持平台一览


| 平台              | 视频 | 图文 |  其他   |
|:----------------|:--:|:--:|:-----:|
| **Twitter / X** | ✅  | ✅  | 📝 文章 |
| **Instagram**   | ✅  | ✅  |       |
| **YouTube**     | ✅  |    | 🎵 音乐 |
| **Facebook**    | ✅  |    |       |
| **Threads**     | ✅  | ✅  |       |
| **Bilibili**    | ✅  |    | 📝 动态 |
| **抖音 / TikTok** | ✅  | ✅  |       |
| **微博**          | ✅  | ✅  |       |
| **小红书**         | ✅  | ✅  |       |
| **贴吧**          | ✅  | ✅  |       |
| **微信公众号**       |    | ✅  |       |
| **快手**          | ✅  |    |       |
| **酷安**          | ✅  | ✅  |       |
| **皮皮虾**         | ✅  | ✅  |       |
| **最右**          | ✅  | ✅  |       |
| **小黑盒**         | ✅  | ✅  |       |

> 🔧 更多平台持续接入中...

## 🚀 快速开始

### 🐳 Docker 运行 (推荐)

```bash
mkdir parse_hub_bot && cd parse_hub_bot

docker run -d \
  --restart=always \
  -e API_ID=你的API_ID \
  -e API_HASH=你的API_HASH \
  -e BOT_TOKEN=你的BOT_TOKEN \
  -v ./logs:/app/logs \
  -v ./data:/app/data \
  --name parse-hub-bot \
  ghcr.io/z-mio/parse_hub_bot:latest
```



### 💻 源码运行

```bash
uv sync
uv run bot.py
```

---

## ⚙️ 配置说明

- **环境变量:** 基础配置  
- **平台配置 (可选):** 平台代理和 Cookie  

### 📝 环境变量

```dotenv
# ✅ 必填
API_ID=        # Telegram API ID，登录 https://my.telegram.org 获取
API_HASH=      # Telegram API Hash，同上获取
BOT_TOKEN=     # 机器人 Token，向 @BotFather 申请

# 🔲 可选
BOT_PROXY=     # Bot 连接 TG 使用的代理，例：http://127.0.0.1:7890
CACHE_TIME=    # 缓存有效时间（秒），默认 2592000（30 天），0 为永久缓存
DOUYIN_API=    # 自定义抖音 API 解析服务地址
```

### 🌐 平台配置

用于为各解析平台单独配置**代理**和 **Cookie**，位于 `data/config/platform_config.yaml`

```yaml
# ═══════════════════════ 全局默认代理 ═══════════════════════
# 当某平台未单独配置代理时，会使用全局默认代理
# 支持填写单个地址(字符串)或多个地址(列表，随机选取)

default_parser_proxies: http://127.0.0.1:7890        # 解析代理（单个）
default_downloader_proxies:                           # 下载代理（代理池）
  - http://127.0.0.1:7890
  - http://127.0.0.1:7891

# ═══════════════════════ 平台独立配置 ═══════════════════════
platforms:
  <platform_id>:                        # 平台 ID，见下方支持列表
    disable_parser_proxy: false          # 是否禁用解析代理（直连）
    disable_downloader_proxy: false      # 是否禁用下载代理（直连）
    parser_proxies:                      # 该平台专用解析代理池
      - http://proxy1:port
    downloader_proxies:                  # 该平台专用下载代理池
      - http://proxy2:port
    cookies:                             # 该平台 Cookie 列表（随机选取）
      - "cookie_string_1"
      - "cookie_string_2"
```


### 🔀 代理优先级

解析代理和下载代理各自遵循相同的优先级逻辑：

```
禁用代理 (disable_*_proxy: true)
  ↓ 未禁用
平台专用代理 (parser_proxies / downloader_proxies)
  ↓ 未配置
全局默认代理 (default_parser_proxies / default_downloader_proxies)
  ↓ 未配置
直连（不使用代理）
```


> 💡 当代理池中有多个地址时，每次请求会**随机选取**一个

### 🔑 支持的平台 ID

`<platform_id>` 必须是以下合法的平台 ID：

| 平台 ID | 对应平台 |
|:---|:---|
| `twitter` | Twitter / X |
| `instagram` | Instagram |
| `youtube` | YouTube |
| `facebook` | Facebook |
| `threads` | Threads |
| `bilibili` | 哔哩哔哩 |
| `douyin` | 抖音 |
| `tiktok` | TikTok |
| `weibo` | 微博 |
| `xhs` | 小红书 |
| `tieba` | 百度贴吧 |
| `wechat` | 微信公众号 |
| `kuaishou` | 快手 |
| `coolapk` | 酷安 |
| `pipixia` | 皮皮虾 |
| `zuiyou` | 最右 |
| `xiaoheihe` | 小黑盒 |

### 🍪 支持 Cookie 的平台

 - `Twitter`
 - `Instagram`
 - `Kuaishou`
 - `Bilibili`
 - `YouTube`

### 📌 配置示例

##### 示例 1：国内平台直连，海外平台走代理

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


#### 示例 2：Twitter 配置 Cookie + 使用全局代理

```yaml
default_parser_proxies: http://127.0.0.1:7890
default_downloader_proxies: http://127.0.0.1:7890

platforms:
  twitter:
    cookies:
      - "auth_token=your_token_here; ct0=your_ct0_here"
```


#### 示例 3：YouTube 使用独立代理池

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


#### 示例 4：B站指定 Cookie 轮换 + 解析直连 + 下载走代理

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



## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=z-mio/Parse_Hub_Bot&type=Date)](https://star-history.com/#z-mio/Parse_Hub_Bot&Date)

## 🤝 参与贡献

欢迎提交 Pull Request 或 Issue！

- 核心解析相关请前往 [ParseHub](https://github.com/z-mio/ParseHub)。
- Bug 反馈请附上相关 URL 和日志信息。

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 协议开源。

---

<div align="center">

**如果这个项目对你有帮助，欢迎点个 ⭐ Star！**

</div>

