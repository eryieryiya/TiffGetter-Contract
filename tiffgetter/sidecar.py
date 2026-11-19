"""TiffGetter 内部 sidecar 协议。

通过 stdin/stdout 逐行交换 JSON，供方案 B 的 Go 进程调用。
本模块是内部 API，不是用户 CLI。
"""
from __future__ import annotations

import json
import platform
import sys
import tempfile
from typing import Any, Dict, List, Optional, TextIO

from core.errors import ProviderError, classify_exception
from core.fetch import HAS_RASTERIO, png_to_geotiff
from tiffgetter import __version__
from tiffgetter.client import (
    SCHEMA_VERSION,
    Client,
    FetchOptions,
    FetchRequest,
    OutputOptions,
    Point,
)

METHODS = (
    'health',
    'parse_coordinates',
    'write_geotiff',
    'google.releases',
    'google.download_release',
)


def _health(params: Dict[str, Any]) -> Dict[str, Any]:
    """返回 sidecar 健康状态与能力清单。"""
    return {
        'status': 'ok',
        'schema_version': SCHEMA_VERSION,
        'version': __version__,
        'python': platform.python_version(),
        'rasterio': HAS_RASTERIO,
        'methods': list(METHODS),
    }


def _parse_coordinates(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """解析 CSV/SHP 坐标文件并返回点列表。"""
    client = Client()
    points = client.parse_coordinates(str(params['path']))
    return [point.to_dict() for point in points]


def _write_geotiff(params: Dict[str, Any]) -> bool:
    """把 PNG 写入 GeoTIFF。"""
    return png_to_geotiff(
        str(params['png_path']),
        str(params['tif_path']),
        dict(params['bounds']),
    )


def _google_releases(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回 Google Earth 指定坐标与 zoom 的 release 列表。"""
    from providers.registry import get_source

    source = get_source('google')
    return source.available_releases(
        float(params['lat']),
        float(params['lon']),
        int(params['zoom']),
    )


def _google_download_release(params: Dict[str, Any]) -> Dict[str, Any]:
    """下载 Google Earth 指定日期的 release，返回临时文件路径。"""
    lat = float(params['lat'])
    lon = float(params['lon'])
    zoom = int(params['zoom'])
    buffer_radius_m = int(params.get('buffer_radius_m', 500))
    date = str(params['date'])
    name = str(params.get('name') or date)
    output_dir = params.get('output_dir')
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix='tiffgetter_google_')
    request = FetchRequest(
        source='google',
        points=[Point(id=name, name=name, lat=lat, lon=lon)],
        options=FetchOptions(
            zoom=zoom,
            buffer_radius_m=buffer_radius_m,
            date_start=date,
            date_end=date,
            dedup=False,
            coord_concurrency=1,
        ),
        output=OutputOptions(root=str(output_dir), layout='explicit'),
    )
    result = Client().fetch(request)
    item = result.items[0] if result.items else None
    return {
        'status': result.status,
        'exit_code': result.exit_code,
        'output_dir': str(output_dir),
        'assets': item.assets if item is not None else None,
        'item': item.to_dict() if item is not None else None,
    }


_HANDLERS = {
    'health': _health,
    'parse_coordinates': _parse_coordinates,
    'write_geotiff': _write_geotiff,
    'google.releases': _google_releases,
    'google.download_release': _google_download_release,
}


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """处理一条 sidecar 请求并返回响应字典。

    Args:
        request: 含 id/method/params 的请求字典。
    Returns:
        含 id/ok/result 或 id/ok/error 的响应字典。
    """
    request_id = request.get('id')
    method = request.get('method')
    params = request.get('params') or {}
    handler = _HANDLERS.get(str(method))
    if handler is None:
        return {
            'id': request_id,
            'ok': False,
            'error': {
                'kind': 'internal',
                'detail': f'未知 sidecar 方法: {method!r}',
            },
        }
    try:
        result = handler(params)
        return {'id': request_id, 'ok': True, 'result': result}
    except ProviderError as e:
        return {
            'id': request_id,
            'ok': False,
            'error': {'kind': e.kind.value, 'detail': e.detail},
        }
    except Exception as e:
        return {
            'id': request_id,
            'ok': False,
            'error': {
                'kind': classify_exception(e).value,
                'detail': f'{type(e).__name__}: {e}',
            },
        }


def _handle_line(line: str) -> Dict[str, Any]:
    """解析并处理一行 JSON 请求。"""
    try:
        request = json.loads(line)
    except ValueError as e:
        return {
            'id': None,
            'ok': False,
            'error': {'kind': 'internal', 'detail': f'JSON 解析失败: {e}'},
        }
    return handle_request(request)


def serve(stdin: Optional[TextIO] = None,
          stdout: Optional[TextIO] = None) -> None:
    """运行 stdin/stdout JSON 行协议循环。

    Args:
        stdin : 输入流，默认 sys.stdin。
        stdout: 输出流，默认 sys.stdout。
    """
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    for line in input_stream:
        text = line.strip()
        if not text:
            continue
        response = _handle_line(text)
        output_stream.write(json.dumps(response, ensure_ascii=False) + '\n')
        output_stream.flush()
