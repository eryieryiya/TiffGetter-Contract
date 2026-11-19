"""结构化运行事件的类型常量与构造辅助（不直接输出）。

事件由调用方注入的 EventSink / 回调消费；本模块不写 stdout。
"""
from typing import Any, Dict

SCHEMA_VERSION = '1.0'

EVENT_TYPES = (
    'log',
    'progress',
    'date_result',
    'coordinate_result',
    'run_summary',
)


def make_event(event_type: str, **payload: Any) -> Dict[str, Any]:
    """构造一个原始事件字典，附带 type 字段。

    Args:
        event_type: 事件类型，需属于 EVENT_TYPES。
        payload   : 事件负载字段。
    Returns:
        含 type 与负载字段的字典。
    """
    event: Dict[str, Any] = {'type': event_type}
    event.update(payload)
    return event
