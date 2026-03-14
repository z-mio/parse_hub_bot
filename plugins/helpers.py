"""plugins 共用的工具函数和数据类"""

from dataclasses import dataclass
from pathlib import Path

from parsehub.types import AnyMediaFile, ParseResult
from pyrogram import Client

from utils.ph import Telegraph


@dataclass
class ProcessedMedia:
    source: AnyMediaFile
    output_paths: list[Path] | None = None
    output_dir: Path | None = None


def build_caption(parse_result: ParseResult, telegraph_url: str = None) -> str:
    """构建消息正文：标题 + 内容 + 来源链接"""
    if telegraph_url:
        body = f"**[{parse_result.title.replace(chr(10), ' ') or '无标题'}]({telegraph_url})**"
    else:
        body = (
            format_text(f"**{parse_result.title}**\n\n{parse_result.content}")
            if parse_result.title or parse_result.content
            else "无标题"
        ).strip()
    return f"{body}\n\n<b>▎[Source]({parse_result.raw_url})</b>".strip()


def format_text(text: str) -> str:
    """格式化输出内容, 限制长度, 添加折叠块样式"""
    text = text.strip()
    if len(text) > 1000:
        text = text[:900] + "......"
        return f"<blockquote expandable>{text}</blockquote>"
    elif len(text) > 500 or len(text.splitlines()) > 10:
        return f"<blockquote expandable>{text}</blockquote>"
    else:
        return text


def progress(current: int, total: int, unit: str):
    text = f"下 载 中... | {f'{current * 100 / total:.0f}%' if unit == 'bytes' else f'{current}/{total}'}"
    if unit == "bytes":
        if round(current * 100 / total, 1) % 25 == 0:
            return text
    else:
        if (current + 1) % 3 == 0 or (current + 1) == total:
            return text
    return None


async def create_telegraph_page(html_content: str, cli: Client, parse_result: ParseResult) -> str:
    """创建 Telegraph 页面，返回页面 URL"""
    me = await cli.get_me()
    page = await Telegraph().create_page(
        parse_result.title or "无标题",
        html_content=html_content,
        author_name=me.full_name,
        author_url=parse_result.raw_url,
    )
    return page.url
