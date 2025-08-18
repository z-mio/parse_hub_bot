import httpx
from tenacity import retry, stop_after_attempt


class ImgHost:
    def __init__(self, proxies: httpx.Proxy = None):
        self.async_client = httpx.AsyncClient(proxy=proxies)

    @retry(stop=stop_after_attempt(5))
    async def litterbox(self, filename: str):
        host_url = "https://litterbox.catbox.moe/resources/internals/api.php"

        file = open(filename, "rb")
        try:
            data = {
                "reqtype": "fileupload",
                "time": "1h",
            }
            response = await self.async_client.post(
                host_url, data=data, files={"fileToUpload": file}
            )
        finally:
            file.close()

        return response.text

    def __aexit__(self, exc_type, exc_val, exc_tb):
        self.async_client.aclose()
