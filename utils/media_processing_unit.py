"""媒体处理器 — 将图片/视频转换为 Telegram 兼容格式"""

import asyncio
import math
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path

from haishoku.haishoku import Haishoku
from PIL import Image, ImageOps

from utils.helpers import run_cmd

# ------------------------------------------------------------------ #
#  公共数据结构
# ------------------------------------------------------------------ #


@dataclass
class MediaProcessResult:
    """统一处理结果"""

    output_paths: list[Path]
    temp_dir: Path | None = None


# ------------------------------------------------------------------ #
#  主类
# ------------------------------------------------------------------ #


class MediaProcessingUnit:
    """媒体处理器，将媒体转换为 Telegram 兼容的格式

    Telegram 限制：
    - 图片宽高比 / 高宽比不能超过 20:1
    - 单次最多发送 10 张图片

    用法：
        mpu = MediaProcessingUnit(output_dir=Path("./output"))
        result = await mpu.process("media.mp4")
    """

    def __init__(
        self,
        output_dir: str | Path,
        segment_height: int = 1400,
        medium_threshold: int = 2,
        overlap: int = 100,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.segment_height = segment_height
        self.medium_threshold = medium_threshold
        self.overlap = overlap

    # ------------------------------------------------------------------ #
    #  公共入口
    # ------------------------------------------------------------------ #

    async def process(self, file_path: str | Path) -> MediaProcessResult:
        media_type = self.get_media_type_by_mime(file_path)
        if media_type == "image":
            return await self.process_image(Path(file_path))
        elif media_type == "video":
            return await self.process_video(Path(file_path))
        else:
            raise ValueError("Unsupported media type")

    # ------------------------------------------------------------------ #
    #  图片处理
    # ------------------------------------------------------------------ #

    async def process_image(self, file_path: Path) -> MediaProcessResult:
        ext = file_path.suffix.lower()
        if ext in [".heif", ".heic", ".avif"]:
            new_img = await asyncio.to_thread(self._img2webp, file_path)
        else:
            new_img = None

        ff = new_img or file_path
        result = self._adapt_image(ff)
        if not result:
            return MediaProcessResult(output_paths=[ff])
        else:
            if new_img:
                os.remove(new_img)
            return result

    def _adapt_image(self, file_path: Path) -> MediaProcessResult | None:
        """分析图片尺寸并做填充/切割，返回 MediaProcessResult"""
        file_path = Path(file_path)
        with Image.open(file_path) as img:
            w, h = img.width, img.height
            wh_ratio = w / h
            hw_ratio = h / w

            # 横图
            if wh_ratio <= 20 and w > h:
                return None
            if wh_ratio > 20:
                padding = self._calc_padding_horizontal(w, h)
                return self._pad_image(file_path, img, padding)

            # 竖图
            if hw_ratio <= 5 or (w < 200 and hw_ratio < 20):
                return None
            if w < 200 and hw_ratio > 20:
                padding = self._calc_padding_vertical(w, h)
                return self._pad_image(file_path, img, padding)

            # 长图切割
            segments = h // self.segment_height
            seg_h = h // 2 if segments < self.medium_threshold else self.segment_height
            return self._split_image(file_path, seg_h)

    def _img2webp(self, file_path: Path) -> Path:
        with Image.open(file_path) as pil_img:
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            output = self.output_dir / Path(file_path).with_suffix(".webp").name
            pil_img.save(output, format="WEBP")
        return output

    # -- 图片辅助 --------------------------------------------------------- #

    @staticmethod
    def _calc_padding_horizontal(w: int, h: int) -> tuple[int, int, int, int]:
        h_padding = w // 20 - h // 2
        return 0, h_padding, 0, h_padding

    @staticmethod
    def _calc_padding_vertical(w: int, h: int) -> tuple[int, int, int, int]:
        w_padding = h // 20 - w // 2
        return w_padding, 0, w_padding, 0

    @staticmethod
    def _get_dominant_color(file_path: Path) -> tuple[int, int, int]:
        haishoku = Haishoku.loadHaishoku(str(file_path))
        return tuple(int(v * 0.8) for v in haishoku.palette[0][1])

    def _pad_image(
        self,
        file_path: Path,
        img: Image.Image,
        padding: tuple[int, int, int, int],
    ) -> MediaProcessResult:
        fill_color = self._get_dominant_color(file_path)
        padded = ImageOps.expand(img, padding, fill=fill_color)
        out_path = self.output_dir / f"padded_{time.time_ns()}.png"
        padded.save(out_path)
        return MediaProcessResult(
            output_paths=[out_path],
        )

    def _split_image(self, file_path: Path, segment_height: int) -> MediaProcessResult:
        temp_dir = self.output_dir / f"split_{time.time_ns()}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        segments = self._do_split(file_path, temp_dir, segment_height)
        return MediaProcessResult(
            output_paths=segments,
            temp_dir=temp_dir,
        )

    def _do_split(
        self,
        input_path: Path,
        output_dir: Path,
        segment_height: int,
    ) -> list[Path]:
        img = Image.open(input_path)
        width, height = img.size
        num_segments = math.ceil(height / segment_height)
        result = []
        for i in range(num_segments):
            top = i * segment_height - (self.overlap if i != 0 else 0)
            bottom = min((i + 1) * segment_height, height)
            segment = img.crop((0, top, width, bottom))
            out_path = output_dir / f"segment_{i + 1:03d}.png"
            segment.save(out_path)
            result.append(out_path)
        img.close()
        return result

    # ------------------------------------------------------------------ #
    #  视频处理
    # ------------------------------------------------------------------ #

    async def process_video(self, file_path: Path) -> MediaProcessResult:
        codec = await self.get_video_codec(file_path)
        if codec != "h264":
            new_video = await self.ensure_h264(file_path)
        else:
            new_video = None

        ff = new_video or file_path
        video_size = os.path.getsize(ff)
        if video_size > 1024 * 1024 * 1024 * 2:  # 2G
            output_paths, output_dir = await self.split_video(ff, self.output_dir)
            if new_video:
                os.remove(new_video)
            return MediaProcessResult(output_paths=output_paths, temp_dir=output_dir)
        return MediaProcessResult(output_paths=[ff])

    @staticmethod
    async def get_video_codec(file_path: Path) -> str:
        out = await run_cmd(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        )
        return out.lower() if out else ""

    @staticmethod
    async def get_duration(file_path: Path) -> float:
        out = await run_cmd(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        )
        return float(out) if out else 0.0

    @staticmethod
    async def ensure_h264(file_path: Path) -> Path:
        out = file_path.with_stem(file_path.stem + "_h264")
        cmd = [
            "ffmpeg",
            "-i",
            str(file_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-y",
            str(out),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        if out.exists() and out.stat().st_size > 0:
            return out
        return file_path

    async def split_video(
        self,
        file_path: Path,
        output_dir: Path,
        size_limit: int = 2_000_000_000,
        ffmpeg_args: str = "-c copy",
        keep_sec: float = 1.0,
    ) -> tuple[list[Path], Path]:
        base = file_path.stem
        output_dir = output_dir.joinpath(f"{base}_split")
        output_dir.mkdir(parents=True, exist_ok=True)
        ext = file_path.suffix.lstrip(".")
        total_duration = int(await self.get_duration(file_path))
        cur = 0
        part = 1
        output_paths = []

        while cur < total_duration:
            out_file = output_dir / f"{base}_part_{part:03d}.{ext}"
            output_paths.append(out_file)
            cmd = [
                "ffmpeg",
                "-ss",
                str(cur),
                "-i",
                str(file_path),
                "-fs",
                str(size_limit),
                *ffmpeg_args.split(),
                "-y",
                str(out_file),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            new_dur = int(await self.get_duration(out_file))
            if new_dur <= 0:
                break
            cur += new_dur
            if cur < total_duration:
                cur = max(cur - int(keep_sec), 0)
            part += 1
        return output_paths, output_dir

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_media_type_by_mime(file_path: str | Path) -> str:
        mime, _ = mimetypes.guess_type(str(file_path))
        if mime:
            if mime.startswith("image/"):
                return "image"
            elif mime.startswith("video/"):
                return "video"
        return "unknown"
