import asyncio
import os
import time

from pyrogram import Client
from pyrogram.session import Session

from core.config import ws
from log import logger

logger = logger.bind(name="Watchdog")
STOP_TIMEOUT = 30
_grace_task: asyncio.Task[None] | None = None
_disconnected_at: float | None = None


async def on_connect(_: Client, session: Session) -> None:
    """Bot 连接成功回调函数"""

    if session.is_media:
        return

    global _disconnected_at, _grace_task
    if _grace_task is not None:
        _grace_task.cancel()
        _grace_task = None

    if _disconnected_at is None:
        logger.success("Bot 开始运行...")
    else:
        disconnected_seconds = time.monotonic() - _disconnected_at
        logger.success(f"Bot 已重新连接, 断开 {disconnected_seconds:.1f} 秒")
        _disconnected_at = None


async def on_disconnect(cli: Client, session: Session) -> None:
    """Bot 断开连接回调函数"""

    global _disconnected_at, _grace_task
    if session.is_media:
        return

    if ws.exit_flag:
        if _grace_task is not None and _grace_task is not asyncio.current_task():
            _grace_task.cancel()
            _grace_task = None
        logger.info("Bot 已结束运行")
        return

    if _grace_task is not None:
        return

    if _disconnected_at is None:
        _disconnected_at = time.monotonic()
    logger.warning(f"Bot 已断开连接, 等待自动重连 (最多 {ws.reconnect_grace_seconds} 秒)")
    _grace_task = asyncio.create_task(_exit_if_not_reconnected(cli))


async def _exit_if_not_reconnected(cli: Client) -> None:
    """等待主连接恢复, 超时后结束进程"""
    global _grace_task
    await asyncio.sleep(ws.reconnect_grace_seconds)
    _grace_task = None
    logger.error(f"Bot 断开超过 {ws.reconnect_grace_seconds} 秒仍未恢复, 结束进程等待容器重启")
    try:
        await asyncio.wait_for(cli.stop(), STOP_TIMEOUT)
    except Exception as e:
        logger.exception(e)
    await logger.complete()
    # 回调任务里抛 SystemExit 不一定能结束进程, 直接非零退出交给容器重启
    os._exit(1)
