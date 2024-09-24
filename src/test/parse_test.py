import asyncio

from loguru import logger

from src.ParseHub.main import ParseHub
from dotenv import load_dotenv

load_dotenv("/.env")


@logger.catch
async def test_parse_hub():
    ph = ParseHub()
    test = {
        "bilibili": "https://www.bilibili.com/video/BV1GfHWeTEWa",
        "youtube": "https://www.youtube.com/watch?v=KfOEabr38WU",
        "twitter": "https://twitter.com/aobuta_anime/status/1827284717848424696",
        "douyin": "https://www.douyin.com/video/7411441695126048052",
        "tieba": "http://c.tieba.baidu.com/p/8985515891",
        "xhs": "https://www.xiaohongshu.com/explore/66ef879f000000001201308e",
        "facebook": "https://www.facebook.com/share/v/KrPrU7A8Jf4i1TxE/",
        "weibo": "https://weibo.com/3208333150/Ow0iEbEX0",
    }
    # for k, v in test.items():
    #     result = await ph.parse(v)
    #     print(f"{k} {result.title}")
    r = await ph.parse(test["weibo"])
    print(r.desc)
    # m = await r.download()
    # print(m)
    # summary = await m.summary()
    # print(summary)


if __name__ == "__main__":
    asyncio.run(test_parse_hub())
