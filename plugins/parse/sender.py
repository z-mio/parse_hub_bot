import asyncio
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from functools import partial
from itertools import batched
from typing import Any, BinaryIO, cast

from easy_ai18n import PreLocaleSelector
from parsehub.types import AniFile, AniRef, AnyMediaRef, AnyParseResult, ImageFile, LivePhotoFile, VideoFile
from pyrogram import Client, enums
from pyrogram.errors import FloodWait, Forbidden, SlowmodeWait, WebpageCurlFailed, WebpageMediaEmpty
from pyrogram.types import (
    InlineKeyboardButton as Ikb,
)
from pyrogram.types import (
    InlineKeyboardMarkup as Ikm,
)
from pyrogram.types import (
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    InputRichMessage,
    LinkPreviewOptions,
    Message,
    ReplyParameters,
)

from core import bs
from log import logger
from plugins.helpers import build_caption, build_caption_by_str, format_label
from plugins.parse.cache import build_cached_media_group, cache_media_from_message
from repo.settings import SettingsConfig
from services import CacheEntry, CacheMedia, CacheMediaType, CacheParseResult, PipelineResult, StatusReporter
from services.media import ProcessedMedia, resolve_media_info
from utils.helpers import pack_dir_to_tar_gz, to_list

logger = logger.bind(name="ParseSender")
MAX_RETRIES = 5
GIF_ONLY_SKIP_DOWNLOAD_COUNT_THRESHOLD = 5


type ReplyMediaGroupItem = InputMediaPhoto | InputMediaVideo | InputMediaDocument


@dataclass(frozen=True, slots=True)
class MessageSender:
    cli: Client
    msg: Message
    config: SettingsConfig
    delete_after_seconds: float | None = None

    @property
    def reply_parameters(self) -> ReplyParameters | None:
        return None if self.config.reply_msg else ReplyParameters()

    def delete_after(self, seconds: float | int | None) -> "MessageSender":
        if not seconds:
            return self
        return replace(self, delete_after_seconds=float(seconds))

    def _delete_later(self, sent: Message | Sequence[Message]) -> None:
        if self.delete_after_seconds is None:
            return

        messages = to_list(sent)

        async def fn() -> None:
            await asyncio.sleep(self.delete_after_seconds or 0)
            for message in messages:
                try:
                    await message.delete()
                except Exception as e:
                    logger.debug(
                        f"定时删除消息失败: chat_id={message.chat and message.chat.id}, msg_id={message.id}, error={e}"
                    )

        asyncio.get_running_loop().create_task(fn())

    async def _send_and_schedule_delete[T](self, send_coro_fn: Callable[[], Awaitable[T]]) -> T:
        sent = await self._send(send_coro_fn)
        if isinstance(sent, Message) or isinstance(sent, list):
            self._delete_later(sent)
        return sent

    @staticmethod
    async def _send[T](send_coro_fn: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(MAX_RETRIES):
            try:
                return await send_coro_fn()
            except (FloodWait, SlowmodeWait) as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"{e.ID} 重试 ({attempt + 1}/{MAX_RETRIES})，等待 {e.value}s")
                    await asyncio.sleep(e.value)
                else:
                    raise
            except Forbidden as e:
                logger.warning(f"消息发送失败, Bot 无权限: {e}")
                break
            except Exception as e:
                logger.warning(f"消息发送失败: {e}")
                break
            await asyncio.sleep(0.5)
        raise RuntimeError("消息发送失败")

    async def chat_action(self, action: enums.ChatAction) -> None:
        await self.msg.reply_chat_action(action)

    async def typing(self) -> None:
        await self.chat_action(enums.ChatAction.TYPING)

    async def upload_document(self) -> None:
        await self.chat_action(enums.ChatAction.UPLOAD_DOCUMENT)

    async def upload_photo(self) -> None:
        await self.chat_action(enums.ChatAction.UPLOAD_PHOTO)

    async def upload_video(self) -> None:
        await self.chat_action(enums.ChatAction.UPLOAD_VIDEO)

    async def text(
        self,
        text: str,
        *,
        link_preview_options: LinkPreviewOptions | None = None,
        reply_markup: Ikm | None = None,
    ) -> Message:
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(
                    self.msg.reply_text,
                    text,
                    link_preview_options=link_preview_options,
                    reply_markup=reply_markup,
                    reply_parameters=self.reply_parameters,
                )
            ),
        )

    async def text_no_preview(self, text: str, *, reply_markup: Ikm | None = None) -> Message:
        return await self.text(
            text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=reply_markup,
        )

    async def text_with_preview_above(self, text: str, *, reply_markup: Ikm | None = None) -> Message:
        return await self.text(
            text,
            link_preview_options=LinkPreviewOptions(show_above_text=True),
            reply_markup=reply_markup,
        )

    async def document(
        self,
        document: str | BinaryIO,
        *,
        caption: str | None = None,
        force_document: bool | None = None,
        use_reply_policy: bool = True,
    ) -> Message:
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(
                    self.msg.reply_document,
                    document,
                    caption=caption or "",
                    force_document=force_document,
                    reply_parameters=self.reply_parameters if use_reply_policy else None,
                )
            ),
        )

    def reply_to(self, msg: Message) -> "MessageSender":
        return replace(self, msg=msg)

    async def force_document(
        self,
        document: str | BinaryIO,
        *,
        caption: str | None = None,
        use_reply_policy: bool = True,
    ) -> Message:
        return await self.document(
            document,
            caption=caption,
            force_document=True,
            use_reply_policy=use_reply_policy,
        )

    async def photo(self, photo: str | BinaryIO, *, caption: str | None = None) -> Message:
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(self.msg.reply_photo, photo, caption=caption or "", reply_parameters=self.reply_parameters)
            ),
        )

    async def video(
        self,
        video: str | BinaryIO,
        *,
        caption: str | None = None,
        video_cover: str | BinaryIO | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
        supports_streaming: bool | None = None,
    ) -> Message:
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(
                    self.msg.reply_video,
                    video,
                    caption=caption or "",
                    video_cover=video_cover,
                    duration=duration or 0,
                    width=width or 0,
                    height=height or 0,
                    supports_streaming=True if supports_streaming is None else supports_streaming,
                    reply_parameters=self.reply_parameters,
                )
            ),
        )

    async def streaming_video(
        self,
        video: str | BinaryIO,
        *,
        caption: str | None = None,
        video_cover: str | BinaryIO | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Message:
        return await self.video(
            video,
            caption=caption,
            video_cover=video_cover,
            duration=duration,
            width=width,
            height=height,
            supports_streaming=True,
        )

    async def streaming_video_with_cover_fallback(
        self,
        video: str | BinaryIO,
        *,
        caption: str | None = None,
        video_cover: str | BinaryIO | None = None,
        duration: int | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> Message:
        try:
            return await self.streaming_video(
                video,
                caption=caption,
                video_cover=video_cover,
                duration=duration,
                width=width,
                height=height,
            )
        except (WebpageCurlFailed, WebpageMediaEmpty):
            logger.warning("Tg 获取封面失败, 移除封面上传")
            return await self.streaming_video(
                video,
                caption=caption,
                duration=duration,
                width=width,
                height=height,
            )

    async def animation(self, animation: str | BinaryIO, *, caption: str | None = None) -> Message:
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(
                    self.msg.reply_animation,
                    animation,
                    caption=caption or "",
                    reply_parameters=self.reply_parameters,
                )
            ),
        )

    async def media_group(self, media: list[ReplyMediaGroupItem]) -> list[Message]:
        return await self._send_and_schedule_delete(
            partial(self.msg.reply_media_group, media=cast(Any, media), reply_parameters=self.reply_parameters)
        )

    async def rich_message(
        self,
        rich_message: InputRichMessage,
        *,
        reply_markup: Ikm | None = None,
    ) -> Message:
        if not self.msg.chat or not self.msg.chat.id:
            raise ValueError("not chat or chat_id")
        reply_parameters = (
            ReplyParameters(message_id=self.msg.id) if self.reply_parameters is None else self.reply_parameters
        )
        return cast(
            Message,
            await self._send_and_schedule_delete(
                partial(
                    self.cli.send_rich_message,
                    chat_id=self.msg.chat.id,
                    message_thread_id=self.msg.message_thread_id,
                    rich_message=rich_message,
                    reply_markup=reply_markup,
                    reply_parameters=reply_parameters,
                )
            ),
        )


async def send_raw(
    sender: MessageSender,
    result: PipelineResult,
    reporter: StatusReporter,
    *,
    _t: PreLocaleSelector,
    custom_content: str = "",
) -> None:
    """Raw 模式：将文件以原始文档形式上传。"""
    logger.debug("Raw 模式, 直接上传文件")
    await reporter.report(_t("上 传 中..."))
    try:
        caption = build_caption(result.parse_result, config=sender.config, custom_content=custom_content)
        docs: list[InputMediaDocument] = []
        gifs = []
        livephoto_videos: dict[int, InputMediaDocument] = {}

        for processed in result.processed_list:
            file_paths = processed.output_paths or [processed.source.path]
            file_path = file_paths[0]
            doc = InputMediaDocument(media=str(file_path))
            if isinstance(processed.source, AniFile):
                gifs.append(doc)
            elif isinstance(processed.source, LivePhotoFile):
                docs.append(doc)
                livephoto_videos[len(docs) - 1] = InputMediaDocument(media=str(processed.source.video_path))
            else:
                docs.append(doc)

        if len(docs + gifs) == 1:
            all_docs = docs + gifs
            await sender.upload_document()
            sent_msg = await sender.force_document(media_input(all_docs[0].media), caption=caption)
            if livephoto_videos and sent_msg:
                await sender.reply_to(sent_msg).force_document(
                    media_input(livephoto_videos[0].media),
                    use_reply_policy=False,
                )
        else:
            msgs: list[Message] = []
            for batch in batched(docs, 10):
                await sender.upload_document()
                mg = await sender.media_group(list(batch))
                msgs.extend(mg)
            if livephoto_videos:
                for idx, media_doc in livephoto_videos.items():
                    await sender.upload_document()
                    await sender.reply_to(msgs[idx]).force_document(
                        media_input(media_doc.media),
                        use_reply_policy=False,
                    )
            if gifs:
                await sender.text(
                    format_label(_t("GIF 下载链接")),
                    reply_markup=build_gif_button(to_list(result.parse_result.media)),
                )
            await sender.text_no_preview(caption)

    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"Raw 模式上传失败: {e}")
        await reporter.report_error(_t("上传"), e)
        return
    else:
        await reporter.dismiss()
    finally:
        result.cleanup()


async def send_zip(
    sender: MessageSender,
    result: PipelineResult,
    reporter: StatusReporter,
    *,
    _t: PreLocaleSelector,
    custom_content: str = "",
) -> None:
    logger.debug("Zip 模式, 开始打包")
    await reporter.report(_t("打 包 中..."))
    try:
        caption = build_caption(result.parse_result, config=sender.config, custom_content=custom_content)
        if result.output_dir is None:
            raise ValueError("缺少打包目录")
        pack_path = await asyncio.to_thread(pack_dir_to_tar_gz, result.output_dir)
    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"打包失败: {e}")
        await reporter.report_error(_t("打包"), Exception("..."))
        return
    finally:
        result.cleanup()

    await reporter.report(_t("上 传 中..."))
    try:
        await sender.upload_document()
        await sender.document(str(pack_path), caption=caption)
    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"上传失败: {e}")
        await reporter.report_error(_t("上传"), e)
        return
    else:
        await reporter.dismiss()
    finally:
        if not bs.debug_skip_cleanup:
            logger.debug("清理压缩包")
            os.remove(pack_path)


async def send_media(
    sender: MessageSender,
    parse_result: AnyParseResult,
    processed_list: list[ProcessedMedia],
    caption: str,
    *,
    _t: PreLocaleSelector,
) -> CacheEntry | None:
    """构建、发送媒体，并返回缓存条目。"""
    media_refs = to_list(parse_result.media)
    photos_videos, animations = build_input_media(media_refs, processed_list, video_cover=sender.config.video_cover)
    all_count = len(photos_videos) + len(animations)
    logger.debug(f"媒体分类完成: animations={len(animations)}, photos_videos={len(photos_videos)}")

    if all_count == 1:
        logger.debug("单媒体模式发送")
        media_list = await send_single(sender, photos_videos, animations, caption)
    else:
        logger.debug(f"多媒体模式发送: total={all_count}")
        media_list = await send_multi(sender, photos_videos, animations, caption, media_refs, _t=_t)

    if media_list is None:
        return None
    return CacheEntry(
        parse_result=CacheParseResult(title=parse_result.title, content=parse_result.content),
        media=media_list,
    )


async def send_cached(sender: MessageSender, entry: CacheEntry, url: str, *, custom_content: str = "") -> None:
    """从 file_id 缓存直接发送，跳过解析/下载/转码。"""
    logger.debug(f"缓存发送: media={entry.media}")
    caption = build_caption_by_str(
        entry.parse_result.title,
        entry.parse_result.content,
        url,
        entry.telegraph_url,
        hide_source=sender.config.hide_source,
        custom_content=custom_content,
        hide_title=sender.config.hide_title,
        hide_desc=sender.config.hide_desc,
        rich=entry.rich,
    )

    if entry.rich:
        await sender.rich_message(rich_message=InputRichMessage(markdown=caption))
        return

    if entry.telegraph_url:
        await sender.text_with_preview_above(caption)
        return

    if not entry.media:
        await sender.text_no_preview(caption)
        return

    if len(entry.media) == 1:
        await send_cached_single(sender, entry.media[0], caption, video_cover=sender.config.video_cover)
    else:
        await send_cached_multi(sender, entry.media, caption, video_cover=sender.config.video_cover)


def media_input(media: str | BinaryIO | None) -> str | BinaryIO:
    return cast(str | BinaryIO, media)


def build_input_media(
    media_refs: Sequence[AnyMediaRef], processed_list: list[ProcessedMedia], *, video_cover: bool
) -> tuple[list[InputMediaPhoto | InputMediaVideo], list[InputMediaAnimation]]:
    """根据处理结果和媒体引用构建 Telegram InputMedia 列表。"""
    photos_videos: list[InputMediaPhoto | InputMediaVideo] = []
    animations: list[InputMediaAnimation] = []

    for media_ref, processed in zip(media_refs, processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width, height, duration = resolve_media_info(processed, file_path_str)

            match processed.source:
                case ImageFile():
                    photos_videos.append(InputMediaPhoto(media=file_path_str))
                case AniFile():
                    animations.append(InputMediaAnimation(media=file_path_str))
                case VideoFile():
                    photos_videos.append(
                        InputMediaVideo(
                            media=file_path_str,
                            video_cover=media_ref.thumb_url if video_cover else None,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )
                case LivePhotoFile():
                    photos_videos.append(
                        InputMediaVideo(
                            media=processed.source.video_path,
                            video_cover=file_path_str if video_cover else None,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )

    return photos_videos, animations


async def send_single(
    sender: MessageSender,
    photos_videos: list[InputMediaPhoto | InputMediaVideo],
    animations: list[InputMediaAnimation],
    caption: str,
) -> list[CacheMedia] | None:
    """发送单个媒体，返回 CacheMedia 列表。上传失败时降级为 document。"""
    media_list: list[CacheMedia] = []
    all_media = animations + photos_videos

    try:
        sent: Message | None = None
        if animations:
            await sender.upload_photo()
            sent = await sender.animation(media_input(animations[0].media), caption=caption)
        else:
            single = photos_videos[0]
            match single:
                case InputMediaPhoto():
                    await sender.upload_photo()
                    sent = await sender.photo(media_input(single.media), caption=caption)
                case InputMediaVideo():
                    await sender.upload_video()
                    sent = await sender.streaming_video_with_cover_fallback(
                        media_input(single.media),
                        caption=caption,
                        video_cover=single.video_cover,
                        duration=single.duration,
                        width=single.width,
                        height=single.height,
                    )

        if sent and (cm := cache_media_from_message(sent)):
            media_list.append(cm)
    except Exception as e:
        logger.warning(f"上传失败 {e}, 使用兼容模式上传")
        await sender.upload_document()
        await sender.force_document(media_input(all_media[0].media), caption=caption)
        return None

    return media_list


def build_gif_button(media_refs: Sequence[AnyMediaRef]) -> Ikm:
    buttons = []
    n = 5
    for i, v in enumerate(media_refs):
        if isinstance(v, AniRef):
            buttons.append(Ikb(f"{i + 1}", url=v.url))
    ikbs = [list(i) for i in batched(buttons, n)]
    return Ikm(ikbs)


async def send_multi(
    sender: MessageSender,
    photos_videos: list[InputMediaPhoto | InputMediaVideo],
    animations: list[InputMediaAnimation],
    caption: str,
    media_refs: Sequence[AnyMediaRef],
    *,
    _t: PreLocaleSelector,
) -> list[CacheMedia] | None:
    """发送多个媒体（动图逐条、图片视频分批），返回 CacheMedia 列表。"""
    media_list: list[CacheMedia] = []
    not_cache = False
    if len([i for i in media_refs if isinstance(i, AniRef)]) > GIF_ONLY_SKIP_DOWNLOAD_COUNT_THRESHOLD:
        not_cache = True
        await sender.text(
            format_label(_t("GIF 过多跳过上传, 请自行下载")),
            reply_markup=build_gif_button(media_refs),
        )
    else:
        for ani in animations:
            await sender.upload_photo()
            caption_ = caption if ani == animations[-1] and not photos_videos else ""
            try:
                sent = await sender.animation(media_input(ani.media), caption=caption_)
            except Exception as e:
                logger.warning(f"上传失败 {e}, 使用兼容模式上传")
                not_cache = True
                await sender.upload_document()
                await sender.force_document(media_input(ani.media), caption=caption_)
            else:
                if sent and sent.document:
                    media_list.append(CacheMedia(type=CacheMediaType.DOCUMENT, file_id=sent.document.file_id))
                elif sent and sent.animation:
                    media_list.append(CacheMedia(type=CacheMediaType.ANIMATION, file_id=sent.animation.file_id))

    try:
        for batch in batched(photos_videos, 10):
            if batch[-1] == photos_videos[-1]:
                batch[0].caption = caption

            await sender.upload_photo()
            sent_msgs = await sender.media_group(list(batch))
            for m in sent_msgs:
                if cm := cache_media_from_message(m):
                    media_list.append(cm)
    except Exception as e:
        logger.warning(f"上传失败 {e}, 使用兼容模式上传")
        input_documents: list[InputMediaDocument] = [
            InputMediaDocument(media=media_input(item.media)) for item in photos_videos
        ]
        for document_batch in batched(input_documents, 10):
            if document_batch[-1] == input_documents[-1]:
                document_batch[-1].caption = caption

            await sender.upload_document()
            await sender.media_group(list(document_batch))
        return None

    return None if not_cache else media_list


async def send_cached_single(sender: MessageSender, m: CacheMedia, caption: str, *, video_cover: bool) -> None:
    """从缓存发送单个媒体。"""
    match m.type:
        case CacheMediaType.PHOTO:
            await sender.upload_photo()
            await sender.photo(m.file_id, caption=caption)
        case CacheMediaType.VIDEO:
            await sender.upload_video()
            await sender.streaming_video(
                m.file_id,
                caption=caption,
                video_cover=m.cover_file_id if video_cover else None,
            )
        case CacheMediaType.ANIMATION:
            await sender.upload_photo()
            await sender.animation(m.file_id, caption=caption)
        case CacheMediaType.DOCUMENT:
            await sender.upload_document()
            await sender.force_document(m.file_id, caption=caption)


async def send_cached_multi(sender: MessageSender, media: list[CacheMedia], caption: str, *, video_cover: bool) -> None:
    """从缓存发送多个媒体。"""
    animations = [m for m in media if m.type == CacheMediaType.ANIMATION]
    others = [m for m in media if m.type != CacheMediaType.ANIMATION]

    for ani in animations:
        await sender.upload_photo()
        await sender.animation(ani.file_id, caption=caption if ani == animations[-1] and not others else "")

    media_group = build_cached_media_group(others, video_cover=video_cover)
    for batch in batched(media_group, 10):
        if batch[-1] == media_group[-1]:
            batch[0].caption = caption

        await sender.upload_photo()
        await sender.media_group(list(batch))
