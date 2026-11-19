"""TiffGetter 公开库门面。

本包是无界面、无用户 CLI 的 Python 库。导入本包不会启动 GUI 或解析命令行参数。
"""
from .client import (
    SCHEMA_VERSION,
    CancelToken,
    Client,
    Event,
    EventSink,
    FetchItem,
    FetchOptions,
    FetchRequest,
    FetchResult,
    OutputOptions,
    Point,
)

__version__ = '0.1.0'

__all__ = [
    'SCHEMA_VERSION',
    'CancelToken',
    'Client',
    'Event',
    'EventSink',
    'FetchItem',
    'FetchOptions',
    'FetchRequest',
    'FetchResult',
    'OutputOptions',
    'Point',
    '__version__',
]
