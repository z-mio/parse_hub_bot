import asyncio
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from inspect import signature
from typing import List

import httpx


class WeiboAPI:
    @staticmethod
    def get_id_by_url(url: str) -> str | None:
        bid = url.split("/")[-1]
        if bid.isdigit() or len(bid) == 9:
            return bid
        return None

    async def parse(self, url: str) -> "WeiboContent":
        bid = self.get_id_by_url(url)
        cookies = {
            "SUB": "_2AkMR47Mlf8NxqwFRmfocxG_lbox2wg7EieKnv0L-JRMxHRl-yT9yqhFdtRB6OmOdyoia9pKPkqoHRRmSBA_WNPaHuybH",
        }
        api = f"https://weibo.com/ajax/statuses/show?id={bid}"
        async with httpx.AsyncClient() as client:
            response = await client.get(api, cookies=cookies)
            response.raise_for_status()
            result = response.json()
        return WeiboContent.parse(result)


class MediaType(Enum):
    VIDEO = "video"
    PHOTO = "pic"
    LIVE_PHOTO = "livephoto"
    GIF = "gif"


class Info:
    @property
    @abstractmethod
    def media_url(self):
        raise NotImplementedError()

    @property
    @abstractmethod
    def thumb_url(self):
        raise NotImplementedError()


@dataclass
class MediaInfo:
    format: str = None
    mp4_hd_url: str = None
    mp4_sd_url: str = None
    duration: int = None
    prefetch_size: int = None

    @staticmethod
    def parse(media_dict: dict) -> "MediaInfo":
        format_ = media_dict["format"]
        mp4_hd_url = media_dict.get("mp4_hd_url")
        mp4_sd_url = media_dict.get("mp4_sd_url")
        duration = media_dict["duration"]
        prefetch_size = media_dict["prefetch_size"]
        return MediaInfo(format_, mp4_hd_url, mp4_sd_url, duration, prefetch_size)


@dataclass
class PageInfo(Info):
    object_type: MediaType = None
    media_info: MediaInfo = None
    page_pic: str = None
    short_url: str = None

    @staticmethod
    def parse(page_info_dict: dict) -> "PageInfo":
        object_type = MediaType(page_info_dict["object_type"])
        media_info = MediaInfo.parse(page_info_dict["media_info"])
        page_pic = page_info_dict.get("page_pic")
        short_url = page_info_dict.get("short_url")
        return PageInfo(object_type, media_info, page_pic, short_url)

    @property
    def media_url(self):
        return self.media_info.mp4_hd_url or self.media_info.mp4_sd_url

    @property
    def thumb_url(self):
        return self.page_pic


@dataclass
class Pic:
    url: str = None
    width: int = None
    height: int = None
    cut_type: int = None
    type: str | None = None


@dataclass
class PicInfo(Info):
    """photo, livephoto, gif.
    video为livephoto和gif视频
    """

    pic_id: str = None
    type: MediaType = None
    thumbnail: Pic = None
    largest: Pic = None
    video: str = None

    @staticmethod
    def parse(pic_dict: dict) -> "PicInfo":
        return PicInfo(
            pic_id=pic_dict["pic_id"],
            type=MediaType(pic_dict["type"]),
            thumbnail=Pic(**pic_dict["thumbnail"]),
            largest=Pic(**pic_dict["largest"]),
        )

    @property
    def media_url(self):
        return self.largest.url if self.type == MediaType.PHOTO else self.video

    @property
    def thumb_url(self):
        return self.thumbnail.url


@dataclass
class MixMediaInfoItem(Info):
    type: MediaType = None
    data: PageInfo | PicInfo = None

    @property
    def media_url(self):
        return self.data.media_url

    @property
    def thumb_url(self):
        return self.data.thumb_url


@dataclass
class MixMediaInfo:
    items: List[MixMediaInfoItem] = None

    @staticmethod
    def parse(mix_media_info_dict: dict) -> "MixMediaInfo":
        items = []
        for item_dict in mix_media_info_dict["items"]:
            type_ = MediaType(item_dict["type"])
            if type_ == MediaType.PHOTO:
                data = PicInfo.parse(item_dict["data"])
            elif type_ == MediaType.VIDEO:
                data = PageInfo.parse(item_dict["data"])
            else:
                data = None
            items.append(MixMediaInfoItem(type_, data))
        return MixMediaInfo(items)


@dataclass
class Data:
    id: str = None
    mid: str = None
    text: str = None  # 带html标签
    text_raw: str = None  # 纯文本
    pic_infos: list[PicInfo] = None
    page_info: PageInfo = None
    mix_media_info: MixMediaInfo = None
    retweeted_status: "Data" = None

    @staticmethod
    def parse(data_dict: dict) -> "Data":
        if page_info := data_dict.get("page_info"):
            data_dict["page_info"] = PageInfo.parse(page_info)
        if pic_infos := data_dict.get("pic_infos"):
            data_dict["pic_infos"] = [
                PicInfo.parse(pic_info) for pic_info in pic_infos.values()
            ]
        if mix_media_info := data_dict.get("mix_media_info"):
            data_dict["mix_media_info"] = MixMediaInfo.parse(mix_media_info)
        if retweeted_status := data_dict.get("retweeted_status"):
            data_dict["retweeted_status"] = Data.parse(retweeted_status)
        return Data.from_kwargs(**data_dict)

    @classmethod
    def from_kwargs(cls, **kwargs):
        cls_fields = {field for field in signature(cls).parameters}

        native_args, new_args = {}, {}
        for name, val in kwargs.items():
            if name in cls_fields:
                native_args[name] = val
            else:
                new_args[name] = val

        ret = cls(**native_args)

        for new_name, new_val in new_args.items():
            setattr(ret, new_name, new_val)
        return ret

    @property
    def content(self):
        """干净的正文"""
        text = self.text_raw
        if short_url := (self.page_info and self.page_info.short_url):
            text = text.replace(short_url, "")
        return text.strip()


@dataclass
class WeiboContent:
    data: Data

    @staticmethod
    def parse(json_dict: dict) -> "WeiboContent":
        data = Data.parse(json_dict)
        return WeiboContent(data=data)


if __name__ == "__main__":
    print(asyncio.run(WeiboAPI().parse("https://weibo.com/3208333150/Ow0iEbEX0")))
