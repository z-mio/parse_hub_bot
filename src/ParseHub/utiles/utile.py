import importlib
import inspect
import pkgutil
import re
import base64
import aiofiles
import httpx
import cv2
from typing import Literal
from urlextract import URLExtract

from ...ParseHub import parsers


def re_match(text: str, pattern: str) -> bool:
    return bool(re.match(pattern, text))


def is_method_overridden(method_name, base_class, derived_class):
    base_method = getattr(base_class, method_name, None)
    derived_method = getattr(derived_class, method_name, None)

    if base_method is None or derived_method is None:
        return False

    return (
        base_method != derived_method
        and inspect.isfunction(base_method)
        and inspect.isfunction(derived_method)
    )


def get_all_subclasses(cls):
    for _, module_name, _ in pkgutil.walk_packages(
        parsers.__path__, f"{parsers.__name__}."
    ):
        importlib.import_module(module_name)

    subclasses = set(cls.__subclasses__())
    for subclass in cls.__subclasses__():
        subclasses.update(get_all_subclasses(subclass))
    return subclasses


def progress(current, total, type_=Literal["数量", "百分比"]):
    return f"{current * 100 / total:.0f}%" if type_ == "百分比" else f"{current}/{total}"


def timestamp_to_time(timestamp):
    hours = int(timestamp / 3600)
    minutes = int((timestamp % 3600) / 60)
    seconds = int(timestamp % 60)
    if f"{hours:02d}" == "00":
        return f"{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def match_url(text: str) -> str:
    """从文本中提取url"""
    if not text:
        return ""
    text = re.sub(r"(https?://)", r" \1", text)
    url = URLExtract().find_urls(text, only_unique=True)
    return url[0] if url else ""


async def img2base64(img: str) -> str:
    """将网络或本地图片转化为base64编码"""
    if img.startswith("http"):
        async with httpx.AsyncClient() as cli:
            content = (await cli.get(img)).content
    else:
        async with aiofiles.open(img, "rb") as f:
            content = await f.read()
    return base64.b64encode(content).decode("utf-8")


def video_to_png(video: str) -> str:
    """提取视频第一帧
    :return: 图片路径
    """
    o_p = f"{video}.png"
    video = cv2.VideoCapture(video)
    image = video.read()[1]
    cv2.imwrite(o_p, image)
    return o_p
