import copy

from easy_ai18n import PreLocaleSelector
from parsehub import AnyParseResult
from parsehub.types import RichTextParseResult
from pyrogram import Client, enums, raw
from pyrogram.parser.utils import add_surrogates, remove_surrogates
from pyrogram.types import (
    InlineQueryResult,
    InlineQueryResultArticle,
    InputRichBlock,
    InputRichMessageContent,
    InputTextMessageContent,
    LinkPreviewOptions,
    Message,
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
from plugins.parse.rich import (
    RICH_MEDIA_LIMIT,
    build_rich_media_blocks,
    cached_rich_media_blocks,
    rich_caption_blocks,
    rich_media_messages,
)
from repo.settings import SettingsConfig
from services import ParseService, SettingsService, UserService
from services.cache import CacheEntry, parse_cache, persistent_cache
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
            await responder.answer(_text_result(_t("请加上链接或回复一条消息")))
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
    ) -> None:
        if self.answered:
            logger.warning("guest: 已回复过, 忽略重复回复")
            return
        self.answered = True
        try:
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
                fallback=_text_result(caption),
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

    fallback = _text_result(build_caption(parse_result, config=config))
    with ParsePipeline(
        query,
        raw_url,
        _GuestReporter(),
        parse_result=_limit_media(parse_result),
        singleflight=False,
        t=_t,
    ) as pipeline:
        pr = await pipeline.run()
        if pr is not None and pr.processed_list:
            await responder.answer(await _to_guest_rich(pr, config), fallback=fallback)
        else:
            await responder.answer(fallback)


def _limit_media(parse_result: AnyParseResult) -> AnyParseResult:
    media = to_list(parse_result.media)
    if len(media) <= RICH_MEDIA_LIMIT:
        return parse_result
    limited = copy.copy(parse_result)
    limited.media = media[:RICH_MEDIA_LIMIT]
    return limited


def _guest_article(
    media_blocks: list[InputRichBlock],
    title: str | None,
    content: str | None,
    raw_url: str,
    config: SettingsConfig,
) -> InlineQueryResultArticle:
    message = rich_media_messages(
        media_blocks[:RICH_MEDIA_LIMIT],
        rich_caption_blocks(title, content, raw_url, config),
        slideshow=config.rich_slideshow,
        limit=RICH_MEDIA_LIMIT,
    )[0]
    return InlineQueryResultArticle(
        title=title or "-",
        description=content,
        input_message_content=InputRichMessageContent(message),
    )


async def _to_guest_rich(pr: PipelineResult, config: SettingsConfig) -> InlineQueryResultArticle:
    """下载完成 → 本地文件富文本消息: 媒体块在上(幻灯片), caption 块在下"""
    return _guest_article(
        await build_rich_media_blocks(pr, video_cover=True),
        pr.parse_result.title,
        pr.parse_result.content,
        pr.parse_result.raw_url,
        config,
    )


def _cached_rich_result(entry: CacheEntry, raw_url: str, config: SettingsConfig) -> InlineQueryResultArticle:
    return _guest_article(
        cached_rich_media_blocks(entry.media or []),
        entry.parse_result.title,
        entry.parse_result.content,
        raw_url,
        config,
    )


def _text_result(caption: str) -> InlineQueryResult:
    """下载失败/无链接时的保底: 纯文本消息"""
    return InlineQueryResultArticle(
        title="-",
        input_message_content=InputTextMessageContent(
            caption,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        ),
    )


def _error_result(_t: PreLocaleSelector, error: Exception) -> InlineQueryResult:
    stage = "解析"
    text = _t(f"{format_label(f'{stage}错误:')} \n```\n{error}```")
    if bs.demo_mode:
        text += _t("\n\n<b>问题反馈: @MisakaSisters</b>")
    return _text_result(text)
