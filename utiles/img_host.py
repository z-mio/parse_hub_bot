import os

import httpx
from tenacity import retry, stop_after_attempt


class ImgHost:
    def __init__(self, proxies: httpx.Proxy | str = None):
        self.async_client = httpx.AsyncClient(proxy=proxies)

    async def _to_file(self, filename_or_url):
        if str(filename_or_url).startswith("http"):
            response = await self.async_client.get(filename_or_url)
            filename = filename_or_url.split("/")[-1]
            with open(filename, "wb") as f:
                f.write(response.content)
        else:
            filename = filename_or_url
        return filename

    @retry(stop=stop_after_attempt(5))
    async def catbox(self, filename_or_url: str):
        host_url = "https://catbox.moe/user/api.php"
        filename = await self._to_file(filename_or_url)

        file = open(filename, "rb")
        try:
            data = {
                "reqtype": "fileupload",
                "userhash": "",
            }
            response = await self.async_client.post(
                host_url, data=data, files={"fileToUpload": file}
            )
            response.raise_for_status()
            return response.text
        finally:
            file.close()
            os.remove(filename)

    @retry(stop=stop_after_attempt(5))
    async def litterbox(self, filename_or_url: str):
        host_url = "https://litterbox.catbox.moe/resources/internals/api.php"
        filename = await self._to_file(filename_or_url)
        file = open(filename, "rb")
        try:
            data = {
                "reqtype": "fileupload",
                "time": "1h",
            }
            response = await self.async_client.post(
                host_url, data=data, files={"fileToUpload": file}
            )
            response.raise_for_status()
            return response.text
        finally:
            file.close()
            os.remove(filename)
