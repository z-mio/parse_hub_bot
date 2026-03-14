import asyncio
import shutil

from markdown import markdown
from parsehub import Platform
from parsehub.types import (
    AniFile,
    AnyMediaRef,
    ImageFile,
    LivePhotoFile,
    ParseResult,
    PostType,
    ProgressUnit,
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
from plugins.helpers import ProcessedMedia, build_caption, progress
from services import ParseService
from utils.converter import clean_article_html
from utils.filters import platform_filter
from utils.media_processing_unit import MediaProcessingUnit
from utils.ph import Telegraph


async def send_ph(html_content: str, cli: Client, msg: Message, parse_result: ParseResult) -> Message:
    me = await cli.get_me()
    page = await Telegraph().create_page(
        parse_result.title or "无标题",
        html_content=html_content,
        author_name=me.full_name,
        author_url=parse_result.raw_url,
    )
    return await msg.reply_text(
        build_caption(parse_result, page.url),
        link_preview_options=LinkPreviewOptions(show_above_text=True),
    )


async def handle_parse(cli: Client, msg: Message, url: str):
    status_msg = await msg.reply_text("**▎解 析 中...**")

    # ── 解析 ──
    try:
        parse_result = await ParseService(url).parse()
    except Exception as e:
        logger.exception(e)
        logger.error("解析失败, 以上为错误信息")
        await status_msg.edit_text(
            f"解析错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await status_msg.delete()
        return None

    # ── 富文本直接 telegraph 发送 ──
    if parse_result.type == PostType.RICHTEXT:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)
        if parse_result.platform == Platform.WEIXIN:
            await send_ph(
                clean_article_html(
                    markdown(parse_result.markdown_content.replace("mmbiz.qpic.cn", "mmbiz.qpic.cn.in"))
                ),
                cli,
                msg,
                parse_result,
            )
        elif parse_result.platform == Platform.COOLAPK:
            await send_ph(
                clean_article_html(
                    markdown(parse_result.markdown_content.replace("image.coolapk.com", "qpic.cn.in/image.coolapk.com"))
                ),
                cli,
                msg,
                parse_result,
            )
        else:
            await send_ph(clean_article_html(markdown(parse_result.markdown_content)), cli, msg, parse_result)
        await status_msg.delete()
        return None

    # ── 下载 ──
    await status_msg.edit_text("**▎下 载 中...**")

    try:
        download_result = await parse_result.download(callback=ProgressCallback(), callback_args=(status_msg,))
    except Exception as e:
        logger.exception(e)
        logger.error("解析或下载失败, 以上为错误信息")
        await status_msg.edit_text(
            f"下载错误: \n```\n{e}```",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        await asyncio.sleep(5)
        await status_msg.delete()
        return None

    # ── 格式转换 ──
    await status_msg.edit_text("**▎格式转换中...**")

    try:
        processed_dir = download_result.output_dir.joinpath("processed")
        processor = MediaProcessingUnit(processed_dir)
        media_files = download_result.media if isinstance(download_result.media, list) else [download_result.media]
        processed_list: list[ProcessedMedia] = []
        for media_file in media_files:
            result = await processor.process(media_file.path)
            processed_list.append(ProcessedMedia(media_file, result.output_paths, result.temp_dir))
    except Exception as e:
        await status_msg.edit_text(f"格式转换错误: \n```\n{e}```")
        logger.exception(e)
        logger.error("格式转换失败, 以上为错误信息")
        await asyncio.sleep(5)
        await status_msg.delete()
        shutil.rmtree(download_result.output_dir, ignore_errors=True)
        return None

    # ── 上传 ──
    await status_msg.edit_text("**▎上 传 中...**")

    try:
        await msg.reply_chat_action(enums.ChatAction.UPLOAD_PHOTO)

        caption = build_caption(parse_result)

        if not processed_list:
            return await msg.reply_text(
                caption,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )

        input_photos_videos: list[InputMediaPhoto | InputMediaVideo] = []
        input_animations: list[InputMediaAnimation] = []

        media_refs: list[AnyMediaRef] = (
            parse_result.media if isinstance(parse_result.media, list) else [parse_result.media]
        )

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

        if len(all_media) == 1:
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

    except Exception as e:
        await status_msg.edit_text("上传失败")
        logger.exception(e)
        logger.error("上传失败, 以上为错误信息")
        await asyncio.sleep(5)
        await status_msg.delete()
        return None
    finally:
        shutil.rmtree(download_result.output_dir, ignore_errors=True)
    await status_msg.delete()
    return None


@Client.on_message((filters.text | filters.caption) & platform_filter)
async def text_parse(cli: Client, msg: Message):
    url = msg.text or msg.caption
    await handle_parse(cli, msg, url)


@Client.on_message(filters.command(["jx"]))
async def cmd_jx(cli: Client, msg: Message):
    url = msg.command[1] if msg.command[1:] else ""

    if not url and msg.reply_to_message:
        url = msg.reply_to_message.text or msg.reply_to_message.caption or ""

    if not url:
        await msg.reply_text("请加上链接或回复一条消息")
        return

    await handle_parse(cli, msg, url)


class ProgressCallback:
    async def __call__(self, current: int, total: int, unit: ProgressUnit, msg: Message, *args) -> None:
        text = progress(current, total, unit)
        if not text or msg.text == text:
            return
        text = f"**▎{text}**"
        await msg.edit_text(text)
        msg.text = text
