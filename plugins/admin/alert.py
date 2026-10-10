from pyrogram import Client
from pyrogram.errors import RPCError

from core import bs
from db import get_session
from i18n import t_
from log import logger
from plugins.admin.render import build_cookie_alert
from services import CookieAlert, UserService

logger = logger.bind(name="CookieAlert")


async def send_cookie_alert(cli: Client, alert: CookieAlert) -> None:
    for uid in bs.admin_ids:
        async with get_session() as session:
            _t = t_[await UserService(session).get_lang(uid)]
        try:
            await cli.send_rich_message(uid, build_cookie_alert(_t, alert))
        except RPCError as e:
            logger.warning(f"向管理员 {uid} 发送 cookie 失效通知失败: {e}")
