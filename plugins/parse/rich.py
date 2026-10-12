import html
import re
from itertools import batched

from parsehub.types import (
    AniFile,
    AnyParseResult,
    ImageFile,
    ImageParseResult,
    LivePhotoFile,
    MultimediaParseResult,
    VideoFile,
    VideoRef,
)
from pyrogram.types import (
    InputMediaAnimation,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    InputRichBlock,
    InputRichBlockAnimation,
    InputRichBlockCollage,
    InputRichBlockDetails,
    InputRichBlockDocument,
    InputRichBlockExpandableBlockQuotation,
    InputRichBlockParagraph,
    InputRichBlockPhoto,
    InputRichBlockSlideshow,
    InputRichBlockVideo,
    InputRichMessage,
    RichText,
    RichTextBold,
    RichTextUrl,
)

from repo.settings import SettingsConfig
from services import CacheMedia, CacheMediaType, PipelineResult
from services.media import fetch_thumb, make_thumb, resolve_media_info
from utils.helpers import to_list

# 实测一条富文本消息的幻灯片/拼图可容纳 50 个媒体
RICH_MEDIA_LIMIT = 50
# 拼图布局下超过该数量的媒体折叠进详情块, 避免长帖刷屏
COLLAGE_FOLD_THRESHOLD = 10


def _strip_markup(text: str) -> str:
    return html.unescape(re.sub(r"</?[^>]+>", "", text))


def is_rich_media_result(parse_result: AnyParseResult) -> bool:
    """图文/多媒体结果且媒体不全是视频 (纯视频帖子走常规视频发送)"""
    if not isinstance(parse_result, ImageParseResult | MultimediaParseResult):
        return False
    return not all(isinstance(m, VideoRef) for m in to_list(parse_result.media))


def rich_caption_blocks(
    title: str | None,
    content: str | None,
    raw_url: str,
    config: SettingsConfig,
    *,
    custom_content: str = "",
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
    if custom_content:
        blocks.append(InputRichBlockParagraph(_strip_markup(custom_content)))  # type: ignore[arg-type]
    if not config.hide_source:
        source_runs: list[RichText | str] = [
            RichTextBold("▎"),  # type: ignore[arg-type]
            RichTextUrl("Source", raw_url),  # type: ignore[arg-type]
        ]
        blocks.append(
            InputRichBlockParagraph(["\n", RichTextBold(source_runs)])  # type: ignore[arg-type]
        )
    return blocks


async def build_rich_media_blocks(
    pr: PipelineResult, *, video_cover: bool, skip_gifs: bool = False
) -> list[InputRichBlock]:
    """下载完成 → 按帖子原始顺序的媒体块(图片/视频/动图), 上层自行决定哪些进幻灯片"""
    media_refs = to_list(pr.parse_result.media)
    blocks: list[InputRichBlock] = []
    thumb_index = 0
    for media_ref, processed in zip(media_refs, pr.processed_list, strict=False):
        file_paths = processed.output_paths or [processed.source.path]
        for file_path in file_paths:
            file_path_str = str(file_path)
            width, height, duration = resolve_media_info(processed, file_path_str)

            match processed.source:
                case ImageFile():
                    blocks.append(InputRichBlockPhoto(InputMediaPhoto(file_path_str)))
                case AniFile():
                    if not skip_gifs:
                        blocks.append(InputRichBlockAnimation(InputMediaAnimation(file_path_str)))
                case VideoFile():
                    thumb = None
                    if video_cover and pr.output_dir is not None:
                        thumb_path = pr.output_dir / f"_thumb_{thumb_index}.jpg"
                        thumb_index += 1
                        if media_ref.thumb_url:
                            thumb = await fetch_thumb(media_ref.thumb_url, thumb_path)
                    blocks.append(
                        InputRichBlockVideo(
                            InputMediaVideo(
                                media=file_path_str,
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
                    if video_cover and pr.output_dir is not None:
                        thumb_path = pr.output_dir / f"_thumb_{thumb_index}.jpg"
                        thumb_index += 1
                        thumb = make_thumb(file_path_str, thumb_path)
                    blocks.append(
                        InputRichBlockVideo(
                            InputMediaVideo(
                                media=processed.source.video_path,
                                thumb=thumb,
                                duration=duration,
                                width=width,
                                height=height,
                                supports_streaming=True,
                            )
                        )
                    )
    return blocks


def rich_media_messages(
    media_blocks: list[InputRichBlock], caption_blocks: list[InputRichBlock], *, slideshow: bool, limit: int
) -> list[InputRichMessage]:
    """媒体块+caption 块 → 富文本消息序列: 文档块独立, 其余按 limit 进幻灯片/拼图, 文档与 caption 附在最后一条"""
    standalone = [b for b in media_blocks if isinstance(b, InputRichBlockDocument)]
    gallery_blocks = [b for b in media_blocks if not isinstance(b, InputRichBlockDocument)]
    container: type = InputRichBlockSlideshow if slideshow else InputRichBlockCollage

    messages: list[InputRichMessage] = []
    chunks = list(batched(gallery_blocks, limit)) or [()]
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        fold = not slideshow and len(chunk) > COLLAGE_FOLD_THRESHOLD
        blocks: list[InputRichBlock] = []
        # 折叠时 caption 放在详情块之前, 避免被客户端自动折叠隐藏
        if is_last and fold:
            blocks.extend(standalone)
            blocks.extend(caption_blocks)
        if len(chunk) > 1:
            if fold:
                blocks.append(
                    InputRichBlockDetails(
                        f"展开媒体 ({len(chunk)})",  # type: ignore[arg-type]
                        blocks=[InputRichBlockCollage(list(chunk))],
                        is_open=False,
                    )
                )
            else:
                blocks.append(container(list(chunk)))
        else:
            blocks.extend(chunk)
        if is_last and not fold:
            blocks.extend(standalone)
            blocks.extend(caption_blocks)
        messages.append(InputRichMessage(blocks=blocks))
    return messages


def cached_rich_media_blocks(media: list[CacheMedia]) -> list[InputRichBlock]:
    blocks: list[InputRichBlock] = []
    for m in media:
        match m.type:
            case CacheMediaType.PHOTO:
                blocks.append(InputRichBlockPhoto(InputMediaPhoto(m.file_id)))
            case CacheMediaType.VIDEO:
                blocks.append(InputRichBlockVideo(InputMediaVideo(m.file_id, supports_streaming=True)))
            case CacheMediaType.ANIMATION:
                blocks.append(InputRichBlockAnimation(InputMediaAnimation(m.file_id)))
            case CacheMediaType.DOCUMENT:
                blocks.append(InputRichBlockDocument(InputMediaDocument(m.file_id)))
    return blocks
