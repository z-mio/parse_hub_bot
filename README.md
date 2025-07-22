# ParseHubBot

---

**Telegram聚合解析Bot, 支持AI总结, 支持内联模式**  
**Telegram aggregation analysis Bot, supports AI summary, supports inline mode**

部署好的Bot: [@ParseHubBot](https://t.me/ParseHubBot)目前支持的平台:

- `抖音视频|图文`
- `哔哩哔哩视频|动态`
- `YouTube`
- `YouTube Music`
- `TikTok视频|图文`
- `小红书视频|图文`
- `Twitter视频|图文`
- `百度贴吧图文|视频`
- `Facebook视频`
- `微博视频|图文`
- `Instagram视频|图文`
- [查看更多...](https://github.com/z-mio/ParseHub)

![](https://img.155155155.xyz/i/2024/09/66f2d4b70416c.webp)
![](https://img.155155155.xyz/i/2024/09/66f2d4d6ca7ec.webp)

## 部署Bot

### 修改配置

将 `.env.exa` 复制为 `.env`, 并修改配置

| 参数                        | 说明                                             |
|---------------------------|------------------------------------------------|
| `API_HASH`, `API_ID`      | 登录 https://my.telegram.org 获取                  |
| `BOT_TOKEN`               | 在 @BotFather 获取                                |
| `BOT_PROXY`               | 海外服务器无需填写                                      |
| `PARSER_PROXY`            | 解析时使用的代理                                       |
| `DOWNLOADER_PROXY`        | 下载时使用的代理                                       |
| `DOUYIN_API`              | 你部署的抖音API地址, 默认: https://douyin.wtf            |
| `AI_SUMMARY`              | 是否开启AI总结                                       |
| `API_KEY`                 | openai 密钥                                      |
| `BASE_URL`                | openai api地址                                   |
| `MODEL`                   | AI总结使用的模型                                      |
| `PROMPT`                  | AI总结提示词                                        |
| `TRANSCRIPTIONS_PROVIDER` | 语音转文本模型提供商 支持: `openai`,`azure`,`fast_whisper` | 
| `TRANSCRIPTIONS_BASE_URL` | 语音转文本 API端点                                    |
| `TRANSCRIPTIONS_API_KEY`  | 语音转文本 API密钥                                    |
| `CACHE_TIME`              | 解析结果缓存时间, 单位: 秒, 0为不缓存, 默认缓存10分钟               |

### 开始部署

#### Docker (推荐):

**在项目根目录运行:**

```shell
sudo sh start.sh
```

停止Bot: `docker stop parse-hub-bot`  
重启Bot: `docker restart parse-hub-bot`

#### 直接运行:

**在项目根目录运行:**

```shell
apt install python3-pip -y
pip install uv --break-system-packages
uv venv --python 3.12
uv sync
```

**启动bot**

   ```shell
   uv run bot.py
   ```

**设置命令列表**
私聊bot发送指令 `/menu`

## 使用

普通使用: 发送分享链接给bot即可
内联使用: 任意聊天窗口输入: `@bot用户名 链接`
![](https://img.155155155.xyz/i/2024/09/66f3f92973ad1.webp)

## 相关项目

- [z-mio/ParseHub](https://github.com/z-mio/ParseHub)

## 鸣谢

- [OhMyGPT](https://www.ohmygpt.com)
- [KurimuzonAkuma/pyrogram](https://github.com/KurimuzonAkuma/pyrogram)
