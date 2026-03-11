import asyncio
import hashlib
import io
from pathlib import Path

from PIL import Image
from pyrogram import Client


async def schedule_delete_messages(client: Client, chat_id: int, message_ids: int | list, delay_seconds: int = 2):
    """定时删除消息"""

    await asyncio.sleep(delay_seconds)

    try:
        await client.delete_messages(chat_id, message_ids)
    except Exception:
        ...


def progress(current: int, total: int, unit: str):
    text = f"下 载 中... | {f'{current * 100 / total:.0f}%' if unit == 'bytes' else f'{current}/{total}'}"
    if unit == "bytes":
        if round(current * 100 / total, 1) % 25 == 0:
            return text
    else:
        if (current + 1) % 3 == 0 or (current + 1) == total:
            return text
    return None


def encrypt(text: str):
    """hash加密"""
    md5 = hashlib.md5()
    md5.update(text.encode("utf-8"))
    return md5.hexdigest()


def img2webp(img) -> io.BytesIO:
    """将图片转换为webp格式, 返回io.BytesIO对象, 可直接上传到telegram"""
    with Image.open(img) as pil_img:
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")
        output = io.BytesIO()
        pil_img.save(output, format="WEBP")
        output.seek(0)
    return output


async def run_cmd(*cmd: str) -> str:
    """运行外部命令并异步读取输出"""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    return stdout.decode().strip()


async def get_video_codec(file: str) -> str:
    """获取视频编码格式"""
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
        file,
    )
    return out.lower() if out else ""


async def ensure_h264(file: str) -> str:
    """如果视频不是 H.264 编码，转码为 H.264。返回最终文件路径。"""
    codec = await get_video_codec(file)
    if codec == "h264":
        return file

    src = Path(file)
    out = src.with_stem(src.stem + "_h264")
    cmd = [
        "ffmpeg",
        "-i",
        str(file),
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
        return str(out)
    return file


async def get_duration(file: str) -> float:
    """获取视频时长"""
    out = await run_cmd(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        file,
    )
    return float(out) if out else 0.0


async def split_video(
    file: str,
    output_dir: str,
    size_limit: int = 2_000_000_000,
    ffmpeg_args: str = "-c copy",
    keep_sec: float = 1.0,
) -> list[Path]:
    """按大小切片视频"""
    src = Path(file)
    if not src.exists():
        raise FileNotFoundError(file)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base = src.stem
    ext = src.suffix.lstrip(".")
    total_duration = int(await get_duration(file))
    cur = 0
    part = 1

    # print(f"▶ 总时长: {total_duration}s")
    # print(f"📁 输出目录: {out_dir.resolve()}\n")
    op = []
    while cur < total_duration:
        out_file = out_dir / f"{base}_part_{part:03d}.{ext}"
        op.append(out_file)
        # print(f"🎬 生成分段: {out_file.name} (起点 {cur}s)")

        cmd = [
            "ffmpeg",
            "-ss",
            str(cur),
            "-i",
            str(file),
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

        new_dur = int(await get_duration(str(out_file)))
        if new_dur <= 0:
            # print(f"⚠️ {out_file.name} 为空，停止。")
            break

        cur += new_dur
        if cur < total_duration:
            cur = max(cur - int(keep_sec), 0)

        part += 1

    # print(f"\n✅ 分割完成，共输出 {part - 1} 段。")
    return op
