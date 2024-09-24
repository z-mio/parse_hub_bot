"""
项目地址: https://github.com/JigsawStack/insanely-fast-whisper-api/tree/472d70426115168c29e46484edeb85978ed7e805
"""
import asyncio

import httpx
from dataclasses import dataclass


class WhisperAPI:
    def __init__(self, base_url: str, api_key: str = None):
        self.api_key = api_key
        self.base_url = base_url

    async def transcribe(self, audio_paht: str) -> "WhisperResult":
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                file = open(audio_paht, "rb")
                result = await client.post(
                    url=f"{self.base_url}/upload",
                    headers={"x-admin-api-key": self.api_key} if self.api_key else {},
                    files={"audio": file},
                    data={"batch_size": 24},
                )
                result.raise_for_status()
                data = result.json()
                wi = WhisperResult.parse(data)
        except Exception as e:
            raise Exception(f"语音转文字失败: {e}")
        else:
            return wi


@dataclass
class WhisperResult:
    text: str
    chucks: list["Chunk"]
    status: str
    task_id: str

    @staticmethod
    def parse(data: dict) -> "WhisperResult":
        text = data["output"]["text"]
        chucks = [Chunk.parse(chunk) for chunk in data["output"]["chunks"]]
        status = data["status"]
        task_id = data["task_id"]
        return WhisperResult(text, chucks, status, task_id)


@dataclass
class Chunk:
    begin: float
    end: float
    text: str

    @staticmethod
    def parse(data: dict) -> "Chunk":
        begin = data["timestamp"][0]
        end = data["timestamp"][1]
        text = data["text"]
        return Chunk(begin, end, text)


if __name__ == "__main__":
    api = WhisperAPI("http://127.0.0.1:6006")
    result = asyncio.run(
        api.transcribe(
            r"D:\PycharmProjects\ParseHub\src\test\downloads\1725616436283858100.mp4"
        )
    )
    print(result)
