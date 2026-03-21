import inspect
import logging
import sys
from typing import TYPE_CHECKING

import loguru

if TYPE_CHECKING:
    from loguru import Logger

logger: "Logger" = loguru.logger.bind(name="Main")


def formatter(record):
    rid = record["extra"].get("req_id")
    if rid:
        return (
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>[{extra[name]}][{extra[req_id]}] {message}</level>\n"
        )
    else:
        return (
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}:{function}:{line}</cyan> | "
            "<level>[{extra[name]}] {message}</level>\n"
        )


def setup_logging(debug: bool = False) -> None:
    logger.remove()

    level = "DEBUG" if debug else "INFO"
    logger.add(sys.stderr, level=level, format=formatter)

    logger.add(
        "logs/bot.log",
        rotation="10 MB",
        level="INFO",
        format=formatter,
        enqueue=True,
    )

    if debug:
        logger.debug("调试模式已启用")


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame:
            filename = frame.f_code.co_filename
            is_logging = filename == logging.__file__
            is_frozen = "importlib" in filename and "_bootstrap" in filename
            if depth > 0 and not (is_logging or is_frozen):
                break
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level="ERROR", force=True)
