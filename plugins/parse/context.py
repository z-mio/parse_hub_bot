from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from easy_ai18n import PreLocaleSelector

from repo.settings import ParseMode, SettingsConfig

if TYPE_CHECKING:
    from pyrogram import Client
    from pyrogram.types import Message


GIF_ONLY_SKIP_DOWNLOAD_COUNT_THRESHOLD = 5


@dataclass(frozen=True, slots=True)
class ParseRequest:
    cli: Client
    msg: Message
    url: str
    mode: ParseMode
    config: SettingsConfig
    t_: PreLocaleSelector
    bypass_cache: bool = False
    delete_share_url_msg: bool = False
    custom_content: str = ""

    @property
    def chat_id(self) -> int | None:
        return self.msg.chat.id if self.msg.chat else None


@dataclass(frozen=True, slots=True)
class ParseOptions:
    use_caching: bool
    skip_media_processing: bool
    singleflight: bool
    save_metadata: bool
    gif_only_skip_download_count_threshold: int

    @classmethod
    def from_mode(cls, mode: ParseMode, *, bypass_cache: bool) -> ParseOptions:
        match mode:
            case ParseMode.RAW:
                return cls(
                    use_caching=False,
                    skip_media_processing=True,
                    singleflight=False,
                    save_metadata=False,
                    gif_only_skip_download_count_threshold=0,
                )
            case ParseMode.ZIP:
                return cls(
                    use_caching=False,
                    skip_media_processing=True,
                    singleflight=False,
                    save_metadata=True,
                    gif_only_skip_download_count_threshold=0,
                )
            case ParseMode.PREVIEW:
                return cls(
                    use_caching=True,
                    skip_media_processing=False,
                    singleflight=not bypass_cache,
                    save_metadata=False,
                    gif_only_skip_download_count_threshold=GIF_ONLY_SKIP_DOWNLOAD_COUNT_THRESHOLD,
                )
