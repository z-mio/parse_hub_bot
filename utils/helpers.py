import asyncio
import hashlib


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
