from parsehub.types import ParseError
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from methods.tg_parse_hub import TgParseHub


@Client.on_callback_query(filters.regex("^summary_|unsummary_"))
async def ai_summary(_, cq: CallbackQuery):
    hash_url = cq.data.split("_")[1]
    ph = TgParseHub()
    try:
        result = await ph.parse(hash_url)
    except ParseError:
        # 缓存失效, 重新解析
        return
    match cq.data.split("_")[0]:
        case "summary":
            await result.ai_summary(cq)
        case "unsummary":
            await result.un_ai_summary(cq)
