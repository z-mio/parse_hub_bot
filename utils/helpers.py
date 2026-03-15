import asyncio


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
