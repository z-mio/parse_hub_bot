import asyncio
import hashlib

from pyrogram import Client


async def schedule_delete_messages(client: Client, chat_id: int, message_ids: int | list, delay_seconds: int = 2):
    """定时删除消息"""

    await asyncio.sleep(delay_seconds)

    try:
        await client.delete_messages(chat_id, message_ids)
    except Exception:
        ...


def encrypt(text: str):
    """hash加密"""
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    return md5.hexdigest()


async def run_cmd(*cmd: str, timeout: float = 30) -> str:
    """运行外部命令并异步读取输出"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return ""
    return stdout.decode().strip()
