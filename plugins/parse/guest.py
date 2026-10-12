import io
import os

import httpx
from parsehub import AnyParseResult
from parsehub.types import AniFile, ImageFile, LivePhotoFile, RichTextParseResult, VideoFile
from pyrogram import Client, enums
from pyrogram.types import (
    InlineQueryResult,
    InlineQueryResultArticle,
    InlineQueryResultPhoto,
    InlineQueryResultVideo,
    InputMediaAnimation,
    InputMediaPhoto,
    InputMediaVideo,
    InputRichBlock,
    InputRichBlockAnimation,
    InputRichBlockCollage,
    InputRichBlockExpandableBlockQuotation,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
    InputRichBlockSlideshow,
    InputRichBlockVideo,
    InputRichMessage,
    InputRichMessageContent,
    InputTextMessageContent,
    LinkPreviewOptions,
    Message,
    RichText,
    RichTextBold,
    RichTextUrl,
)

from db import get_session
from i18n import t_
from log import logger
from plugins.helpers import build_caption
from plugins.parse.inline import (
    DEFAULT_PARSE_RESULT_THUMB_URL,
    build_cached_inline_results,
    build_inline_results,
)
from plugins.parse.sender import media_input
from repo.settings import SettingsConfig
from services import ParseService, SettingsService, UserService
from services.cache import parse_cache, persistent_cache
from services.media import resolve_media_info
from services.pipeline import ParsePipeline, PipelineResult, StatusReporter
from utils.helpers import to_list, with_request_id

logger = logger.bind(name="GuestParse")


class _GuestReporter(StatusReporter):
    """guest 没有可编辑的状态消息, 只记日志"""

    async def report(self, text: str) -> None:
        logger.debug(text)

    async def report_error(self, stage: str, error: Exception) -> None:
        logger.warning(f"guest 流水线[{stage}]失败: {error}")

    async def dismiss(self) -> None:
        pass


@Client.on_guest_message()
@with_request_id
async def call_guest_parse(cli: Client, message: Message) -> None:
    """游客模式解析: bot 不在群时被 @ 召唤, 用 setBotGuestChatResult 直接回一条消息

    注意: query_id 单次有效, 调用失败同样作废, 结果必须在发送前选好, 不能兜底重试。
    不做 platform_filter: 回复别人链接消息时只 @bot 的用法里, 链接在被回复消息里。
    """
    if not message.guest_query_id:
        return
    from_user = message.from_user.id if message.from_user else 0
    async with get_session() as session:
        lang = await UserService(session).get_lang(from_user)
        config = await SettingsService(session).get_config_by_user(from_user)
        _t = t_[lang]

    query = message.text or message.caption or ""
    if not query or ParseService().parser.get_platform(query) is None:
        # 只 @bot 不带链接: 试试被回复消息的文本(回复链在 guest update 的 reference_messages 里)
        ref = message.reply_to_message
        if ref and (t := ref.text or ref.caption or ""):
            query = t
    if ParseService().parser.get_platform(query) is None:
        # 只有主动 @bot 才回馈提示; 回复 bot 消息没链接视为正常聊天, 静默忽略
        entities = message.entities or message.caption_entities or []
        mentioned = any(e.type == enums.MessageEntityType.MENTION for e in entities)
        if mentioned:
            await _answer(cli, message, _text_result(None, _t("请加上链接或回复一条消息")), query)
        else:
            logger.debug(f"guest 查询无有效链接且未 @: {query}")
        return
    logger.info(f"收到游客解析请求: query={query}, from_user={from_user}")

    raw_url = await ParseService().get_raw_url(query)

    if cached := await persistent_cache.get(raw_url):
        logger.debug("guest: 缓存命中")
        results = build_cached_inline_results(cached, raw_url, lang, config)
        result = _pick_result(results, config)
        await _answer(cli, message, result, query)
        return

    parse_result = await parse_cache.get(raw_url)
    if parse_result is None:
        parse_result = await ParseService().parse(query)
        await parse_cache.set(raw_url, parse_result)

    # 富文本/无媒体: 不需要下载, 走 inline 同款文本结果
    if isinstance(parse_result, RichTextParseResult) or not to_list(parse_result.media):
        results = await build_inline_results(parse_result, cli, lang, config)
        result = _to_guest_result(results, parse_result, config)
        await _answer(cli, message, result, query)
        return

    # 有媒体: 下载 → 处理 → 富文本块上传本地文件
    # 文件须在 answer_guest_query 上传完成前存在, 不能先 cleanup
    with ParsePipeline(
        query, raw_url, _GuestReporter(), parse_result=parse_result, singleflight=False, t=_t
    ) as pipeline:
        pr = await pipeline.run()
        if pr is None or not pr.processed_list:
            logger.warning(f"guest 下载失败, 退回文本: {query}")
            result = _text_result(raw_url, build_caption(parse_result, config=config))
        else:
            result = await _to_guest_rich(pr, config)
        await _answer(cli, message, result, query)


async def _answer(cli: Client, message: Message, result: InlineQueryResult | None, query: str) -> None:
    if result is None or not message.guest_query_id:
        logger.warning(f"guest: 无可回复结果, query={query}")
        return
    try:
        sent = await cli.answer_guest_query(message.guest_query_id, result)
        logger.debug(f"guest 回复成功: {sent}")
    except Exception as e:
        logger.warning(f"guest 回复失败({type(e).__name__}): {e}")


def _pick_result(results: list[InlineQueryResult], config: SettingsConfig) -> InlineQueryResult | None:
    """cached 结果里挑一条: 跳过原始链接占位, 取第一个媒体/文本结果"""
    if config.enable_inline_raw_url and results:
        results = results[1:]
    return results[0] if results else None


def _plain_caption(parse_result: AnyParseResult, config: SettingsConfig) -> str:
    """富文本 paragraph 是纯文本, caption 里的 markdown/html 标记会原样泄露, 手工拼"""
    parts = []
    if not config.hide_title and parse_result.title:
        parts.append(parse_result.title)
    if not config.hide_desc and parse_result.content:
        parts.append(parse_result.content)
    caption = "\n\n".join(parts)
    if not config.hide_source:
        caption += f"\n\n▎Source: {parse_result.raw_url}"
    return caption


def _rich_caption_blocks(parse_result: AnyParseResult, config: SettingsConfig) -> list[InputRichBlock]:
    """与常规解析同布局的 caption 块: 粗体标题+短正文 / 标题段 + 可折叠长文, ▎Source 超链接独立段"""
    blocks: list[InputRichBlock] = []
    content = (parse_result.content or "").strip()
    show_desc = not config.hide_desc and bool(content)
    is_long = len(content) > 500 or len(content.splitlines()) > 10

    head: list[RichText | str] = []
    if not config.hide_title and parse_result.title:
        head.append(RichTextBold(parse_result.title))
    if show_desc and not is_long:
        head += ["\n\n", content]
    if head:
        blocks.append(InputRichBlockParagraph(head))  # type: ignore[arg-type]
    if show_desc and is_long:
        if len(content) > 1000:
            content = content[:900] + "......"
        blocks.append(InputRichBlockExpandableBlockQuotation(content))  # type: ignore[arg-type]
    if not config.hide_source:
        source_runs: list[RichText | str] = [
            RichTextBold("▎"),  # type: ignore[arg-type]
            RichTextUrl("Source", parse_result.raw_url),  # type: ignore[arg-type]
        ]
        blocks.append(
            InputRichBlockParagraph(["\n", RichTextBold(source_runs)])  # type: ignore[arg-type]
        )
    return blocks


def _shrink_thumb(img_bytes: bytes, out_path: str) -> str | None:
    """压到 TG thumb 规格(<=320px JPEG)"""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((320, 320))
        img.save(out_path, "JPEG", quality=80)
        return out_path
    except Exception:
        return None


async def _fetch_thumb(url: str, work_dir: str) -> str | None:
    """下载平台缩略图并压到 TG thumb 规格, 失败返回 None"""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return _shrink_thumb(resp.content, os.path.join(work_dir, f"_thumb_{abs(hash(url)) & 0xFFFF:04x}.jpg"))
    except Exception as e:
        logger.debug(f"缩略图获取失败({url}): {e}")
        return None


def _local_thumb(file_path: str, work_dir: str) -> str | None:
    """本地图压到 TG thumb 规格"""
    try:
        with open(file_path, "rb") as f:
            return _shrink_thumb(f.read(), os.path.join(work_dir, f"_thumb_{os.path.basename(file_path)}.jpg"))
    except Exception:
        return None


async def _to_guest_rich(pr: PipelineResult, config: SettingsConfig) -> InlineQueryResult:
    """下载完成 → 本地文件富文本消息: 媒体块在上(多图幻灯片, 动图独立块), caption 块在下

    视频用 thumb(内嵌小图)而不是 video_cover: 富文本场景客户端不渲染 video_cover。
    """
    media_refs = to_list(pr.parse_result.media)
    work_dir = str(pr.output_dir or ".")

    media_blocks: list[InputRichBlock] = []
    animations: list[InputRichBlock] = []
    for media_ref, processed in zip(media_refs, pr.processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width, height, duration = resolve_media_info(processed, file_path_str)

            match processed.source:
                case ImageFile():
                    media_blocks.append(InputRichBlockPhoto(InputMediaPhoto(media_input(file_path_str))))
                case AniFile():
                    animations.append(InputRichBlockAnimation(InputMediaAnimation(media_input(file_path_str))))
                case VideoFile():
                    thumb = await _fetch_thumb(media_ref.thumb_url, work_dir) if media_ref.thumb_url else None
                    media_blocks.append(
                        InputRichBlockVideo(
                            InputMediaVideo(
                                media=media_input(file_path_str),
                                thumb=thumb,
                                duration=duration,
                                width=width,
                                height=height,
                                supports_streaming=True,
                            )
                        )
                    )
                case LivePhotoFile():
                    media_blocks.append(
                        InputRichBlockVideo(
                            InputMediaVideo(
                                media=media_input(processed.source.video_path),
                                thumb=_local_thumb(file_path_str, work_dir),
                                duration=duration,
                                width=width,
                                height=height,
                                supports_streaming=True,
                            )
                        )
                    )

    blocks: list[InputRichBlock] = []
    if len(media_blocks) > 1:
        blocks.append(InputRichBlockSlideshow(media_blocks[:10]))  # 幻灯片张数有上限
    else:
        blocks.extend(media_blocks)
    blocks.extend(animations[:10])
    blocks.extend(_rich_caption_blocks(pr.parse_result, config))

    return InlineQueryResultArticle(
        title=pr.parse_result.title or "-",
        description=pr.parse_result.content,
        input_message_content=InputRichMessageContent(InputRichMessage(blocks=blocks)),
    )


def _text_result(raw_url: str | None, caption: str) -> InlineQueryResult:
    """下载失败/无链接时的保底: 纯文本消息"""
    return InlineQueryResultArticle(
        title="-",
        input_message_content=InputTextMessageContent(
            caption, link_preview_options=LinkPreviewOptions(is_disabled=not raw_url, url=raw_url)
        ),
    )


def _to_guest_result(
    results: list[InlineQueryResult], parse_result: AnyParseResult, config: SettingsConfig
) -> InlineQueryResult | None:
    """把 inline 结果列表转成一条 guest 回复:
    多媒体 → 富文本 collage; 直连视频 → 视频结果; 非直连视频保留封面图+原链接
    """
    if config.enable_inline_raw_url and results:
        results = results[1:]
    if not results:
        return None

    media_list = to_list(parse_result.media)
    caption = build_caption(parse_result, config=config)
    title = parse_result.title or "-"

    def convert(r: InlineQueryResult) -> InlineQueryResult | None:
        # download 占位图 → 直连 mp4 视频结果 (guest 没有 chosen_result 二次上传)
        if not (isinstance(r, InlineQueryResultPhoto) and (r.id or "").startswith("download_")):
            return r
        ref = media_list[int(r.id.split("_")[1])]
        return InlineQueryResultVideo(
            video_url=ref.url,
            thumb_url=ref.thumb_url or DEFAULT_PARSE_RESULT_THUMB_URL,
            title=title,
            caption=caption,
            video_width=ref.width or 0,
            video_height=ref.height or 0,
        )

    converted = [convert(r) for r in results]
    if len(converted) == 1:
        return converted[0]

    # 多个媒体 → 富文本 collage 拼贴(单条消息塞多张)
    blocks: list[InputRichBlock] = []
    for r in converted:
        if isinstance(r, InlineQueryResultPhoto):
            blocks.append(InputRichBlockPhoto(InputMediaPhoto(r.photo_url)))
        elif isinstance(r, InlineQueryResultVideo):
            blocks.append(InputRichBlockVideo(InputMediaVideo(r.video_url, thumb=r.thumb_url)))
        else:
            return converted[0]

    if len(blocks) < 2:
        return converted[0]
    blocks = blocks[:10]

    return InlineQueryResultArticle(
        title=title,
        description=parse_result.content,
        input_message_content=InputRichMessageContent(
            InputRichMessage(
                blocks=[
                    InputRichBlockParagraph(_plain_caption(parse_result, config)),  # type: ignore[arg-type]
                    InputRichBlockCollage(blocks),
                ]
            )
        ),
    )
