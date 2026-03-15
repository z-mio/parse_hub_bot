import asyncio

from parsehub.types import (
    AniFile,
    AnyMediaRef,
    ImageFile,
    LivePhotoFile,
    PostType,
    VideoFile,
)
from parsehub.utils.media_info import MediaInfoReader
from pyrogram import Client, enums, filters
from pyrogram.types import (
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Message,
)

from log import logger
from plugins.helpers import build_caption, create_richtext_telegraph
from services.pipeline import ParsePipeline, StatusReporter
from utils.filters import platform_filter

logger = logger.bind(name="Parse")


class MessageStatusReporter(StatusReporter):
    """基于 Telegram Message 的状态报告器"""

    def __init__(self, user_msg: Message):
        self._user_msg = user_msg
        self._msg = None

    async def report(self, text: str) -> None:
        await self.edit_text(text)

    async def report_error(self, stage: str, error: Exception) -> None:
        await self.edit_text(
            f"{stage}错误: \n```\n{error}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await self._msg.delete()

    async def dismiss(self) -> None:
        await self._msg.delete()

    async def edit_text(self, text: str, **kwargs):
        if self._msg is None:
            self._msg = await self._user_msg.reply_text(text, **kwargs)
        else:
            if self._msg.text != text:
                await self._msg.edit_text(text, **kwargs)
                self._msg.text = text


async def handle_parse(cli: Client, msg: Message, url: str):
    logger.debug(f"收到解析请求: url={url}, chat_id={msg.chat.id}, msg_id={msg.id}")
    reporter = MessageStatusReporter(msg)

    pipeline = ParsePipeline(url, reporter)
    result = await pipeline.run()

    if result is None:
        logger.debug(f"Pipeline 返回 None, 跳过后续处理: url={url}")
        return

    parse_result = result.parse_result

    # ── 富文本 → Telegraph ──
    if parse_result.type == PostType.RICHTEXT:
        logger.debug(f"富文本类型, 创建 Telegraph 页面: title={parse_result.title}")
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)
        ph_url = await create_richtext_telegraph(cli, parse_result)
        logger.debug(f"Telegraph 页面创建完成: {ph_url}")
        await msg.reply_text(
            build_caption(parse_result, ph_url),
            link_preview_options=LinkPreviewOptions(show_above_text=True),
        )
        await reporter.dismiss()
        return

    # ── 上传 ──
    logger.debug(f"开始上传媒体: media_count={len(result.processed_list)}")
    await reporter.report("**▎上 传 中...**")
    try:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)
        caption = build_caption(parse_result)

        if not result.processed_list:
            logger.debug("无媒体文件, 仅发送文本")
            await msg.reply_text(
                caption,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            await reporter.dismiss()
            return

        await _send_media(msg, parse_result, result.processed_list, caption)
    except Exception as e:
        await reporter.report_error("上传", e)
        return
    finally:
        result.cleanup()

    await reporter.dismiss()


async def _send_media(msg: Message, parse_result, processed_list, caption: str):
    logger.debug(f"构建媒体列表: processed_count={len(processed_list)}")
    input_photos_videos: list[InputMediaPhoto | InputMediaVideo] = []
    input_animations: list[InputMediaAnimation] = []

    media_refs: list[AnyMediaRef] = parse_result.media if isinstance(parse_result.media, list) else [parse_result.media]

    for media_ref, processed in zip(media_refs, processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width = processed.source.width
            height = processed.source.height
            duration = getattr(processed.source, "duration", 0)

            if processed.output_paths:
                media_info = MediaInfoReader.read(file_path_str)
                width, height, duration = (
                    media_info.width,
                    media_info.height,
                    media_info.duration,
                )

            match processed.source:
                case ImageFile():
                    input_photos_videos.append(InputMediaPhoto(media=file_path_str))
                case AniFile():
                    input_animations.append(InputMediaAnimation(media=file_path_str))
                case VideoFile():
                    input_photos_videos.append(
                        InputMediaVideo(
                            media=file_path_str,
                            video_cover=media_ref.thumb_url,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )
                case LivePhotoFile():
                    input_photos_videos.append(
                        InputMediaVideo(
                            media=processed.source.video_path,
                            video_cover=file_path_str,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                        )
                    )

    all_media = input_animations + input_photos_videos
    logger.debug(f"媒体分类完成: animations={len(input_animations)}, photos_videos={len(input_photos_videos)}")

    if len(all_media) == 1:
        logger.debug("单媒体模式发送")
        try:
            if input_animations:
                await msg.reply_animation(input_animations[0].media, caption=caption)
            else:
                single = input_photos_videos[0]
                match single:
                    case InputMediaPhoto():
                        await msg.reply_photo(single.media, caption=caption)
                    case InputMediaVideo():
                        await msg.reply_video(
                            single.media,
                            caption=caption,
                            video_cover=single.video_cover,
                            duration=single.duration,
                            width=single.width,
                            height=single.height,
                            supports_streaming=True,
                        )
        except Exception as e:
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            await msg.reply_document(all_media[0].media, caption=caption)
    else:
        logger.debug(f"多媒体模式发送: total={len(all_media)}")
        sent_animations = [await msg.reply_animation(ani.media) for ani in input_animations]
        try:
            sent_groups = sent_animations + [
                await msg.reply_media_group(input_photos_videos[i : i + 10])
                for i in range(0, len(input_photos_videos), 10)
            ]
        except Exception as e:
            logger.warning(f"上传失败 {e}, 使用兼容模式上传")
            input_documents = [InputMediaDocument(media=item.media) for item in input_photos_videos]
            sent_groups = sent_animations + [
                await msg.reply_media_group(input_documents[i : i + 10])  # type: ignore
                for i in range(0, len(input_documents), 10)
            ]

        first_msg = sent_groups[0][0] if isinstance(sent_groups[0], list) else sent_groups[0]
        await first_msg.reply_text(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def text_parse(cli: Client, msg: Message):
    url = msg.text or msg.caption
    logger.debug(f"text_parse 触发: url={url}")
    await handle_parse(cli, msg, url)


@Client.on_message(filters.command(["jx"]))
async def cmd_jx(cli: Client, msg: Message):
    logger.debug(f"cmd_jx 触发: command={msg.command}")
    url = msg.command[1] if msg.command[1:] else ""

    if not url and msg.reply_to_message:
        url = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not url:
        await msg.reply_text("请加上链接或回复一条消息")
        return

    await handle_parse(cli, msg, url)
