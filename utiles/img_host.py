import asyncio
import os
import shutil
from pathlib import Path

import aiofiles
import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

from config.config import TEMP_DIR
from log import logger


class ImgHost:
    def __init__(self, proxy: httpx.Proxy | str = None):
        self.proxy = proxy
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
    async def _to_file(self, filename_or_url: str | Path):
        if str(filename_or_url).startswith("http"):
            response = await self._get_client.get(filename_or_url)
            filename = filename_or_url.split("/")[-1]
            async with aiofiles.open(filename, "wb") as f:
                await f.write(response.content)
            return filename
        else:
            tmp_name = TEMP_DIR / f"tmp_{Path(filename_or_url).name}"
            shutil.copy2(filename_or_url, tmp_name)
            return tmp_name

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    async def catbox(self, filename_or_url: str | Path):
        host_url = "https://catbox.moe/user/api.php"
        filename = await self._to_file(filename_or_url)

        file = open(filename, "rb")
        try:
            data = {
                "reqtype": "fileupload",
                "userhash": "",
            }
            response = await self._get_client.post(host_url, data=data, files={"fileToUpload": file})
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error("catbox 图片上传失败, 以下为错误信息")
            raise e
        finally:
            file.close()
            os.remove(filename)

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    async def litterbox(self, filename_or_url: str | Path):
        host_url = "https://litterbox.catbox.moe/resources/internals/api.php"
        filename = await self._to_file(filename_or_url)
        file = open(filename, "rb")
        try:
            data = {
                "reqtype": "fileupload",
                "fileNameLength": 16,
                "time": "72h",
            }
            response = await self._get_client.post(host_url, data=data, files={"fileToUpload": file})
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error("litterbox 图片上传失败, 以下为错误信息")
            raise e
        finally:
            file.close()
            os.remove(filename)

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(2))
    async def zioooo(self, filename_or_url: str | Path):
        api_url = "https://img.zio.ooo/api/v2"
        filename = await self._to_file(filename_or_url)
        file = open(filename, "rb")
        try:
            group = await self._get_client.get(api_url + "/group")
            storage = group.json()["data"]["storages"][0]["id"]
            data = {
                "storage_id": storage,
            }
            response = await self._get_client.post(api_url + "/upload", data=data, files={"file": file})
            response.raise_for_status()
            j = response.json()
            if j["status"] != "success":
                raise Exception(f"zioooo 图片上传失败: {j['message']}")
            data = j["data"]
            return data["public_url"]
        except Exception as e:
            logger.error("zioooo 图片上传失败, 以下为错误信息")
            raise e
        finally:
            file.close()
            os.remove(filename)

    @property
    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(proxy=self.proxy, timeout=30)
        return self._client

    async def aclose(self):
        if self._client is not None and not getattr(self._client, "is_closed", False):
            await self._client.aclose()
            self._client = None


if __name__ == "__main__":
    print(asyncio.run(ImgHost().zioooo("https://i.iij.li/i/20250928/68d8f26f7b571.png")))
