import os
import re
from pathlib import Path
from typing import Callable

import aiofiles
import httpx
from httpx._types import ProxiesTypes


async def download_file(
    url: str,
    save_path: str | Path = None,
    *,
    proxies: ProxiesTypes = None,
    progress: Callable = None,
    progress_args: tuple = (),
) -> str:
    """
    :param url: 下载链接
    :param save_path: 保存路径, 默认保存到downloads文件夹, 如果路径以/结尾，则自动获取文件名
    :param proxies: 代理
    :param progress: 下载进度回调函数
    :param progress_args: 下载进度回调函数参数
    :return: 文件路径

    .. note::
        下载进度回调函数签名: async def progress(current: int, total: int, *args) -> None:
    """

    async with httpx.AsyncClient(proxies=proxies) as client:
        save_dir, filename = os.path.split(save_path) if save_path else (None, None)
        save_dir = (
            Path(os.path.abspath(save_dir))
            if save_dir
            else Path.cwd().joinpath("downloads")
        )
        filename = filename or await get_file_name_form_url(url, client)

        if not filename:
            raise ValueError("无法获取文件名")

        save_path = save_dir.joinpath(filename)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with client.stream("GET", url, follow_redirects=True) as r:
                r.raise_for_status()

                total_size = int(r.headers.get("Content-Length", 0))
                current = 0

                async with aiofiles.open(save_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=10240):
                        await f.write(chunk)
                        current += len(chunk)
                        if progress:
                            await progress(current, total_size, *progress_args)
        except httpx.ConnectTimeout:
            raise DownloadError("连接超时")
        except Exception as e:
            raise DownloadError(f"下载失败: {e}")

    return str(save_path)


async def get_file_name_form_url(url: str, client: httpx.AsyncClient):
    response = await client.head(url, follow_redirects=True)
    response.raise_for_status()
    if content_disposition := response.headers.get("content-disposition"):
        if filename_match := re.findall("filename=(.+)", content_disposition):
            return filename_match[0]
    return url.removesuffix("/").split("/")[-1]


class DownloadError(Exception):
    pass
