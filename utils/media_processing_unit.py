"""媒体处理器 — 将图片/视频转换为 Telegram 兼容格式"""

import asyncio
import math
import mimetypes
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from haishoku.haishoku import Haishoku
from loguru import logger
from PIL import Image, ImageOps
from PIL.Image import Resampling

from utils.helpers import run_cmd


@dataclass
class MediaProcessResult:
    """统一处理结果"""

    output_paths: list[Path]
    temp_dir: Path | None = None


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
        logger: Callable = logger.info,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.segment_height = segment_height
        self.medium_threshold = medium_threshold
        self.overlap = overlap
        self.logger = logger

    # ------------------------------------------------------------------ #
    #  公共入口
    # ------------------------------------------------------------------ #

    async def process(self, file_path: str | Path) -> MediaProcessResult:
        media_type = self.get_media_type_by_mime(file_path)
        self.logger(f"开始处理媒体: path={file_path}, type={media_type}")
        if media_type == "image":
            return await self.process_image(Path(file_path))
        elif media_type == "video":
            return await self.process_video(Path(file_path))
        else:
            raise ValueError(f"Unsupported media type: {file_path}")

    # ------------------------------------------------------------------ #
    #  图片处理
    # ------------------------------------------------------------------ #

    async def process_image(self, file_path: Path) -> MediaProcessResult:
        ext = file_path.suffix.lower()
        needs_convert = ext in {".heif", ".heic", ".avif"}
        converted: Path | None = None

        if needs_convert:
            self.logger(f"图片格式需转换: {ext} -> webp")
            converted = await asyncio.to_thread(self._img2webp, file_path)

        source = converted or file_path

        downscaled = self._downscale_image(source)
        if downscaled:
            if converted and converted.exists():
                os.remove(converted)
                converted = None
            source = downscaled

        try:
            result = self._adapt_image(source)
        except Exception as e:
            if downscaled and downscaled.exists():
                os.remove(downscaled)
            if converted and converted.exists():
                os.remove(converted)
            raise Exception(e) from e

        if result is None:
            self.logger(f"图片无需额外处理: {source}")
            return MediaProcessResult(output_paths=[source])
        else:
            if downscaled and downscaled.exists():
                self.logger(f"删除中间缩放文件: {downscaled}")
                os.remove(downscaled)
            if converted and converted.exists():
                self.logger(f"删除中间 webp 文件: {converted}")
                os.remove(converted)
            return result

    def _adapt_image(self, file_path: Path) -> MediaProcessResult | None:
        """分析图片尺寸并做填充 / 切割，返回 None 表示无需处理"""
        with Image.open(file_path) as img:
            w, h = img.width, img.height

        wh_ratio = w / h
        hw_ratio = h / w
        self.logger(f"图片尺寸: {w}x{h}, wh_ratio={wh_ratio:.2f}, hw_ratio={hw_ratio:.2f}")

        if w >= h:
            # 横图
            if wh_ratio <= 20:
                self.logger("横图比例正常，跳过处理")
                return None
            self.logger("横图比例超限，需要填充")
            padding = self._calc_padding_horizontal(w, h)
            with Image.open(file_path) as img:
                return self._pad_image(file_path, img, padding)
        else:
            # 竖图
            if hw_ratio <= 5 or (w < 200 and hw_ratio < 20):
                self.logger("竖图比例正常，跳过处理")
                return None
            if w < 200 and hw_ratio > 20:
                self.logger("窄竖图比例超限，需要填充")
                padding = self._calc_padding_vertical(w, h)
                with Image.open(file_path) as img:
                    return self._pad_image(file_path, img, padding)
            # 长图切割
            segments = h // self.segment_height
            seg_h = h // 2 if segments < self.medium_threshold else self.segment_height
            self.logger(f"长图切割: segments={segments}, seg_h={seg_h}")
            return self._split_image(file_path, seg_h)

    def _img2webp(self, file_path: Path) -> Path:
        with Image.open(file_path) as pil_img:
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            output = self.output_dir / file_path.with_suffix(".webp").name
            pil_img.save(output, format="WEBP")
        self.logger(f"webp 转换完成: {output}")
        return output

    def _downscale_image(self, file_path: Path, max_side: int = 2560) -> Path | None:
        """若图片任一边超过 max_side，等比缩放至长边为 max_side，返回新文件路径；无需缩放返回 None"""
        with Image.open(file_path) as img:
            w, h = img.size
            if max(w, h) <= max_side:
                return None
            scale = max_side / max(w, h)
            new_w, new_h = int(w * scale), int(h * scale)
            self.logger(f"图片长边超限({max(w, h)}px > {max_side}px)，缩放: {w}x{h} -> {new_w}x{new_h}")
            resized = img.resize((new_w, new_h), Resampling.LANCZOS)
            out_path = self.output_dir / f"downscaled_{time.time_ns()}{file_path.suffix}"
            resized.save(out_path)
        return out_path

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
    def _get_dominant_color(file_path: Path) -> tuple[int, ...]:
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
        self.logger(f"填充完成: padding={padding}, color={fill_color}, output={out_path}")
        return MediaProcessResult(output_paths=[out_path])

    def _split_image(self, file_path: Path, segment_height: int) -> MediaProcessResult:
        temp_dir = self.output_dir / f"split_{time.time_ns()}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        segments = self._do_split(file_path, temp_dir, segment_height)
        self.logger(f"图片切割完成: {len(segments)} 段, output_dir={temp_dir}")
        return MediaProcessResult(output_paths=segments, temp_dir=temp_dir)

    def _do_split(
        self,
        input_path: Path,
        output_dir: Path,
        segment_height: int,
    ) -> list[Path]:
        with Image.open(input_path) as img:
            width, height = img.size
            num_segments = math.ceil(height / segment_height)
            self.logger(f"切割参数: size={width}x{height}, segment_h={segment_height}, num={num_segments}")
            result: list[Path] = []
            for i in range(num_segments):
                top = i * segment_height - (self.overlap if i != 0 else 0)
                bottom = min((i + 1) * segment_height, height)
                segment = img.crop((0, top, width, bottom))
                out_path = output_dir / f"segment_{i + 1:03d}.png"
                segment.save(out_path)
                result.append(out_path)
        return result

    # ------------------------------------------------------------------ #
    #  视频处理
    # ------------------------------------------------------------------ #

    async def process_video(self, file_path: Path) -> MediaProcessResult:
        codec = await self.get_video_codec(file_path)
        self.logger(f"视频编码: codec={codec}, path={file_path}")

        converted: Path | None = None
        if codec != "h264":
            self.logger("编码非 h264，开始转码")
            converted = await self.ensure_h264(file_path)
            self.logger(f"转码完成: {converted}")

        source = converted or file_path
        video_size = source.stat().st_size
        self.logger(f"视频大小: {video_size / 1024 / 1024:.1f} MB")

        if video_size > 2 * 1024**3:  # 2 GiB
            self.logger("视频超过 2 GiB，开始分割")
            output_paths, output_dir = await self.split_video(source, self.output_dir)
            if converted:
                os.remove(converted)
            return MediaProcessResult(output_paths=output_paths, temp_dir=output_dir)

        return MediaProcessResult(output_paths=[source])

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
        return out.strip().lower() if out else ""

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
        return float(out.strip()) if out else 0.0

    async def ensure_h264(self, file_path: Path) -> Path:
        out = self.output_dir / (file_path.stem + "_h264" + file_path.suffix)
        duration = await self.get_duration(file_path)
        height = await self._get_video_height(file_path)

        cmd = self._build_sw_transcode_cmd(file_path, out, duration, height)

        self.logger(f"h264 转码: {file_path.name} -> {out.name}, duration={duration:.0f}s, encoder=SW:libx264")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if out.exists() and out.stat().st_size > 0:
            self.logger(f"h264 转码成功: size={out.stat().st_size / 1024 / 1024:.1f}MB")
            return out

        self.logger(f"h264 转码失败，返回原文件: {file_path}")
        return file_path

    @staticmethod
    async def _get_video_height(file_path: Path) -> int:
        out = await run_cmd(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=height",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
        )
        return int(out.strip()) if out and out.strip().isdigit() else 0

    def _build_sw_transcode_cmd(self, file_path: Path, out: Path, duration: float, height: int) -> list[str]:
        if duration <= 30:
            preset, crf = "slow", "18"
        elif duration <= 60:
            preset, crf = "medium", "20"
        elif duration <= 600:
            preset, crf = "fast", "23"
        elif duration <= 1800:
            preset, crf = "veryfast", "26"
        else:
            preset, crf = "ultrafast", "28"

        scale = ["-vf", "scale=-2:720"] if duration > 1800 and height > 720 else []
        self.logger(f"SW 转码策略: preset={preset}, crf={crf}, scale={'720p' if scale else 'original'}")

        return [
            "ffmpeg",
            "-i",
            str(file_path),
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            crf,
            *scale,
            "-c:a",
            "aac",
            "-y",
            str(out),
        ]

    async def split_video(
        self,
        file_path: Path,
        output_dir: Path,
        size_limit: int = 2_000_000_000,
        ffmpeg_args: list[str] | None = None,
        keep_sec: float = 1.0,
    ) -> tuple[list[Path], Path]:
        if ffmpeg_args is None:
            ffmpeg_args = ["-c", "copy"]

        base = file_path.stem
        split_dir = output_dir / f"{base}_split"
        split_dir.mkdir(parents=True, exist_ok=True)
        ext = file_path.suffix.lstrip(".")
        total_duration = int(await self.get_duration(file_path))
        self.logger(f"视频分割: duration={total_duration}s, size_limit={size_limit}")

        cur, part, output_paths = 0, 1, []
        while cur < total_duration:
            out_file = split_dir / f"{base}_part_{part:03d}.{ext}"
            output_paths.append(out_file)
            cmd = [
                "ffmpeg",
                "-ss",
                str(cur),
                "-i",
                str(file_path),
                "-fs",
                str(size_limit),
                *ffmpeg_args,
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
            self.logger(f"分割 part {part}: offset={cur}s, duration={new_dur}s, file={out_file}")
            if new_dur <= 0:
                break
            cur += new_dur
            if cur < total_duration:
                cur = max(cur - int(keep_sec), 0)
            part += 1

        self.logger(f"视频分割完成: {len(output_paths)} 段")
        return output_paths, split_dir

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_media_type_by_mime(file_path: str | Path) -> str:
        mime, _ = mimetypes.guess_type(str(file_path))
        if mime:
            if mime.startswith("image/"):
                return "image"
            if mime.startswith("video/"):
                return "video"
        return "unknown"


async def main():
    mpu = MediaProcessingUnit(output_dir=Path(r"D:\Downloads\新建文件夹"))
    result = await mpu.process(r"D:\Downloads\36751083810-1-30066.mp4")
    print(result.output_paths)


if __name__ == "__main__":
    asyncio.run(main())
