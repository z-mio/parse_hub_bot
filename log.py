import inspect
import logging
from typing import TYPE_CHECKING

import loguru

if TYPE_CHECKING:
    # 避免 sphinx autodoc 解析注释失败
    # 因为 loguru 模块实际上没有 `Logger` 类
    from loguru import Logger

logger: "Logger" = loguru.logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        level: str | int
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def init_logger():
    logging.basicConfig(handlers=[InterceptHandler()], force=True)


init_logger()
