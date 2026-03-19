<div align="center">

# 🔗 ParseHubBot

**Telegram 聚合解析 Bot，支持 AI 总结 & 内联模式**

**Telegram Aggregation Parsing Bot with AI Summary & Inline Mode**

[![License](https://img.shields.io/github/license/z-mio/Parse_Hub_Bot?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-blue?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?style=flat-square&logo=telegram&logoColor=white)](https://t.me/ParseHubot)

[实例演示](https://t.me/ParseHubot) · [相关项目](https://github.com/z-mio/ParseHub) · [问题反馈](https://github.com/z-mio/ParseHubBot/issues)

</div>

---

> [!WARNING]
> 🚧 本项目正在重构中

> **实例：[@ParseHubot](https://t.me/ParseHubot)**

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

## 🚀 部署与配置

### 1. 前置条件

- Python `3.12+`
- 推荐使用 `uv` 管理依赖
- 若使用 Docker：Docker `20+`
- 若手动运行：请确保系统可用 `ffmpeg`（媒体处理依赖）

### 2. 配置文件

#### 2.1 环境变量（`.env`）

先复制模板：

```shell
# Linux / macOS
cp .env.exa .env

# Windows PowerShell
Copy-Item .env.exa .env
```

再按需填写：

| 参数           | 必填 | 说明                                                                 |
|--------------|----|--------------------------------------------------------------------|
| `API_ID`     | ✅  | Telegram API ID，登录 [my.telegram.org](https://my.telegram.org) 获取   |
| `API_HASH`   | ✅  | Telegram API Hash，登录 [my.telegram.org](https://my.telegram.org) 获取 |
| `BOT_TOKEN`  | ✅  | Bot Token，向 [@BotFather](https://t.me/BotFather) 申请                |
| `BOT_PROXY`  | 可选 | Bot 连接 Telegram 使用的代理，例如 `http://127.0.0.1:7890`                   |
| `DATA_PATH`  | 可选 | 数据目录，默认 `data`                                                     |
| `CACHE_TIME` | 可选 | 缓存秒数，默认 `2592000`（30 天），`0` 表示永久缓存                                 |
| `DOUYIN_API` | 可选 | 自定义抖音 API 地址                                                       |

#### 2.2 平台配置（`platform_config.yaml`）

先复制模板：

```shell
# Linux / macOS
cp data/config/platform_config.yaml.exa data/config/platform_config.yaml

# Windows PowerShell
Copy-Item data/config/platform_config.yaml.exa data/config/platform_config.yaml
```

配置结构说明：

```yaml
default_parser_proxies: [ ]        # 全局解析代理池（可选）
default_downloader_proxies: [ ]    # 全局下载代理池（可选）

platforms:
  twitter: # 平台 id
    disable_parser_proxy: false   # true 时该平台解析强制不走代理
    disable_downloader_proxy: false
    parser_proxies: [ ]            # 平台解析代理池（随机选择）
    downloader_proxies: [ ]        # 平台下载代理池（随机选择）
    cookies: [ ]                   # 平台 cookies（部分内容需要登录）
```

代理生效逻辑：

- 解析代理：`platform.parser_proxies` > `default_parser_proxies` > 不使用代理
- 下载代理：`platform.downloader_proxies` > `default_downloader_proxies` > 不使用代理
- 若 `disable_*_proxy: true`，对应阶段会强制不使用代理

配置示例：

```yaml
default_parser_proxies:
  - http://127.0.0.1:7890

platforms:
  twitter:
    cookies:
      - auth_token=xxxx; ct0=xxxx

  bilibili:
    disable_parser_proxy: true
    downloader_proxies:
      - http://127.0.0.1:7890
      - http://127.0.0.1:7891
```

### 3. 部署运行

#### 3.1 Docker（推荐）

`start.sh` 支持以下命令：`start`（默认）/ `stop` / `restart` / `logs` / `status`。

```shell
bash start.sh            # 构建并启动（等价于 start）
bash start.sh stop       # 停止并移除容器
bash start.sh restart    # 重启容器
bash start.sh logs       # 查看容器日志
bash start.sh status     # 查看容器状态
bash start.sh -h         # 查看帮助
```

如果你不使用脚本，也可手动执行 Docker：

```shell
docker build -t parse-hub-bot .
docker run -d \
  --restart=on-failure:2 \
  --env-file .env \
  -v ./logs:/app/logs \
  -v ./data:/app/data \
  --name parse-hub-bot \
  parse-hub-bot
```

#### 3.2 手动运行

```shell
# 1) 安装 uv（任选其一，详见 https://docs.astral.sh/uv/ ）
# 2) 安装项目依赖
uv sync

# 3) 启动 Bot
uv run bot.py
```

## 🔗 相关项目

- [z-mio/ParseHub](https://github.com/z-mio/ParseHub) — 聚合解析核心库

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。
