"""plugins 共用的工具函数和数据类"""

import asyncio
import re
from html.parser import HTMLParser
from typing import cast
from urllib.parse import urlsplit

from easy_ai18n import LocaleContent
from markdown import markdown
from parsehub import ParseHub, Platform
from parsehub.types import AnyParseResult, RichTextParseResult
from pyrogram import Client
from pyrogram.types import (
    InputRichBlockDetails,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockTable,
    InputRichMessage,
    Message,
    RichBlockTableCell,
    RichText,
    RichTextBold,
    RichTextCode,
    RichTextUrl,
)

from i18n import t_
from log import logger
from repo.settings import SettingsConfig
from utils.converter import clean_article_html
from utils.ph import Telegraph

logger = logger.bind(name="Helpers")

COMMANDS = {
    "start": t_("开始"),
    "jx": t_("解析并预览内容"),
    "raw": t_("发送原文件, 避免画质压缩"),
    "zip": t_("打包发送, 附带解析信息"),
    "jxjx": t_("绕过缓存解析"),
    "lang": t_("语言"),
    "cfg": t_("配置"),
    "ocfg": t_("旧版配置菜单"),
}


def build_start_text() -> LocaleContent:
    return t_(
        f"**发送分享链接以进行解析**\n\n"
        f"**支持的平台:**\n"
        f"<blockquote expandable>{get_supported_platforms()}</blockquote>\n\n"
        f"**命令列表:**\n"
        f"<blockquote expandable>"
        f"/jx <链接> - 解析并预览内容\n"
        f"/raw <链接> - 发送原文件, 避免画质压缩\n"
        f"/zip <链接> - 打包发送, 附带解析信息\n"
        f"/jxjx <链接> - 绕过缓存解析\n"
        f"/lang - 语言\n"
        f"/cfg - 配置\n"
        f"/cfg <频道用户名/链接/id> - 频道配置\n"
        f"/ocfg - 旧版配置菜单\n"
        f"</blockquote>\n\n"
        f"**开源地址: [GitHub](https://github.com/z-mio/parse_hub_bot)**"
    )


GITHUB_REPO_URL = "https://github.com/z-mio/parse_hub_bot"


def _r(value: object) -> RichText:
    """kurigram 的 RichText 参数运行时可接受 str/list，但标注只写了 RichText 类"""
    return cast("RichText", value)


def _platform_table(lang: str) -> InputRichBlockTable:
    header = [
        RichBlockTableCell(text=_r(t_("平台")[lang]), is_header=True),
        RichBlockTableCell(text=_r(t_("支持类型")[lang]), is_header=True),
    ]
    rows = [
        [
            RichBlockTableCell(text=_r(i["name"])),
            RichBlockTableCell(text=_r(", ".join(i["supported_types"]))),
        ]
        for i in sorted(ParseHub().get_platforms(), key=lambda i: i["name"], reverse=True)
    ]
    return InputRichBlockTable(cells=[header, *rows], is_bordered=True, is_striped=True)


def build_help_rich_message(lang: str) -> InputRichMessage:
    """以 RichMessage blocks 形式构建 /help 富文本文档"""
    command_lines = [
        ("jx", f" <{t_('链接')[lang]}>"),
        ("raw", f" <{t_('链接')[lang]}>"),
        ("zip", f" <{t_('链接')[lang]}>"),
        ("jxjx", f" <{t_('链接')[lang]}>"),
        ("lang", ""),
        ("cfg", ""),
    ]
    command_items = [
        InputRichBlockListItem(
            blocks=[
                InputRichBlockParagraph(
                    _r(
                        [
                            RichTextCode(_r(f"/{cmd}")),
                            f"{suffix} - {COMMANDS[cmd][lang]}",
                        ]
                    )
                )
            ]
        )
        for cmd, suffix in command_lines
    ]
    command_items.append(
        InputRichBlockListItem(
            blocks=[
                InputRichBlockParagraph(
                    _r(
                        [
                            RichTextCode(_r("/cfg")),
                            f" <{t_('频道用户名/链接/id')[lang]}> - {t_('频道配置')[lang]}",
                        ]
                    )
                )
            ]
        )
    )
    command_items.append(
        InputRichBlockListItem(
            blocks=[
                InputRichBlockParagraph(
                    _r(
                        [
                            RichTextCode(_r("/ocfg")),
                            f" - {COMMANDS['ocfg'][lang]}",
                        ]
                    )
                )
            ]
        )
    )

    return InputRichMessage(
        blocks=[
            InputRichBlockParagraph(text=_r(t_("发送分享链接以进行解析")[lang])),
            InputRichBlockDetails(
                summary=_r(t_("支持的平台")[lang]),
                blocks=[_platform_table(lang)],
            ),
            InputRichBlockDetails(
                summary=_r(t_("命令列表")[lang]),
                blocks=[InputRichBlockList(items=command_items)],
            ),
            InputRichBlockParagraph(
                _r(RichTextBold(_r([t_("开源地址")[lang], ": ", RichTextUrl(_r("GitHub"), GITHUB_REPO_URL)])))
            ),
        ]
    )


def build_caption(
    parse_result: AnyParseResult,
    telegraph_url: str | None = None,
    *,
    custom_content: str = "",
    config: SettingsConfig,
    rich: bool = False,
) -> str:
    return build_caption_by_str(
        parse_result.title,
        replace_url(parse_result.platform, parse_result.markdown_content)
        if rich and isinstance(parse_result, RichTextParseResult)
        else parse_result.content,
        parse_result.raw_url,
        telegraph_url,
        hide_source=config.hide_source,
        custom_content=custom_content,
        hide_title=config.hide_title,
        hide_desc=config.hide_desc,
        rich=rich,
    )


def build_caption_by_str(
    title: str | None,
    content: str | None,
    raw_url: str,
    telegraph_url: str | None = None,
    *,
    hide_source: bool = False,
    custom_content: str = "",
    hide_title: bool = False,
    hide_desc: bool = False,
    rich: bool = False,
) -> str:
    """构建消息正文：标题 + 内容 + 来源链接"""
    title, content = title or "", content or ""
    if rich:
        body = f"### {title}\n\n <details><summary>📃</summary>\n\n{content}\n\n</details>"
    elif telegraph_url:
        label = (title or content[:15]).replace("\n", " ") or "-"
        body = f"**[{label}]({telegraph_url})**"
    else:
        parts = []
        if not hide_title and title:
            parts.append(f"**{title}**")
        if not hide_desc and content:
            parts.append(content)
        body = format_text(("\n\n".join(parts)).strip())

    if custom_content:
        body += f"\n\n{custom_content}"

    if hide_source:
        return body
    return f"{body}\n\n{format_label(f"<a href='{raw_url}'>Source</a>")}"


def format_text(text: str) -> str:
    """格式化输出内容, 限制长度, 添加折叠块样式"""
    text = text.strip()
    if len(text) > 500 or len(text.splitlines()) > 10:
        if len(text) > 1000:
            text = text[:900] + "......"
        return f"<blockquote expandable>{text}</blockquote>"
    else:
        return text


# Telegraph 单页内容上限约 64KB, 预留空间给分页导航
TELEGRAPH_PAGE_MAX_BYTES = 60_000

_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


def _split_html_blocks(html: str) -> list[str]:
    """按顶层块级元素把 HTML 切成若干块, 每块是一个完整元素"""
    line_offsets = [0]
    for m in re.finditer("\n", html):
        line_offsets.append(m.end())

    class _Splitter(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=False)
            self.depth = 0
            self.block_start: int | None = None
            self.blocks: list[tuple[int, int]] = []

        def _offset(self) -> int:
            line, col = self.getpos()
            return line_offsets[line - 1] + col

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if self.depth == 0:
                self.block_start = self._offset()
            if tag not in _VOID_TAGS:
                self.depth += 1

        def handle_startendtag(self, tag: str, attrs: list) -> None:
            if self.depth == 0:
                start = self._offset()
                self.blocks.append((start, start + len(self.get_starttag_text() or "")))

        def handle_endtag(self, tag: str) -> None:
            if tag in _VOID_TAGS:
                return
            if self.depth > 0:
                self.depth -= 1
            if self.depth == 0 and self.block_start is not None:
                end = html.find(">", self._offset()) + 1
                self.blocks.append((self.block_start, end))
                self.block_start = None

    splitter = _Splitter()
    splitter.feed(html)
    splitter.close()
    return [html[s:e] for s, e in splitter.blocks] or [html]


def _pack_page_chunks(blocks: list[str], max_bytes: int = TELEGRAPH_PAGE_MAX_BYTES) -> list[str]:
    """把块按字节数装箱成若干页"""
    chunks: list[str] = []
    cur: list[str] = []
    cur_size = 0
    for block in blocks:
        size = len(block.encode())
        if cur and cur_size + size > max_bytes:
            chunks.append("".join(cur))
            cur, cur_size = [], 0
        cur.append(block)
        cur_size += size
    if cur:
        chunks.append("".join(cur))
    return chunks


def _page_nav(prev_url: str | None, next_url: str | None) -> str:
    links = []
    if prev_url:
        links.append(f'<a href="{prev_url}">← 上一页</a>')
    if next_url:
        links.append(f'<a href="{next_url}">下一页 →</a>')
    return f"<p>{' ｜ '.join(links)}</p>"


async def create_telegraph_page(html_content: str, cli: Client, parse_result: AnyParseResult) -> str:
    """创建 Telegraph 页面，返回页面 URL。内容超过 Telegraph 上限时分页互链，仍返回第一页 URL"""
    logger.debug(f"创建 Telegraph 页面: title={parse_result.title}")
    me = await cli.get_me()
    author_name = f"{me.full_name} | @{me.username}"
    title = parse_result.title or "-"
    telegraph = Telegraph()

    chunks = _pack_page_chunks(_split_html_blocks(html_content))
    if len(chunks) == 1:
        page = await telegraph.create_page(
            title,
            html_content=chunks[0],
            author_name=author_name,
            author_url=parse_result.raw_url,
        )
        logger.debug(f"Telegraph 页面已创建: {page.url}")
        return page.url

    total = len(chunks)
    logger.debug(f"Telegraph 内容超限, 分页创建: {total} 页")
    pages = []
    for i, chunk in enumerate(chunks):
        page = await telegraph.create_page(
            f"{title} ({i + 1}/{total})",
            html_content=chunk,
            author_name=author_name,
            author_url=parse_result.raw_url,
        )
        pages.append(page)
        await asyncio.sleep(0.5)

    for i, page in enumerate(pages):
        prev_url = pages[i - 1].url if i > 0 else None
        next_url = pages[i + 1].url if i < total - 1 else None
        await telegraph.edit_page(
            page.path,
            f"{title} ({i + 1}/{total})",
            html_content=chunks[i] + _page_nav(prev_url, next_url),
            author_name=author_name,
            author_url=parse_result.raw_url,
        )
        await asyncio.sleep(0.5)

    logger.debug(f"Telegraph 分页已创建: {pages[0].url} 共 {total} 页")
    return pages[0].url


def replace_url(platform: Platform | None, v: str) -> str:
    match platform:
        case Platform.WEIXIN:
            v = v.replace("mmbiz.qpic.cn", "qpic.cn.in/mmbiz.qpic.cn")
        case Platform.COOLAPK:
            v = v.replace("image.coolapk.com", "qpic.cn.in/image.coolapk.com")
        case Platform.DOUBAN:
            # 豆瓣图片分片域名 img1~imgN.doubanio.com
            v = re.sub(r"img\d+\.doubanio\.com", r"qpic.cn.in/\g<0>", v)
    return v


async def create_richtext_telegraph(cli: Client, parse_result: RichTextParseResult) -> str:
    """将富文本解析结果转换为 Telegraph 页面，返回页面 URL"""
    logger.debug(f"富文本转 Telegraph: platform={parse_result.platform}, md_len={len(parse_result.markdown_content)}")
    md = replace_url(parse_result.platform, parse_result.markdown_content)
    html = clean_article_html(markdown(md))
    return await create_telegraph_page(html, cli, parse_result)


def get_supported_platforms() -> str:
    text: list[str] = []
    for i in ParseHub().get_platforms():
        text.append(f"**{i['name']}** __({'__, __'.join(i['supported_types'])})__")
    text.sort(reverse=True)
    return "\n".join(text)


def format_label(text: str) -> str:
    return f"<b>▎{text}</b>"


def parse_channel_ref(value: str) -> int | str:
    """解析频道 ID、用户名或 Telegram 链接，忽略 URL 参数、片段和消息 ID。"""
    channel_id_re = re.compile(r"-100\d{1,19}\Z")
    internal_channel_id_re = re.compile(r"[1-9]\d{0,19}\Z")
    username_re = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}\Z")
    telegram_link_hosts = frozenset({"t.me", "telegram.me"})

    value = value.strip()
    if not value:
        raise ValueError("频道引用不能为空")

    if channel_id_re.fullmatch(value):
        return int(value)

    url = urlsplit(value if "://" in value else f"https://{value}")
    if url.netloc.lower() in telegram_link_hosts:
        if url.scheme not in {"http", "https"}:
            raise ValueError("仅支持 HTTP 或 HTTPS Telegram 链接")

        path_parts = tuple(part for part in url.path.split("/") if part)
        match path_parts:
            case ("c", internal_channel_id) | ("c", internal_channel_id, _):
                if not internal_channel_id_re.fullmatch(internal_channel_id):
                    raise ValueError("无效的 /c/ 频道链接")
                return int(f"-100{internal_channel_id}")

            case (username,):
                if username_re.fullmatch(username):
                    return f"@{username}"
                raise ValueError("频道用户名格式无效")

            case _:
                raise ValueError("Telegram 链接必须包含用户名或 /c/ 频道 ID")

    if "://" in value:
        raise ValueError("仅支持 t.me 或 telegram.me 链接")

    username = value.removeprefix("@")
    if not username_re.fullmatch(username):
        raise ValueError("频道用户名格式无效")

    return f"@{username}"


def get_thread_id(msg: Message) -> int | None:
    return msg.message_thread_id or (1 if msg.chat and msg.chat.is_forum else None)
