# ParseHubBot
---

**Telegram聚合解析Bot, 支持AI总结, 支持内联模式**

部署好的Bot: [@ParseHubBot](https://t.me/ParseHubBot)
目前支持的平台:

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
- 更多平台添加中...

![](https://img.155155155.xyz/i/2024/09/66f2d4b70416c.webp)
![](https://img.155155155.xyz/i/2024/09/66f2d4d6ca7ec.webp)

## 部署Bot

### 修改配置

将 `.env.exa` 复制为 `.env`, 并修改配置

| 参数                   | 说明                            |
|----------------------|-------------------------------|
| `API_HASH`, `API_ID` | 登录 https://my.telegram.org 获取 |
| `BOT_TOKEN`          | 在 @BotFather 获取               |
| `PROXY`              | 海外服务器无需填写                     |
| `DOUYIN_API`         | 你部署的抖音API地址                   |
| `XHS_API`            | 你部署的小红书API地址                  |
| `XHS_COOKIE`         | 浏览器F12打开控制台获取                 |
| `AI_SUMMARY`         | 是否开启AI总结                      |
| `API_KEY`            | openai 密钥                     |
| `BASE_URL`           | openai api地址                  |
| `MODEL`              | AI总结使用的模型                     |

- **部署抖音API**
  参考 [文档](https://github.com/Evil0ctal/Douyin_TikTok_Download_API?tab=readme-ov-file#部署方式二-docker) 部署即可

- **部署小红书API**
  参考文档: [LINK](https://reajason.github.io/xhs/basic.html#id4)
  部署:
  ```shell
  docker run -it -d -p 5005:5005 --name xhs-api reajason/xhs-api:latest
  ```
  获取 `a1` 值:
  ```shell
  docker logs xhs-api -f
  ```
  ![](https://img.155155155.xyz/i/2024/09/66f3f5dbc09cd.webp)
  将 `Cookie` 中的 `a1` 值替换即可

### 开始部署

**环境: python版本 >= 3.10**

1. **安装pip**
   ```shell
   apt install python3-pip -y
   ```

2. **安装依赖**
   ```shell
   pip3 install -r requirements.txt
   ```

3. **运行**
   ```shell
   python3 bot.py
   ```

4. **设置命令列表**
   私聊bot发送指令 `/menu`

## 使用

普通使用: 发送分享链接给bot即可
内联使用: 任意聊天窗口输入: `@bot用户名 链接`
![](https://img.155155155.xyz/i/2024/09/66f3f92973ad1.webp)

## 鸣谢

- [OhMyGPT](https://www.ohmygpt.com)
- [KurimuzonAkuma/pyrogram](https://github.com/KurimuzonAkuma/pyrogram)
- [Evil0ctal/Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API)
- [ReaJason/xhs](https://github.com/ReaJason/xhs)
- [BalconyJH/DynRender-skia](https://github.com/BalconyJH/DynRender-skia)
- [langchain-ai/langchain](https://github.com/langchain-ai/langchain)
- [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp)