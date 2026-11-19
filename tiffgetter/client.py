"""TiffGetter v1 契约对象与无界面客户端。"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

SCHEMA_VERSION = '1.0'

SOURCE_NAMES = ('wayback', 'esri', 'bing', 'osm', 'google')

FAILURE_KINDS = (
    'no_releases',
    'out_of_range',
    'network',
    'timeout',
    'tls',
    'http_error',
    'forbidden',
    'rate_limited',
    'server',
    'blocked',
    'invalid_content',
    'incomplete_tiles',
    'interface_changed',
    'internal',
    'cancelled',
)

EVENT_TYPES = (
    'log',
    'progress',
    'date_result',
    'coordinate_result',
    'run_summary',
)

_DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _enum_value(value: Any) -> Any:
    """把 Enum 或普通值统一转换为可 JSON 序列化的值。"""
    return getattr(value, 'value', value)


@dataclass
class Point:
    """单个坐标点。"""
    id: str
    name: str
    lat: float
    lon: float

    def to_dict(self) -> Dict[str, Any]:
        """转换为契约字典。"""
        return {
            'id': self.id,
            'name': self.name,
            'lat': self.lat,
            'lon': self.lon,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Point':
        """从契约字典构造坐标点。"""
        return cls(
            id=str(data.get('id', '')),
            name=str(data.get('name', '')),
            lat=float(data['lat']),
            lon=float(data['lon']),
        )


@dataclass
class FetchOptions:
    """抓取参数。"""
    zoom: int = 18
    buffer_radius_m: int = 500
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    dedup: bool = True
    coord_concurrency: int = 1

    def to_dict(self) -> Dict[str, Any]:
        """转换为契约字典。"""
        return {
            'zoom': self.zoom,
            'buffer_radius_m': self.buffer_radius_m,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'dedup': self.dedup,
            'coord_concurrency': self.coord_concurrency,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FetchOptions':
        """从契约字典构造参数。"""
        return cls(
            zoom=int(data.get('zoom', 18)),
            buffer_radius_m=int(data.get('buffer_radius_m', 500)),
            date_start=data.get('date_start'),
            date_end=data.get('date_end'),
            dedup=bool(data.get('dedup', True)),
            coord_concurrency=int(data.get('coord_concurrency', 1)),
        )


@dataclass
class OutputOptions:
    """输出位置参数。"""
    root: Optional[str] = None
    layout: str = 'auto'

    def to_dict(self) -> Dict[str, Any]:
        """转换为契约字典。"""
        return {'root': self.root, 'layout': self.layout}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OutputOptions':
        """从契约字典构造输出参数。"""
        return cls(
            root=data.get('root'),
            layout=str(data.get('layout', 'auto')),
        )


@dataclass
class FetchRequest:
    """v1 抓取请求。"""
    source: str
    points: List[Point]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = SCHEMA_VERSION
    options: FetchOptions = field(default_factory=FetchOptions)
    output: OutputOptions = field(default_factory=OutputOptions)

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的契约字典。"""
        return {
            'schema_version': self.schema_version,
            'request_id': self.request_id,
            'source': self.source,
            'points': [point.to_dict() for point in self.points],
            'options': self.options.to_dict(),
            'output': self.output.to_dict(),
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FetchRequest':
        """从契约字典构造请求。"""
        return cls(
            source=str(data['source']),
            points=[Point.from_dict(item) for item in data.get('points', [])],
            request_id=str(data.get('request_id') or uuid.uuid4()),
            schema_version=str(data.get('schema_version', SCHEMA_VERSION)),
            options=FetchOptions.from_dict(data.get('options', {})),
            output=OutputOptions.from_dict(data.get('output', {})),
        )


@dataclass
class FetchItem:
    """单个 release 的处理结果。"""
    point_id: str
    point_name: str
    date: str
    release_id: Optional[str]
    status: str
    failure_kind: Optional[str]
    detail: Optional[str]
    effective_zoom: int
    assets: Dict[str, Optional[str]]
    bounds: Optional[Dict[str, float]]
    diagnostics: Dict[str, Any]
    metadata_source: Optional[str]
    metadata_fetched_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """转换为契约字典。"""
        return {
            'point_id': self.point_id,
            'point_name': self.point_name,
            'date': self.date,
            'release_id': self.release_id,
            'status': self.status,
            'failure_kind': self.failure_kind,
            'detail': self.detail,
            'effective_zoom': self.effective_zoom,
            'assets': dict(self.assets),
            'bounds': dict(self.bounds) if self.bounds is not None else None,
            'diagnostics': self.diagnostics,
            'metadata_source': self.metadata_source,
            'metadata_fetched_at': self.metadata_fetched_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FetchItem':
        """从契约字典构造结果项。"""
        return cls(
            point_id=str(data.get('point_id', '')),
            point_name=str(data.get('point_name', '')),
            date=str(data.get('date', '')),
            release_id=data.get('release_id'),
            status=str(data.get('status', 'failed')),
            failure_kind=data.get('failure_kind'),
            detail=data.get('detail'),
            effective_zoom=int(data.get('effective_zoom', 0)),
            assets=dict(data.get('assets') or {}),
            bounds=data.get('bounds'),
            diagnostics=dict(data.get('diagnostics') or {}),
            metadata_source=data.get('metadata_source'),
            metadata_fetched_at=data.get('metadata_fetched_at'),
        )


@dataclass
class FetchResult:
    """v1 抓取结果。"""
    request_id: str
    status: str
    exit_code: int
    started_at: str
    finished_at: str
    items: List[FetchItem] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的契约字典。"""
        return {
            'schema_version': self.schema_version,
            'request_id': self.request_id,
            'status': self.status,
            'exit_code': self.exit_code,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'items': [item.to_dict() for item in self.items],
            'diagnostics': self.diagnostics,
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FetchResult':
        """从契约字典构造结果。"""
        return cls(
            request_id=str(data.get('request_id', '')),
            status=str(data.get('status', 'failed')),
            exit_code=int(data.get('exit_code', 4)),
            started_at=str(data.get('started_at', '')),
            finished_at=str(data.get('finished_at', '')),
            items=[FetchItem.from_dict(item) for item in data.get('items', [])],
            diagnostics=dict(data.get('diagnostics') or {}),
            schema_version=str(data.get('schema_version', SCHEMA_VERSION)),
        )


@dataclass
class Event:
    """v1 运行事件。"""
    type: str
    schema_version: str = SCHEMA_VERSION
    job_id: str = ''
    sequence: int = 0
    timestamp: str = ''
    item: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的契约字典。"""
        return {
            'type': self.type,
            'schema_version': self.schema_version,
            'job_id': self.job_id,
            'sequence': self.sequence,
            'timestamp': self.timestamp,
            'item': self.item,
        }

    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """从契约字典构造事件。"""
        return cls(
            type=str(data.get('type', 'log')),
            schema_version=str(data.get('schema_version', SCHEMA_VERSION)),
            job_id=str(data.get('job_id', '')),
            sequence=int(data.get('sequence', 0)),
            timestamp=str(data.get('timestamp', '')),
            item=dict(data.get('item') or {}),
        )


class EventSink:
    """事件接收器基类；子类实现 emit。"""

    def emit(self, event: Event) -> None:
        """消费一个事件。"""
        raise NotImplementedError


class CancelToken:
    """协作式取消令牌。"""

    def __init__(self) -> None:
        """创建未取消状态的令牌。"""
        self._event = threading.Event()

    def cancel(self) -> None:
        """标记为已取消。"""
        self._event.set()

    def is_cancelled(self) -> bool:
        """返回是否已取消。"""
        return self._event.is_set()


class _EventEmitter:
    """为单次抓取生成带 job_id/sequence/timestamp 的 Event。"""

    def __init__(self, job_id: str, sink: Optional[Callable[[Event], None]]):
        """保存 job_id 与事件接收函数。"""
        self._job_id = job_id
        self._sink = sink
        self._sequence = 0
        self._lock = threading.Lock()

    def emit(self, event_type: str, item: Dict[str, Any]) -> None:
        """构造并发送一个 Event。"""
        if self._sink is None:
            return
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        event = Event(
            type=event_type,
            job_id=self._job_id,
            sequence=sequence,
            timestamp=_now_iso(),
            item=item,
        )
        self._sink(event)


class _LogEventBridge(logging.Handler):
    """把 tiffgetter 日志转换为 log 事件。"""

    def __init__(self, emit: Callable[[str, Dict[str, Any]], None]):
        """保存事件发送函数。"""
        super().__init__(level=logging.INFO)
        self._emit = emit

    def emit(self, record: logging.LogRecord) -> None:
        """把日志记录转换为 log 事件。"""
        self._emit('log', {
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        })


def _create_fetcher(source: str, dedup: bool, event_sink, cancel) -> Any:
    """构造 ImageFetcher；独立函数便于测试替换。

    Args:
        source    : 数据源名称。
        dedup     : 是否启用重复检测。
        event_sink: 原始事件接收函数。
        cancel    : 协作式取消令牌。
    Returns:
        ImageFetcher 实例。
    """
    from core.fetch import ImageFetcher

    return ImageFetcher(
        source=source,
        dedup=dedup,
        event_sink=event_sink,
        cancel=cancel,
    )


class Client:
    """无界面 TiffGetter 客户端。"""

    def list_sources(self) -> List[Any]:
        """返回全部已注册数据源的 SourceInfo 列表。"""
        from providers.registry import list_sources

        return list_sources()

    def parse_coordinates(self, path: str) -> List[Point]:
        """解析 CSV/SHP 坐标文件，返回坐标点列表。

        Args:
            path: CSV 或 SHP 文件路径。
        Returns:
            Point 列表。
        """
        from coordinate_loader import load_coordinates_file

        coords = load_coordinates_file(path)
        return [
            Point(
                id=str(coord.get('id') or ''),
                name=str(coord.get('name') or ''),
                lat=float(coord['lat']),
                lon=float(coord['lon']),
            )
            for coord in coords
        ]

    def scan_residuals(self, root: str) -> List[Dict[str, Any]]:
        """扫描临时瓦片与历史 release 目录。

        Args:
            root: 扫描根目录。
        Returns:
            可清理项列表。
        """
        from utils.cleanup import scan_residuals

        return scan_residuals(root)

    def cleanup(self, paths: List[str], temp_only: bool = False) -> Dict[str, Any]:
        """删除给定的残留路径。

        Args:
            paths    : 待删除路径列表。
            temp_only: 为 True 时仅删除 temp_tiles_* 临时目录，其余跳过。
        Returns:
            含 requested/deleted/skipped/failed 的结果字典。
        """
        from utils.cleanup import delete_paths

        requested = [str(path) for path in paths]
        if temp_only:
            selected = [
                path for path in requested
                if os.path.basename(os.path.normpath(path)).startswith('temp_tiles_')
            ]
            skipped = [path for path in requested if path not in selected]
        else:
            selected = list(requested)
            skipped = []
        results = delete_paths(selected)
        return {
            'schema_version': SCHEMA_VERSION,
            'temp_only': bool(temp_only),
            'requested': requested,
            'deleted': [item['path'] for item in results if item['ok']],
            'skipped': skipped,
            'failed': [
                {'path': item['path'], 'error': item['error']}
                for item in results if not item['ok']
            ],
        }

    def fetch(self, request: FetchRequest,
              on_event: Optional[Any] = None,
              cancel: Optional[CancelToken] = None) -> FetchResult:
        """执行抓取。

        Args:
            request : FetchRequest 或等价字典。
            on_event: 事件回调（可调用对象）或 EventSink 实例。
            cancel  : 协作式取消令牌。
        Returns:
            FetchResult。
        """
        if not isinstance(request, FetchRequest):
            request = FetchRequest.from_dict(dict(request))
        sink = self._coerce_sink(on_event)
        emitter = _EventEmitter(request.request_id, sink)

        started_at = _now_iso()
        error = self._validate(request)
        if error is not None:
            emitter.emit('log', {'level': 'ERROR', 'message': error})
            emitter.emit('run_summary', {
                'mode': 'single' if len(request.points) == 1 else 'batch',
                'success': 0,
                'failed': 0,
                'status': 'failed',
                'exit_code': 2,
                'error': error,
            })
            return FetchResult(
                request_id=request.request_id,
                status='failed',
                exit_code=2,
                started_at=started_at,
                finished_at=_now_iso(),
                items=[],
                diagnostics=self._empty_diagnostics(error),
            )

        from providers.registry import get_source

        info = get_source(request.source).info
        effective_zoom = request.options.zoom
        if effective_zoom < info.min_zoom:
            effective_zoom = info.min_zoom
        if effective_zoom > info.max_zoom:
            effective_zoom = info.max_zoom
        if effective_zoom != request.options.zoom:
            emitter.emit('log', {
                'level': 'WARNING',
                'message': (
                    f"zoom {request.options.zoom} 超出数据源 "
                    f"{request.source} 范围，已截断为 {effective_zoom}"
                ),
                'logger': 'tiffgetter.client',
            })

        date_range = None
        if request.options.date_start and request.options.date_end:
            date_range = (request.options.date_start, request.options.date_end)

        output_root = request.output.root or self._default_output_root(request.source)

        package_logger = logging.getLogger('tiffgetter')
        bridge = _LogEventBridge(emitter.emit)
        package_logger.addHandler(bridge)

        def raw_sink(raw: Dict[str, Any]) -> None:
            """把核心原始事件补充坐标信息后转发为 Event。"""
            self._handle_raw_event(request, emitter, raw)

        try:
            fetcher = _create_fetcher(
                request.source,
                request.options.dedup,
                raw_sink,
                cancel,
            )
            if len(request.points) == 1:
                point = request.points[0]
                results = fetcher.fetch_all(
                    lat=point.lat,
                    lon=point.lon,
                    zoom=effective_zoom,
                    output_dir=output_root,
                    buffer_size=request.options.buffer_radius_m,
                    date_range=date_range,
                    dedup=request.options.dedup,
                    emit_events=True,
                    event_coord=1,
                    cancel=cancel,
                )
                summaries = [{
                    'index': 1,
                    'name': point.name or point.id,
                    'lat': point.lat,
                    'lon': point.lon,
                    'output_dir': output_root,
                    'total_dates': len(results),
                    'success': sum(1 for r in results if r['status'] == 'success'),
                    'failed': sum(1 for r in results if r['status'] == 'failed'),
                    'cancelled': False,
                    'results': results,
                }]
            else:
                coords = [
                    {
                        'id': point.id,
                        'name': point.name,
                        'lat': point.lat,
                        'lon': point.lon,
                    }
                    for point in request.points
                ]
                summaries = fetcher.fetch_batch(
                    coords=coords,
                    output_root=output_root,
                    zoom=effective_zoom,
                    buffer_size=request.options.buffer_radius_m,
                    date_range=date_range,
                    coord_concurrency=request.options.coord_concurrency,
                    dedup=request.options.dedup,
                    emit_events=True,
                    cancel=cancel,
                )
        finally:
            package_logger.removeHandler(bridge)

        items: List[FetchItem] = []
        for summary in summaries:
            point = request.points[summary['index'] - 1]
            for raw in summary.get('results', []):
                items.append(self._to_item(point, raw, effective_zoom))

        cancelled = cancel is not None and cancel.is_cancelled()
        diagnostics = self._aggregate_diagnostics(items)
        status, exit_code = self._compute_status(items, cancelled)
        return FetchResult(
            request_id=request.request_id,
            status=status,
            exit_code=exit_code,
            started_at=started_at,
            finished_at=_now_iso(),
            items=items,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _handle_raw_event(self, request: FetchRequest, emitter: _EventEmitter,
                          raw: Dict[str, Any]) -> None:
        """把核心原始事件补充坐标信息与运行状态后转发。

        Args:
            request: 当前请求，用于按 coord_index 映射坐标点。
            emitter: 事件发送器。
            raw    : 核心产生的原始事件字典。
        """
        event = dict(raw)
        event_type = event.pop('type')
        coord_index = event.get('coord_index')
        if event_type in ('date_result', 'progress'):
            point = None
            if isinstance(coord_index, int) and 1 <= coord_index <= len(request.points):
                point = request.points[coord_index - 1]
            elif len(request.points) == 1:
                point = request.points[0]
            if point is not None:
                event['point_id'] = point.id
                event['point_name'] = point.name
        if event_type == 'run_summary':
            status, exit_code = self._summary_status(
                int(event.get('success', 0)),
                int(event.get('failed', 0)),
                event.get('total') if event.get('total') is not None
                else event.get('total_dates'),
                event.get('failure_counts') or {},
                bool(event.get('cancelled')),
            )
            event['status'] = status
            event['exit_code'] = exit_code
        emitter.emit(event_type, event)

    @staticmethod
    def _summary_status(success: int, failed: int, total: Optional[int],
                        failure_counts: Dict[str, Any],
                        cancelled: bool) -> tuple:
        """根据运行汇总计算状态与退出码。"""
        if cancelled:
            return 'cancelled', 6
        if failed == 0:
            return 'success', 0
        if total is not None and total > failed:
            return 'partial', 3
        if set(failure_counts.keys()) == {'interface_changed'}:
            return 'failed', 5
        return 'failed', 4

    def _coerce_sink(self, on_event: Optional[Any]) -> Optional[Callable[[Event], None]]:
        """把 on_event 统一转换为 Event 回调。"""
        if on_event is None:
            return None
        if isinstance(on_event, EventSink):
            return on_event.emit
        if callable(on_event):
            return on_event
        raise TypeError('on_event 必须是可调用对象或 EventSink')

    def _validate(self, request: FetchRequest) -> Optional[str]:
        """校验请求；合法返回 None，否则返回错误说明。"""
        if request.schema_version != SCHEMA_VERSION:
            return f"schema_version 必须为 {SCHEMA_VERSION}"
        if request.source not in SOURCE_NAMES:
            return f"未知数据源: {request.source!r}"
        if not request.points:
            return 'points 至少需要 1 个坐标点'
        for point in request.points:
            if not (-90.0 <= point.lat <= 90.0):
                return f"lat 越界: {point.lat}"
            if not (-180.0 <= point.lon <= 180.0):
                return f"lon 越界: {point.lon}"
        options = request.options
        if not (0 <= options.zoom <= 20):
            return f"zoom 越界: {options.zoom}"
        if not (50 <= options.buffer_radius_m <= 5000):
            return f"buffer_radius_m 越界: {options.buffer_radius_m}"
        if not (1 <= options.coord_concurrency <= 16):
            return f"coord_concurrency 越界: {options.coord_concurrency}"
        has_start = options.date_start is not None
        has_end = options.date_end is not None
        if has_start != has_end:
            return 'date_start 与 date_end 必须同时为空或同时提供'
        if has_start:
            if not _DATE_PATTERN.match(options.date_start or ''):
                return f"date_start 格式错误: {options.date_start!r}"
            if not _DATE_PATTERN.match(options.date_end or ''):
                return f"date_end 格式错误: {options.date_end!r}"
            if options.date_start > options.date_end:
                return 'date_start 不能晚于 date_end'
            from providers.registry import get_source

            if not get_source(request.source).info.supports_history:
                return f'数据源 {request.source} 不支持历史日期'
        if request.output.layout not in ('auto', 'explicit'):
            return f"output.layout 非法: {request.output.layout!r}"
        if request.output.layout == 'explicit' and not request.output.root:
            return 'output.layout=explicit 时 root 必填'
        return None

    @staticmethod
    def _default_output_root(source: str) -> str:
        """返回数据源的默认输出根目录。"""
        if source == 'wayback':
            return os.path.join('data', 'output', 'historical')
        return os.path.join('data', 'output', source)

    @staticmethod
    def _empty_diagnostics(detail: str) -> Dict[str, Any]:
        """构造参数错误时的诊断信息。"""
        return {
            'by_kind': {},
            'failed_tiles': 0,
            'samples': [{
                'kind': 'internal',
                'http_status': None,
                'url': '',
                'detail': detail,
            }],
        }

    def _to_item(self, point: Point, raw: Dict[str, Any],
                 effective_zoom: int) -> FetchItem:
        """把核心结果字典转换为 FetchItem。"""
        failures = raw.get('failures') or []
        kind = _enum_value(raw.get('failure_kind'))
        bounds = raw.get('bounds')
        return FetchItem(
            point_id=point.id,
            point_name=point.name,
            date=str(raw.get('date', '')),
            release_id=raw.get('release_id'),
            status=str(raw.get('status', 'failed')),
            failure_kind=kind if kind else None,
            detail=raw.get('detail') or None,
            effective_zoom=effective_zoom,
            assets={
                'png': raw.get('png_path'),
                'tif': raw.get('tif_path'),
                'metadata': raw.get('metadata_path'),
            },
            bounds=dict(bounds) if bounds is not None else None,
            diagnostics=self._build_diagnostics(failures),
            metadata_source=raw.get('metadata_source') or 'native',
            metadata_fetched_at=raw.get('metadata_fetched_at') or None,
        )

    @staticmethod
    def _build_diagnostics(failures: List[Any]) -> Dict[str, Any]:
        """把瓦片失败列表汇总为诊断信息。"""
        by_kind: Dict[str, int] = {}
        for failure in failures:
            key = _enum_value(failure.kind) or 'internal'
            by_kind[str(key)] = by_kind.get(str(key), 0) + 1
        samples = [
            {
                'kind': str(_enum_value(failure.kind) or 'internal'),
                'http_status': failure.http_status,
                'url': failure.url,
                'detail': failure.detail,
            }
            for failure in failures[:3]
        ]
        return {
            'by_kind': by_kind,
            'failed_tiles': len(failures),
            'samples': samples,
        }

    @staticmethod
    def _aggregate_diagnostics(items: List[FetchItem]) -> Dict[str, Any]:
        """汇总全部结果项的诊断信息。"""
        by_kind: Dict[str, int] = {}
        failed_tiles = 0
        samples: List[Dict[str, Any]] = []
        for item in items:
            for key, value in (item.diagnostics.get('by_kind') or {}).items():
                by_kind[key] = by_kind.get(key, 0) + int(value)
            failed_tiles += int(item.diagnostics.get('failed_tiles', 0))
            for sample in item.diagnostics.get('samples') or []:
                if len(samples) < 3:
                    samples.append(sample)
        return {
            'by_kind': by_kind,
            'failed_tiles': failed_tiles,
            'samples': samples,
        }

    @staticmethod
    def _compute_status(items: List[FetchItem], cancelled: bool) -> tuple:
        """按结果项计算运行状态与退出码。"""
        if cancelled:
            return 'cancelled', 6
        if not items:
            return 'failed', 4
        failed = [item for item in items if item.status == 'failed']
        if not failed:
            return 'success', 0
        if len(failed) == len(items):
            kinds = {item.failure_kind for item in failed}
            if kinds == {'interface_changed'}:
                return 'failed', 5
            return 'failed', 4
        return 'partial', 3
