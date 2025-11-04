import importlib
import sys

from log import logger


def setup_optimized_event_loop():
    """配置优化的事件循环，自动选择winloop或uvloop"""
    is_windows = sys.platform == "win32"
    loop_module = "winloop" if is_windows else "uvloop"

    try:
        # 动态导入并安装事件循环
        module = importlib.import_module(loop_module)
        module.install()
        logger.debug(f"{loop_module} 已启用")
        return True
    except ImportError:
        logger.debug(f"{loop_module} 未安装")
        logger.debug("使用标准 asyncio 事件循环")
        return False
    except Exception as e:
        logger.debug(f"启用 {loop_module} 时出错: {e}")
        logger.debug("使用标准 asyncio 事件循环")
        return False
