<div align="center">

# 🔗 ParseHubBot

**Telegram 多平台聚合解析 Bot，支持 AI 总结 & 内联模式**

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

[**🤖 实例演示**](https://t.me/ParseHubot) · [**📚 相关项目**](https://github.com/z-mio/ParseHub) · [**🐛 问题反馈
**](https://github.com/z-mio/Parse_Hub_Bot/issues)

</div>

---

> [!WARNING]  
> 🚧 **本项目正在重构中，部分功能可能存在变动。**
>
> 官方实例：[@ParseHubot](https://t.me/ParseHubot)

## ✨ 功能特性

- 🎬 **多平台解析** — 抖音、B站、YouTube、TikTok、小红书、Twitter 等主流平台一站搞定
- 🤖 **AI 总结** — 自动提取视频/图文核心内容，生成结构化摘要
- ⚡ **内联模式** — 在任意聊天窗口输入 `@BotUsername <链接>` 即可解析
- 📦 **多种模式** — 在线预览, 原始文件, 打包下载
- 🐳 **Docker 部署** — 开箱即用

## 📦 支持平台一览

| 平台                   | 支持内容    |
|:---------------------|:--------|
| 🎵 **抖音**            | 视频 / 图文 |
| 📺 **哔哩哔哩**          | 视频 / 动态 |
| 🟥 **YouTube**       | 视频      |
| 🎧 **YouTube Music** | 音乐      |
| 🎵 **TikTok**        | 视频 / 图文 |
| 📕 **小红书**           | 视频 / 图文 |
| 🐦 **Twitter**       | 视频 / 图文 |
| 🐾 **百度贴吧**          | 视频 / 图文 |
| 📘 **Facebook**      | 视频      |
| 👁️ **微博**           | 视频 / 图文 |
| 📷 **Instagram**     | 视频 / 图文 |
| ...                  | ...     |

> 更多平台支持详见核心库 [ParseHub](https://github.com/z-mio/ParseHub)。

## 📸 预览

<details>
<summary><b>点击展开查看运行效果</b></summary>

<br>

<div align="center">
  <img src="https://img.155155155.xyz/i/2024/09/66f2d4b70416c.webp" width="30%" />
  <img src="https://img.155155155.xyz/i/2024/09/66f2d4d6ca7ec.webp" width="30%" />
  <img src="https://img.155155155.xyz/i/2024/09/66f3f92973ad1.webp" width="30%" />
</div>

</details>

## 🚀 部署与配置

### 1. 前置条件

- **Python**: `>= 3.12`
- **包管理器**: 推荐使用 [uv](https://docs.astral.sh/uv/) 进行依赖管理。
- **手动运行**: 需确保系统已安装 `ffmpeg` (用于音视频处理)。

### 2. 配置文件

配置主要分为**环境变量**与**平台规则配置**两部分。

#### 2.1 环境变量 (`.env`)

首先复制配置文件模板：

```bash
# Linux / macOS
cp .env.exa .env

# Windows PowerShell
Copy-Item .env.exa .env
```

根据需求编辑 `.env` 文件：

| 参数           | 必填 | 说明                                                               |
|:-------------|:--:|:-----------------------------------------------------------------|
| `API_ID`     | ✅  | Telegram API ID，登录 [my.telegram.org](https://my.telegram.org) 获取 |
| `API_HASH`   | ✅  | Telegram API Hash，同上获取                                           |
| `BOT_TOKEN`  | ✅  | 机器人 Token，向 [@BotFather](https://t.me/BotFather) 申请              |
| `BOT_PROXY`  | 🔲 | Bot 连接 TG 使用的代理，例：`http://127.0.0.1:7890`                        |
| `DATA_PATH`  | 🔲 | 数据存储目录，默认 `data`                                                 |
| `CACHE_TIME` | 🔲 | 缓存有效时间（秒），默认 `2592000`（30 天），`0` 为永久缓存                           |
| `DOUYIN_API` | 🔲 | 自定义抖音 API 解析服务地址                                                 |

#### 2.2 平台代理与 Cookie (`platform_config.yaml`)

用于配置各平台的代理和 Cookie。

复制模板：

```bash
# Linux / macOS
cp data/config/platform_config.yaml.exa data/config/platform_config.yaml

# Windows PowerShell
Copy-Item data/config/platform_config.yaml.exa data/config/platform_config.yaml
```

**核心配置逻辑：**

- **代理优先级**：`禁用代理` > `平台代理` > `全局默认代理` > `直连`

<details>
<summary><b>点击查看配置示例</b></summary>

```yaml
default_parser_proxies: http://127.0.0.1:7890
default_downloader_proxies:
  - http://127.0.0.1:7890

platforms:
  twitter:
    cookies:
      - auth_token=xxxx; ct0=xxxx  # 配置 Cookie
  bilibili:
    disable_parser_proxy: true     # B站解析不走代理
    downloader_proxies:
      - http://127.0.0.1:7890      # B站下载指定代理池
```

</details>

### 3. 开始运行

#### 🐳 方式一：Docker 镜像部署（推荐）

```bash
docker pull ghcr.io/z-mio/parse_hub_bot:latest

docker run -d \
  --restart=always \
  --env-file .env \
  -v ./logs:/app/logs \
  -v ./data:/app/data \
  --name parse-hub-bot \
  ghcr.io/z-mio/parse_hub_bot:latest
```

常用容器管理命令：

| 操作    | 命令                                                        |
|:------|:----------------------------------------------------------|
| 查看日志  | `docker logs -f parse-hub-bot`                            |
| 查看状态  | `docker ps -a --filter "name=parse-hub-bot"`              |
| 停止并移除 | `docker stop parse-hub-bot && docker rm -f parse-hub-bot` |
| 更新镜像  | `docker pull ghcr.io/z-mio/parse_hub_bot:latest`          |

#### 🛠️ 方式二：本地构建 Docker 镜像

基于当前仓库代码构建，可使用 `start.sh` 管理脚本：

```bash
bash start.sh            # 🚀 构建并启动（等价于 start）
bash start.sh stop       # ⏹️ 停止并移除容器
bash start.sh restart    # 🔄 重启容器
bash start.sh logs       # 📝 实时查看日志
bash start.sh status     # 📊 查看容器运行状态
```

#### 💻 方式三：手动运行

```bash
# 1. 安装项目依赖 (基于 uv)
uv sync

# 2. 启动机器人
uv run bot.py
```

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=z-mio/Parse_Hub_Bot&type=Date)](https://star-history.com/#z-mio/Parse_Hub_Bot&Date)

## 🤝 参与贡献

欢迎提交 Pull Request 或 Issue！

- 核心解析相关请前往 [ParseHub](https://github.com/z-mio/ParseHub)。
- Bug 反馈请附上相关 URL 和日志信息。

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 协议开源。
