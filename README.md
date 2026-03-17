<div align="center">

# 🔗 ParseHubBot

**Telegram 聚合解析 Bot，支持 AI 总结 & 内联模式**

**Telegram Aggregation Parsing Bot with AI Summary & Inline Mode**

[![License](https://img.shields.io/github/license/z-mio/Parse_Hub_Bot?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://t.me/ParseHubBot)

[实例演示](https://t.me/ParseHubBot) · [相关项目](https://github.com/z-mio/ParseHub) · [问题反馈](https://github.com/z-mio/ParseHubBot/issues)

</div>

---

> [!WARNING]
> 🚧 本项目正在重构中

## ✨ 功能特性

- 🎬 **多平台支持** — 抖音 / 哔哩哔哩 / YouTube / TikTok / 小红书 / Twitter 等
- 🤖 **AI 总结** — 自动生成内容摘要
- ⚡ **内联模式** — 在任意聊天窗口直接调用解析
- 🐳 **Docker 部署** — 一键启动，开箱即用

## 📦 支持平台

| 平台            | 支持内容    |
|---------------|---------|
| 抖音            | 视频 / 图文 |
| 哔哩哔哩          | 视频 / 动态 |
| YouTube       | 视频      |
| YouTube Music | 音乐      |
| TikTok        | 视频 / 图文 |
| 小红书           | 视频 / 图文 |
| Twitter       | 视频 / 图文 |
| 百度贴吧          | 图文 / 视频 |
| Facebook      | 视频      |
| 微博            | 视频 / 图文 |
| Instagram     | 视频 / 图文 |

> 📎 更多平台支持请查看 [ParseHub](https://github.com/z-mio/ParseHub)

## 📸 截图预览

<details>
<summary>点击展开</summary>

![](https://img.155155155.xyz/i/2024/09/66f2d4b70416c.webp)
![](https://img.155155155.xyz/i/2024/09/66f2d4d6ca7ec.webp)
![](https://img.155155155.xyz/i/2024/09/66f3f92973ad1.webp)

</details>

## 🚀 快速开始

### 1. 修改配置

#### 环境变量

将 `.env.exa` 复制为 `.env`，并填写以下参数：

| 参数                    | 说明                                               |
|-----------------------|--------------------------------------------------|
| `API_HASH` / `API_ID` | 登录 [my.telegram.org](https://my.telegram.org) 获取 |
| `BOT_TOKEN`           | 在 [@BotFather](https://t.me/BotFather) 获取        |
| `BOT_PROXY`           | 海外服务器无需填写                                        |
| `DOUYIN_API`          | 抖音 API 地址，默认: `https://douyin.wtf`               |

#### 平台配置

将 `data/config/platform_config.yaml.exa` 复制为 `data/config/platform_config.yaml`

> 📌 配置优先级: **平台配置** > **环境变量**

<details>
<summary>配置说明</summary>

```yaml
platforms:
  twitter: # 平台 id
    disable_parser_proxy: false      # 解析时是否禁用代理
    disable_downloader_proxy: false   # 下载时是否禁用代理
    parser_proxies: [ ]                # 解析代理池，多个代理随机选择
    downloader_proxies: [ ]            # 下载代理池，多个代理随机选择
    cookies: [ ]                       # 平台 cookies，部分帖子需登录获取
```

</details>

<details>
<summary>配置示例</summary>

```yaml
platforms:
  twitter:
    cookies:
      - auth_token=xxxx; ct0=xxxx
      - auth_token=xxxx; ct0=xxxx

  bilibili:
    disable_parser_proxy: true
    downloader_proxies:
      - http://127.0.0.1:7890
      - http://127.0.0.1:7891
```

</details>

### 2. 部署运行

#### 🐳 Docker（推荐）

```shell
sudo sh start.sh           # 构建并运行 Bot
sudo sh start.sh stop      # 停止 Bot
sudo sh start.sh restart   # 重启 Bot
sudo sh start.sh -h        # 查看帮助
```

#### 🖥️ 手动运行

```shell
# 安装依赖
apt install python3-pip -y
pip install uv --break-system-packages
uv venv --python 3.12
uv sync

# 启动 Bot
uv run bot.py
```

## 📖 使用方式

| 方式       | 操作                      |
|----------|-------------------------|
| **普通模式** | 发送分享链接给 Bot，或使用指令 `/jx` |
| **内联模式** | 任意聊天窗口输入 `@Bot用户名 链接`   |

## 🔗 相关项目

- [z-mio/ParseHub](https://github.com/z-mio/ParseHub) — 聚合解析核心库

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。
