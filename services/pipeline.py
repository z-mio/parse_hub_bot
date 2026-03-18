import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from parsehub import DownloadResult
from parsehub.types import AnyParseResult, PostType, ProgressUnit

from core import bs, pl_cfg
from log import logger
from plugins.helpers import ProcessedMedia, process_media_files
from services import ParseService
from utils.helpers import to_list

logger = logger.bind(name="Pipeline")

# Singleflight: 同一 URL 只会有一条流水线在执行，后续请求等待 Event 后走缓存
_inflight: dict[str, asyncio.Event] = {}


class StatusReporter(Protocol):
    """抽象状态通知，由调用方实现"""

    async def report(self, text: str) -> None: ...

    async def report_error(self, stage: str, error: Exception) -> None: ...

    async def dismiss(self) -> None: ...


@dataclass
class PipelineResult:
    parse_result: AnyParseResult
    processed_list: list[ProcessedMedia] = field(default_factory=list)
    output_dir: Path | None = None

    def cleanup(self) -> None:
        if bs.debug_skip_cleanup:
            logger.debug("debug_skip_cleanup=True 跳过清理")
            return
        if self.output_dir:
            logger.debug("清理资源")
            shutil.rmtree(self.output_dir, ignore_errors=True)


class PipelineProgressCallback:
    """统一的下载进度回调，依赖 StatusReporter"""

    def __init__(self, reporter: StatusReporter):
        self._reporter = reporter
        self._last_text: str | None = None

    async def __call__(self, current: int, total: int, unit: ProgressUnit, *args, **kwargs) -> None:
        from plugins.helpers import progress as fmt_progress

        text = fmt_progress(current, total, unit)
        if not text or text == self._last_text:
            return
        self._last_text = text
        await self._reporter.report(text)


class ParsePipeline:
    """
    将 解析 → 下载 → 格式转换 封装为一条流水线。
    上传逻辑仍由调用方负责。

    内置 Singleflight 机制：对同一 URL 的并发调用只会执行一次流水线，
    其余调用等待 Event 完成后返回 None（调用方应重新检查缓存）。
    首个调用方在完成上传+缓存后必须调用 finish() 以释放等待者。
    """

    def __init__(
        self,
        url: str,
        reporter: StatusReporter,
        parse_result: AnyParseResult | None = None,
        *,
        singleflight: bool = True,
        skip_media_processing: bool = False,
        skip_download_threshold: int = 0,
        richtext_skip_download: bool = True,
        save_metadata: bool = False,
    ):
        self._url = url
        self._reporter = reporter
        self._parse_result = parse_result
        self._waited = False
        self._singleflight = singleflight
        self._skip_media_processing = skip_media_processing
        self._skip_download_threshold = skip_download_threshold
        self._richtext_skip_download = richtext_skip_download
        self._save_metadata = save_metadata

    @property
    def waited(self) -> bool:
        """是否因 singleflight 而等待了其他流水线"""
        return self._waited

    def finish(self) -> None:
        """首个调用方完成上传+缓存后调用，释放所有等待者"""
        event = _inflight.pop(self._url, None)
        if event is not None:
            event.set()

    async def run(self) -> PipelineResult | None:
        """执行流水线，返回 PipelineResult 或 None（失败时已通知）"""
        if self._singleflight:
            key = self._url
            existing = _inflight.get(key)

            if existing is not None:
                self._waited = True
                logger.debug(f"Singleflight 命中, 等待已有流水线: url={key}")
                await self._reporter.report("已有相同任务正在解析, 等待解析完成...")
                await existing.wait()
                await self._reporter.dismiss()
                return None

            event = asyncio.Event()
            _inflight[key] = event

        try:
            result = await self._execute()
            if result is None:
                self.finish()  # 流水线失败，立即释放等待者
            return result
        except BaseException:
            self.finish()  # 流水线异常，立即释放等待者
            raise

    async def _execute(self) -> PipelineResult | None:
        """实际执行流水线逻辑"""
        logger.debug(f"流水线启动: url={self._url}, has_cached_result={self._parse_result is not None}")
        ps = ParseService()
        # ── 1. 解析 ──
        if self._parse_result is not None:
            logger.debug("使用缓存的解析结果")
            parse_result = self._parse_result
        else:
            await self._reporter.report("解 析 中...")
            parse_result = await self._step("解析", lambda: ps.parse(self._url))
            if parse_result is None:
                return None

        if self._richtext_skip_download and parse_result.type == PostType.RICHTEXT:
            logger.debug("富文本跳过下载")
            return PipelineResult(parse_result=parse_result)

        if self._skip_download_threshold and len(to_list(parse_result.media)) > self._skip_download_threshold:
            logger.debug(
                f"媒体数量({len(to_list(parse_result.media))})大于设定值({self._skip_download_threshold}), 跳过下载"
            )
            return PipelineResult(parse_result=parse_result)

        # ── 2. 下载 ──
        await self._reporter.report("下 载 中...")
        p = ps.parser.get_platform(self._url)
        if pl_cfg.get(p.id):
            proxy = pl_cfg.roll_downloader_proxy(p.id)
            logger.debug(f"使用配置: proxy={proxy}")
            progress_cb = PipelineProgressCallback(self._reporter)
        download_result: DownloadResult = await self._step(
            "下载",
            lambda: parse_result.download(
                callback=progress_cb, callback_args=(), proxy=proxy, save_metadata=self._save_metadata
            ),
        )
        if download_result is None:
            return None
        logger.debug(f"下载完成: output_dir={download_result.output_dir}")

        # ── 3. 格式转换 ──
        if self._skip_media_processing:
            logger.debug(f"流水线完成: download_result={download_result}")
            processed_list = [ProcessedMedia(i, [i.path]) for i in to_list(download_result.media)]
            return PipelineResult(
                parse_result=parse_result, processed_list=processed_list, output_dir=download_result.output_dir
            )

        await self._reporter.report("处 理 中...")
        processed_list = await self._step(
            "格式转换",
            lambda: process_media_files(download_result),
            cleanup=lambda: shutil.rmtree(download_result.output_dir, ignore_errors=True),
        )
        if processed_list is None:
            return None

        logger.debug(f"流水线完成: processed_count={len(processed_list)}")
        return PipelineResult(
            parse_result=parse_result,
            processed_list=processed_list,
            output_dir=download_result.output_dir,
        )

    async def _step(self, stage: str, action, cleanup=None):
        """执行单个步骤，失败时统一处理"""
        logger.debug(f"执行步骤: {stage}")
        try:
            return await action()
        except Exception as e:
            logger.exception(e)
            logger.error(f"{stage}失败, 以上为错误信息")
            await self._reporter.report_error(stage, e)
            if cleanup:
                cleanup()
            return None
