"""库内日志命名空间。

所有内部模块使用 ``tiffgetter.*`` logger；包级 logger 默认挂载 NullHandler，
保证库被导入时不会向 stdout/stderr 输出任何用户日志。
"""
import logging

PACKAGE_LOGGER_NAME = 'tiffgetter'

_package_logger = logging.getLogger(PACKAGE_LOGGER_NAME)
if not _package_logger.handlers:
    _package_logger.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """返回 ``tiffgetter.<name>`` 命名空间下的 logger。

    Args:
        name: 模块名或子命名空间。
    Returns:
        对应层级的 Logger。
    """
    return logging.getLogger(f'{PACKAGE_LOGGER_NAME}.{name}')
