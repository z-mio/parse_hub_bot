import asyncio
import tarfile
from pathlib import Path
from typing import overload


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


@overload
def to_list[T](v: list[T]) -> list[T]: ...


@overload
def to_list[T](v: T) -> list[T]: ...


def to_list(v):
    return v if isinstance(v, list) else [v]


def pack_dir_to_tar_gz(dir_path: str | Path, output_path: str | Path | None = None) -> Path:
    """
    将目录打包为 tar.gz，返回压缩包路径。

    Args:
        dir_path: 要打包的目录
        output_path: 输出压缩包路径；不传则默认生成同名 .tar.gz

    Returns:
        生成的 tar.gz 文件路径
    """
    source_dir = Path(dir_path).resolve()
    if not source_dir.is_dir():
        raise ValueError(f"不是有效目录: {source_dir}")

    if output_path is None:
        output_path = source_dir.with_suffix(".tar.gz")
    else:
        output_path = Path(output_path).resolve()

    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)

    return output_path
