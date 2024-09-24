import os
from abc import ABC
from dataclasses import dataclass
from typing import TypeVar

from .subtitles import Subtitles

MediaT = TypeVar("MediaT", bound="Media")


@dataclass
class Media(ABC):
    """媒体

    path: 本地路径或URL
    ext: 默认扩展名
    thumb_url: 缩略图URL
    """

    path: str = None
    ext: str = None
    thumb_url: str = None
    subtitles: Subtitles = None

    def __str__(self):
        return str(self.path)

    def __repr__(self):
        return str(self.path)

    @property
    def is_url(self) -> bool:
        """是否为URL"""
        path = str(self.path)
        return path.startswith("http") or path.startswith("https")

    def exists(self) -> bool:
        """本地文件是否存在"""
        if self.is_url:
            return False
        return os.path.exists(self.path)


@dataclass
class Video(Media):
    """视频

    path: 本地路径或URL
    ext: 默认扩展名
    thumb_url: 缩略图URL
    """

    path: str = None
    ext: str = "mp4"
    thumb_url: str = None
    subtitles: Subtitles = None


@dataclass
class Image(Media):
    """图片

    path: 本地路径或URL
    ext: 默认扩展名
    thumb_url: 缩略图URL
    """

    path: str = None
    ext: str = "jpg"
    thumb_url: str = path


@dataclass
class Ani(Media):
    """动图

    path: 本地路径或URL
    ext: 默认扩展名
    thumb_url: 缩略图URL
    """

    path: str = None
    ext: str = "gif"
    thumb_url: str = None


__all__ = ["Media", "Video", "Image", "Ani", "MediaT"]
