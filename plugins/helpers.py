"""plugins 共用的工具函数和数据类"""

from dataclasses import dataclass
from pathlib import Path

from markdown import markdown
from parsehub import Platform
from parsehub.types import AnyMediaFile, AnyParseResult, RichTextParseResult
from parsehub.utils.media_info import MediaInfoReader
from pyrogram import Client

from log import logger
from utils.converter import clean_article_html
from utils.media_processing_unit import MediaProcessingUnit
from utils.ph import Telegraph

logger = logger.bind(name="Helpers")


@dataclass
class ProcessedMedia:
    source: AnyMediaFile
    output_paths: list[Path] | None = None
    output_dir: Path | None = None


def resolve_media_info(processed: "ProcessedMedia", file_path: str) -> tuple[int, int, int]:
    """获取媒体的宽、高、时长。若经过转码则从文件读取，否则使用源信息。"""
    if processed.output_paths:
        info = MediaInfoReader.read(file_path)
        return info.width, info.height, info.duration
    return processed.source.width, processed.source.height, getattr(processed.source, "duration", 0)


def build_caption(parse_result: AnyParseResult, telegraph_url: str | None = None):
    return build_caption_by_str(parse_result.title, parse_result.content, parse_result.raw_url, telegraph_url)


def build_caption_by_str(title: str | None, content: str | None, raw_url: str, telegraph_url: str | None = None) -> str:
    """构建消息正文：标题 + 内容 + 来源链接"""
    title, content = title or "", content or ""

    if telegraph_url:
        label = (title or content[:15]).replace("\n", " ") or "无标题"
        body = f"**[{label}]({telegraph_url})**"
    else:
        parts = []
        if title:
            parts.append(f"**{title}**")
        if content:
            parts.append(content)
        body = format_text("\n\n".join(parts) or "**无标题**")

    return f"{body}\n\n<b>▎<a href='{raw_url}'>Source</a></b>"


def format_text(text: str) -> str:
    """格式化输出内容, 限制长度, 添加折叠块样式"""
    text = text.strip()
    if len(text) > 500 or len(text.splitlines()) > 10:
        if len(text) > 1000:
            text = text[:900] + "......"
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
    logger.debug(f"创建 Telegraph 页面: title={parse_result.title}")
    me = await cli.get_me()
    page = await Telegraph().create_page(
        parse_result.title or "无标题",
        html_content=html_content,
        author_name=me.full_name,
        author_url=parse_result.raw_url,
    )
    logger.debug(f"Telegraph 页面已创建: {page.url}")
    return page.url


async def create_richtext_telegraph(cli: Client, parse_result: RichTextParseResult) -> str:
    """将富文本解析结果转换为 Telegraph 页面，返回页面 URL"""
    logger.debug(f"富文本转 Telegraph: platform={parse_result.platform}, md_len={len(parse_result.markdown_content)}")
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
    processor = MediaProcessingUnit(processed_dir, segment_height=1920, logger=logger.bind(name="MediaProcessor").debug)
    media_files = download_result.media if isinstance(download_result.media, list) else [download_result.media]
    logger.debug(f"开始媒体格式转换: 文件数={len(media_files)}, output_dir={processed_dir}")
    processed_list: list[ProcessedMedia] = []
    for media_file in media_files:
        logger.debug(f"处理文件: {media_file.path}")
        result = await processor.process(media_file.path)
        logger.debug(f"处理结果: output_paths={result.output_paths}")
        processed_list.append(ProcessedMedia(media_file, result.output_paths, result.temp_dir))
    logger.debug(f"媒体格式转换完成: 处理数={len(processed_list)}")
    return processed_list
