import asyncio
import copy

from easy_ai18n import PreLocaleSelector
from parsehub import AnyParseResult
from parsehub.types import AniFile, AniRef, ImageFile, LivePhotoFile, RichTextParseResult, VideoFile
from pyrogram import Client, enums, raw
from pyrogram.parser.utils import add_surrogates, remove_surrogates
from pyrogram.types import (
    InlineQueryResult,
    InlineQueryResultArticle,
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    InputRichBlock,
    InputRichBlockAnimation,
    InputRichBlockDocument,
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

from core import bs
from db import get_session
from i18n import t_
from log import logger
from plugins.helpers import build_caption, build_caption_by_str, format_label
from plugins.parse.inline import (
    build_cached_inline_results,
    build_inline_results,
)
from plugins.parse.sender import media_input
from repo.settings import SettingsConfig
from services import ParseService, SettingsService, UserService
from services.cache import CacheEntry, CacheMediaType, parse_cache, persistent_cache
from services.media import fetch_thumb, make_thumb, resolve_media_info
from services.pipeline import ParsePipeline, PipelineResult, StatusReporter
from utils.helpers import to_list, with_request_id

logger = logger.bind(name="GuestParse")
GUEST_MEDIA_LIMIT = 10
GUEST_TIMEOUT = 120


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

    注意: query_id 单次有效, 媒体先上传再提交结果; 提交后不可重试。
    不做 platform_filter: 回复别人链接消息时只 @bot 的用法里, 链接在被回复消息里。
    """
    if not message.guest_query_id:
        return
    from_user = message.from_user.id if message.from_user else 0
    async with get_session() as session:
        lang = await UserService(session).get_lang(from_user)
        config = await SettingsService(session).get_config_by_user(from_user)
        _t = t_[lang]

    responder = _GuestResponder(cli, message.guest_query_id)
    query = _resolve_query(cli, message)
    logger.info(f"收到游客解析请求: query={query}, from_user={from_user}")
    if query is None:
        if _mentions_me(cli, message):
            await responder.answer(_text_result(None, _t("请加上链接或回复一条消息")))
        else:
            logger.debug("guest 查询无有效链接且未 @")
        return

    try:
        await _guest_parse(cli, responder, query, lang, config, _t)
    except Exception as e:
        logger.opt(exception=e).debug("详细堆栈")
        logger.error(f"guest 解析失败: {e}")
        if not responder.answered and not config.hide_error:
            await responder.answer(_error_result(_t, e))


class _GuestResponder:
    """query_id 单次有效(失败也消耗): 整个请求只允许一次 SetBotGuestChatResult"""

    def __init__(self, cli: Client, guest_query_id: str) -> None:
        self._cli = cli
        self._query_id = guest_query_id
        self.answered = False

    async def answer(
        self,
        result: InlineQueryResult,
        *,
        fallback: InlineQueryResult | None = None,
        deadline: float | None = None,
    ) -> None:
        if self.answered:
            logger.warning("guest: 已回复过, 忽略重复回复")
            return
        self.answered = True
        try:
            async with asyncio.timeout_at(deadline):
                written = await result.write(self._cli)
        except Exception as e:
            if fallback is None:
                logger.warning(f"guest 结果构建失败({type(e).__name__}): {e}")
                return
            logger.warning(f"guest 上传失败, 退回文本({type(e).__name__}): {e}")
            try:
                written = await fallback.write(self._cli)
            except Exception as e2:
                logger.warning(f"guest 文本兜底构建失败({type(e2).__name__}): {e2}")
                return
        try:
            r = await self._cli.invoke(
                raw.functions.messages.SetBotGuestChatResult(query_id=int(self._query_id), result=written)
            )
            logger.debug(f"guest 回复成功: {r}")
        except Exception as e:
            logger.warning(f"guest 回复失败({type(e).__name__}): {e}")


def _mentions_me(cli: Client, message: Message) -> bool:
    username = cli.me.username if cli.me else None
    if not username:
        return False
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    s = add_surrogates(text)
    return any(
        e.type == enums.MessageEntityType.MENTION
        and remove_surrogates(s[e.offset : e.offset + e.length]).lower() == f"@{username}".lower()
        for e in entities
    )


def _resolve_query(cli: Client, message: Message) -> str | None:
    query = message.text or message.caption or ""
    if ParseService().parser.get_platform(query) is not None:
        return query
    if _mentions_me(cli, message):
        reply = message.reply_to_message
        query = (reply.text or reply.caption or "") if reply else ""
        if ParseService().parser.get_platform(query) is not None:
            return query
    return None


def _first_result(results: list[InlineQueryResult], config: SettingsConfig) -> InlineQueryResult | None:
    """跳过原始链接占位, 取第一个媒体/文本结果"""
    if config.enable_inline_raw_url and results:
        results = results[1:]
    return results[0] if results else None


def _rich_caption_blocks(
    title: str | None, content: str | None, raw_url: str, config: SettingsConfig
) -> list[InputRichBlock]:
    """与常规解析同布局的 caption 块: 粗体标题+短正文 / 标题段 + 可折叠长文, ▎Source 超链接独立段"""
    blocks: list[InputRichBlock] = []
    content = (content or "").strip()
    show_desc = not config.hide_desc and bool(content)
    is_long = len(content) > 500 or len(content.splitlines()) > 10

    head: list[RichText | str] = []
    if not config.hide_title and title:
        head.append(RichTextBold(title))  # type: ignore[arg-type]
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
            RichTextUrl("Source", raw_url),  # type: ignore[arg-type]
        ]
        blocks.append(
            InputRichBlockParagraph(["\n", RichTextBold(source_runs)])  # type: ignore[arg-type]
        )
    return blocks


async def _guest_parse(
    cli: Client,
    responder: _GuestResponder,
    query: str,
    lang: str,
    config: SettingsConfig,
    _t: PreLocaleSelector,
) -> None:
    raw_url = await ParseService().get_raw_url(query)

    if cached := await persistent_cache.get(raw_url):
        logger.debug("guest: 缓存命中")
        if cached.media:
            caption = build_caption_by_str(
                cached.parse_result.title,
                cached.parse_result.content,
                raw_url,
                cached.telegraph_url,
                hide_source=config.hide_source,
                hide_title=config.hide_title,
                hide_desc=config.hide_desc,
            )
            await responder.answer(
                _cached_rich_result(cached, raw_url, config),
                fallback=_text_result(raw_url, caption),
            )
        else:
            result = _first_result(build_cached_inline_results(cached, raw_url, lang, config), config)
            if result is None:
                logger.warning(f"guest: 无可回复结果, query={query}")
            else:
                await responder.answer(result)
        return

    parse_result = await parse_cache.get(raw_url)
    if parse_result is None:
        parse_result = await ParseService().parse(query)
        await parse_cache.set(raw_url, parse_result)

    if isinstance(parse_result, RichTextParseResult) or not to_list(parse_result.media):
        result = _first_result(await build_inline_results(parse_result, cli, lang, config), config)
        if result is None:
            logger.warning(f"guest: 无可回复结果, query={query}")
        else:
            await responder.answer(result)
        return

    deadline = asyncio.get_running_loop().time() + GUEST_TIMEOUT
    fallback = _text_result(raw_url, build_caption(parse_result, config=config))
    with ParsePipeline(
        query,
        raw_url,
        _GuestReporter(),
        parse_result=_limit_media(parse_result),
        singleflight=False,
        t=_t,
    ) as pipeline:
        result = None
        try:
            async with asyncio.timeout_at(deadline):
                pr = await pipeline.run()
                if pr is not None and pr.processed_list:
                    result = await _to_guest_rich(pr, config)
        except TimeoutError:
            logger.warning(f"guest 下载/处理超时, 退回文本: {query}")
        if result is None:
            await responder.answer(fallback)
        else:
            await responder.answer(result, fallback=fallback, deadline=deadline)


def _limit_media(parse_result: AnyParseResult) -> AnyParseResult:
    media = to_list(parse_result.media)
    kept: list = []
    ani_count = 0
    other_count = 0
    for ref in media:
        if isinstance(ref, AniRef):
            if ani_count >= GUEST_MEDIA_LIMIT:
                continue
            ani_count += 1
        else:
            if other_count >= GUEST_MEDIA_LIMIT:
                continue
            other_count += 1
        kept.append(ref)
    if len(kept) == len(media):
        return parse_result
    limited = copy.copy(parse_result)
    limited.media = kept
    return limited


def _assemble_rich(
    media_blocks: list[InputRichBlock],
    standalone: list[InputRichBlock],
    title: str | None,
    content: str | None,
    raw_url: str,
    config: SettingsConfig,
) -> InlineQueryResultArticle:
    blocks: list[InputRichBlock] = []
    media_blocks = media_blocks[:GUEST_MEDIA_LIMIT]
    if len(media_blocks) > 1:
        blocks.append(InputRichBlockSlideshow(media_blocks))
    else:
        blocks.extend(media_blocks)
    blocks.extend(standalone[:GUEST_MEDIA_LIMIT])
    blocks.extend(_rich_caption_blocks(title, content, raw_url, config))
    return InlineQueryResultArticle(
        title=title or "-",
        description=content,
        input_message_content=InputRichMessageContent(InputRichMessage(blocks=blocks)),
    )


async def _to_guest_rich(pr: PipelineResult, config: SettingsConfig) -> InlineQueryResultArticle:
    """下载完成 → 本地文件富文本消息: 媒体块在上(多图幻灯片, 动图独立块), caption 块在下"""
    media_refs = to_list(pr.parse_result.media)
    media_blocks: list[InputRichBlock] = []
    standalone: list[InputRichBlock] = []
    thumb_index = 0
    for media_ref, processed in zip(media_refs, pr.processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width, height, duration = resolve_media_info(processed, file_path_str)

            match processed.source:
                case ImageFile():
                    media_blocks.append(InputRichBlockPhoto(InputMediaPhoto(media_input(file_path_str))))
                case AniFile():
                    standalone.append(InputRichBlockAnimation(InputMediaAnimation(media_input(file_path_str))))
                case VideoFile():
                    thumb = None
                    if pr.output_dir is not None:
                        thumb_path = pr.output_dir / f"_thumb_{thumb_index}.jpg"
                        thumb_index += 1
                        if media_ref.thumb_url:
                            thumb = await fetch_thumb(media_ref.thumb_url, thumb_path)
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
                    thumb = None
                    if pr.output_dir is not None:
                        thumb_path = pr.output_dir / f"_thumb_{thumb_index}.jpg"
                        thumb_index += 1
                        thumb = make_thumb(file_path_str, thumb_path)
                    media_blocks.append(
                        InputRichBlockVideo(
                            InputMediaVideo(
                                media=media_input(processed.source.video_path),
                                thumb=thumb,
                                duration=duration,
                                width=width,
                                height=height,
                                supports_streaming=True,
                            )
                        )
                    )

    return _assemble_rich(
        media_blocks,
        standalone,
        pr.parse_result.title,
        pr.parse_result.content,
        pr.parse_result.raw_url,
        config,
    )


def _cached_rich_result(entry: CacheEntry, raw_url: str, config: SettingsConfig) -> InlineQueryResultArticle:
    media_blocks: list[InputRichBlock] = []
    standalone: list[InputRichBlock] = []
    for media in entry.media or []:
        match media.type:
            case CacheMediaType.PHOTO:
                media_blocks.append(InputRichBlockPhoto(InputMediaPhoto(media.file_id)))
            case CacheMediaType.VIDEO:
                media_blocks.append(InputRichBlockVideo(InputMediaVideo(media.file_id, supports_streaming=True)))
            case CacheMediaType.ANIMATION:
                standalone.append(InputRichBlockAnimation(InputMediaAnimation(media.file_id)))
            case CacheMediaType.DOCUMENT:
                standalone.append(InputRichBlockDocument(InputMediaDocument(media.file_id)))
    return _assemble_rich(
        media_blocks,
        standalone,
        entry.parse_result.title,
        entry.parse_result.content,
        raw_url,
        config,
    )


def _text_result(raw_url: str | None, caption: str) -> InlineQueryResult:
    """下载失败/无链接时的保底: 纯文本消息"""
    return InlineQueryResultArticle(
        title="-",
        input_message_content=InputTextMessageContent(
            caption,
            link_preview_options=LinkPreviewOptions(
                is_disabled=not raw_url, url=raw_url, show_above_text=bool(raw_url)
            ),
        ),
    )


def _error_result(_t: PreLocaleSelector, error: Exception) -> InlineQueryResult:
    stage = "解析"
    text = _t(f"{format_label(f'{stage}错误:')} \n```\n{error}```")
    if bs.demo_mode:
        text += _t("\n\n<b>问题反馈: @MisakaSisters</b>")
    return _text_result(None, text)
