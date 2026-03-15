"""plugins 共用的工具函数和数据类"""

from dataclasses import dataclass
from pathlib import Path

from markdown import markdown
from parsehub import Platform
from parsehub.types import AnyMediaFile, AnyParseResult, RichTextParseResult
from pyrogram import Client

from utils.converter import clean_article_html
from utils.media_processing_unit import MediaProcessingUnit
from utils.ph import Telegraph


@dataclass
class ProcessedMedia:
    source: AnyMediaFile
    output_paths: list[Path] | None = None
    output_dir: Path | None = None


def build_caption(parse_result: AnyParseResult, telegraph_url: str = None) -> str:
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


async def create_telegraph_page(html_content: str, cli: Client, parse_result: AnyParseResult) -> str:
    """创建 Telegraph 页面，返回页面 URL"""
    me = await cli.get_me()
    page = await Telegraph().create_page(
        parse_result.title or "无标题",
        html_content=html_content,
        author_name=me.full_name,
        author_url=parse_result.raw_url,
    )
    return page.url


async def create_richtext_telegraph(cli: Client, parse_result: RichTextParseResult) -> str:
    """将富文本解析结果转换为 Telegraph 页面，返回页面 URL"""
    md = parse_result.markdown_content
    if parse_result.platform == Platform.WEIXIN:
        md = md.replace("mmbiz.qpic.cn", "mmbiz.qpic.cn.in")
    elif parse_result.platform == Platform.COOLAPK:
        md = md.replace("image.coolapk.com", "qpic.cn.in/image.coolapk.com")
    html = clean_article_html(markdown(md))
    return await create_telegraph_page(html, cli, parse_result)


async def process_media_files(download_result) -> list[ProcessedMedia]:
    """对下载结果中的媒体文件进行格式转换，返回 ProcessedMedia 列表"""
    processed_dir = download_result.output_dir.joinpath("processed")
    processor = MediaProcessingUnit(processed_dir)
    media_files = download_result.media if isinstance(download_result.media, list) else [download_result.media]
    processed_list: list[ProcessedMedia] = []
    for media_file in media_files:
        result = await processor.process(media_file.path)
        processed_list.append(ProcessedMedia(media_file, result.output_paths, result.temp_dir))
    return processed_list
