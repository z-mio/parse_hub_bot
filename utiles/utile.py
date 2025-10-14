import asyncio
import hashlib
import io

from PIL import Image
from pyrogram import Client


async def schedule_delete_messages(
    client: Client, chat_id: int, message_ids: int | list, delay_seconds: int = 2
):
    """定时删除消息"""

    await asyncio.sleep(delay_seconds)

    try:
        await client.delete_messages(chat_id, message_ids)
    except Exception:
        ...


def progress(current, total, status):
    if total == 0:
        return status

    text = None
    if total >= 100:
        if round(current * 100 / total, 1) % 25 == 0:
            text = f"下 载 中... | {status}"
    else:
        if (current + 1) % 3 == 0 or (current + 1) == total:
            text = f"下 载 中... | {status}"
    return text


def encrypt(text: str):
    """hash加密"""
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    return md5.hexdigest()


def img2webp(img):
    with Image.open(img) as pil_img:
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")
        output = io.BytesIO()
        pil_img.save(output, format="WEBP")
        output.seek(0)
    return output
