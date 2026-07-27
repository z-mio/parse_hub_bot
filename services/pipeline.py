import asyncio
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from easy_ai18n import PreLocaleSelector
from parsehub import DownloadResult
from parsehub.types import AniRef, AnyParseResult, PostType, ProgressUnit

from core import bs, pl_cfg
from log import logger
from services import ParseService
from services.media import ProcessedMedia, process_media_files
from services.media import progress as fmt_progress
from utils.helpers import to_list

logger = logger.bind(name="Pipeline")

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
            self.output_dir = None


class PipelineProgressCallback:
    """统一的下载进度回调，依赖 StatusReporter"""

    def __init__(self, reporter: StatusReporter, _t: PreLocaleSelector):
        self._reporter = reporter
        self._last_text: str | None = None
        self._t = _t

    async def __call__(self, current: int, total: int, unit: ProgressUnit, *args: Any, **kwargs: Any) -> None:
        text = fmt_progress(current, total, unit, self._t)
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
    使用 with 创建实例，退出上下文时会自动 finish() 并清理流水线输出。
    """

    def __init__(
        self,
        url: str,
        raw_url: str,
        reporter: StatusReporter,
        parse_result: AnyParseResult | None = None,
        *,
        singleflight: bool = True,
        skip_media_processing: bool = False,
        skip_download_threshold: int = 0,
        gif_only_skip_download_count_threshold: int = 0,
        richtext_skip_download: bool = True,
        save_metadata: bool = False,
        t: PreLocaleSelector,
    ):
        """
        :param url: 未清理的 URL
        :param raw_url: 原始 URL，当做 KEY
        """
        self._url = url
        self._raw_url = raw_url
        self._reporter = reporter
        self._parse_result = parse_result
        self._waited = False
        self._singleflight = singleflight
        self._skip_media_processing = skip_media_processing
        self._skip_download_threshold = skip_download_threshold
        self._gif_only_skip_download_count_threshold = gif_only_skip_download_count_threshold
        self._richtext_skip_download = richtext_skip_download
        self._save_metadata = save_metadata
        self._t = t
        self._result: PipelineResult | None = None
        self._owns_inflight = False

    def __enter__(self) -> "ParsePipeline":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.finish()
        self.cleanup()

    @property
    def waited(self) -> bool:
        """是否因 singleflight 而等待了其他流水线"""
        return self._waited

    def finish(self) -> None:
        """释放等待同一 URL 的 singleflight 调用方"""
        if not self._owns_inflight:
            return
        event = _inflight.pop(self._raw_url, None)
        if event is not None:
            event.set()
        self._owns_inflight = False

    def cleanup(self) -> None:
        """清理流水线输出资源"""
        if self._result is not None:
            self._result.cleanup()

    async def run(self) -> PipelineResult | None:
        """执行流水线，返回 PipelineResult 或 None（失败时已通知）"""
        if self._singleflight:
            key = self._raw_url
            existing = _inflight.get(key)

            if existing is not None:
                self._waited = True
                logger.debug(f"Singleflight 命中, 等待已有流水线: url={key}")
                await self._reporter.report(self._t("已有相同任务正在解析, 等待解析完成..."))
                await existing.wait()
                await self._reporter.dismiss()
                return None

            event = asyncio.Event()
            _inflight[key] = event
            self._owns_inflight = True

        try:
            result = await self._execute()
            self._result = result
            if result is None:
                logger.debug("流水线失败, 立即释放等待者")
                self.finish()
            return result
        except BaseException:
            logger.debug("流水线异常, 立即释放等待者")
            self.finish()
            raise

    async def _execute(self) -> PipelineResult | None:
        """实际执行流水线逻辑"""
        logger.debug(f"流水线启动: url={self._url}, has_cached_result={self._parse_result is not None}")
        ps = ParseService()
        # ── 1. 解析 ──
        if self._parse_result:
            logger.debug("使用缓存的解析结果")
            parse_result = self._parse_result
        else:
            await self._reporter.report(self._t("解 析 中..."))
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

        gif_count = len([i for i in to_list(parse_result.media) if isinstance(i, AniRef)])
        if (
            self._gif_only_skip_download_count_threshold
            and gif_count > self._gif_only_skip_download_count_threshold
            and gif_count == len(to_list(parse_result.media))
        ):
            logger.debug(f"GIF ({gif_count})大于设定值({self._gif_only_skip_download_count_threshold}), 跳过下载")
            return PipelineResult(parse_result=parse_result)

        # ── 2. 下载 ──
        await self._reporter.report(self._t("下 载 中..."))
        p = ps.parser.get_platform(self._url)
        progress_cb = PipelineProgressCallback(self._reporter, _t=self._t)

        async def fn() -> DownloadResult:
            proxy = pl_cfg.roll_downloader_proxy(p.id)
            logger.debug(f"使用配置: proxy={proxy}")
            return await parse_result.download(
                bs.download_dir, callback=progress_cb, callback_args=(), proxy=proxy, save_metadata=self._save_metadata
            )

        download_result: DownloadResult = await self._step(
            "下载",
            lambda: fn(),
            timeout=60 * 30,  # 30分钟
            retries=2,
        )
        if download_result is None:
            return None
        logger.debug(f"下载完成: output_dir={download_result.output_dir}")

        # ── 3. 媒体处理 ──
        await self._reporter.report(self._t("处 理 中..."))
        if self._skip_media_processing:
            logger.debug(f"流水线完成: download_result={download_result}")
            processed_list = [ProcessedMedia(i, [Path(i.path)]) for i in to_list(download_result.media)]
            return PipelineResult(
                parse_result=parse_result, processed_list=processed_list, output_dir=download_result.output_dir
            )
        maybe_processed_list = await self._step(
            "媒体处理",
            lambda: process_media_files(download_result),
            cleanup=lambda: shutil.rmtree(download_result.output_dir, ignore_errors=True),
        )
        if maybe_processed_list is None:
            return None
        processed_list = maybe_processed_list

        logger.debug(f"流水线完成: processed_count={len(processed_list)}")
        return PipelineResult(
            parse_result=parse_result,
            processed_list=processed_list,
            output_dir=download_result.output_dir,
        )

    async def _step[T](
        self,
        stage: str,
        action: Callable[[], Awaitable[T]],
        cleanup: Callable[[], None] | None = None,
        timeout: float | None = None,
        retries: int = 0,
        retry_delay: float = 1,
    ) -> T | None:
        """执行单个步骤，失败时统一处理"""
        max_attempts = retries + 1
        for attempt in range(1, max_attempts + 1):
            logger.debug(f"执行步骤: [{stage}] attempt={attempt}/{max_attempts}")
            try:
                coro = action()
                if timeout is not None:
                    return await asyncio.wait_for(coro, timeout=timeout)
                return await coro
            except TimeoutError:
                error = TimeoutError(f"[{stage}] 超时 (>{timeout}s)")
                logger.error(str(error))
                if attempt < max_attempts:
                    logger.warning(f"[{stage}] 将在 {retry_delay}s 后重试 ({attempt}/{retries})")
                    await asyncio.sleep(retry_delay)
                    continue
                await self._reporter.report_error(stage, error)
                if cleanup:
                    cleanup()
                return None
            except Exception as e:
                logger.exception(e)
                logger.error(f"[{stage}] 失败, 以上为错误信息")
                if attempt < max_attempts:
                    logger.warning(f"[{stage}] 将在 {retry_delay}s 后重试 ({attempt}/{retries})")
                    await asyncio.sleep(retry_delay)
                    continue
                await self._reporter.report_error(stage, e)
                if cleanup:
                    cleanup()
                return None
        return None
