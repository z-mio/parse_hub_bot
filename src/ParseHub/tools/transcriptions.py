import asyncio
import shutil
from dataclasses import dataclass
from typing import Literal

from aiofiles.tempfile import TemporaryDirectory

from ..utiles.whisper_api import WhisperAPI
from pydub import AudioSegment
from openai import AsyncOpenAI
import math
import os
from pathlib import Path


class Transcriptions:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url

    async def transcription(
        self, audio_path: str, model: Literal["openai", "fast_whisper"] = "openai"
    ):
        match model:
            case "openai":
                m = self.openai
            case "fast_whisper":
                m = self.fast_whisper
            case _:
                raise ValueError("Invalid model")

        async with TemporaryDirectory() as temp_dir:
            await self.split_audio(audio_path, temp_dir)
            tasks = [m(Path(temp_dir, f)) for f in os.listdir(temp_dir)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            text, chucks = "", []
            for r in results:
                if not isinstance(r, BaseException):
                    text += r.text
                    chucks.extend(r.chucks)
            return TranscriptionResult(text=text, chucks=chucks)

    async def openai(self, audio_path: str):
        oai = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        audio = open(audio_path, "rb")
        r = await oai.audio.transcriptions.create(
            model="whisper-1", file=audio, response_format="verbose_json"
        )
        chucks = [
            Chunk(begin=i["start"], end=i["end"], text=i["text"]) for i in r.segments
        ]
        tr = TranscriptionResult(text=r.text, chucks=chucks)
        audio.close()

        return tr

    async def fast_whisper(self, audio_path: str):
        wi = WhisperAPI(api_key=self.api_key, base_url=self.base_url)
        r = await wi.transcribe(audio_path)
        return TranscriptionResult(text=r.text, chucks=r.chucks)

    @staticmethod
    async def split_audio(
        file: str | Path, op_dir: str | Path, chunk_size_mb: int = 20
    ):
        """音频切片，并输出到指定文件夹"""
        file_size_bytes = os.path.getsize(file)
        chunk_size_bytes = chunk_size_mb * 1024 * 1024
        audio = AudioSegment.from_file(file)
        Path(op_dir).mkdir(parents=True, exist_ok=True)

        if file_size_bytes <= chunk_size_bytes:
            return shutil.copy2(file, Path(op_dir, "chunk_1.mp3"))

        duration_ms = len(audio)
        chunk_duration_ms = math.floor(
            duration_ms * (chunk_size_bytes / file_size_bytes)
        )

        async def process_chunk(c, op):
            await asyncio.to_thread(c.export, op, "mp3")

        tasks = []
        for i, chunk_start in enumerate(range(0, duration_ms, chunk_duration_ms)):
            chunk_end = chunk_start + chunk_duration_ms
            chunk_start = chunk_start if not i else chunk_start - 1000  # 往前加1秒，避免边界问题
            chunk = audio[chunk_start:chunk_end]

            output_filename = f"chunk_{i + 1}.mp3"
            output_path = os.path.join(op_dir, output_filename)
            tasks.append(process_chunk(chunk, output_path))

        await asyncio.gather(*tasks)


@dataclass
class TranscriptionResult:
    text: str
    chucks: list["Chunk"]


@dataclass
class Chunk:
    begin: float
    end: float
    text: str
