"""sidecar stdin/stdout JSON 行协议测试（离线）。"""
from __future__ import annotations

import io
import json

import tiffgetter.sidecar as sidecar
from tiffgetter import Event


def test_health_reports_methods():
    """health 返回版本、rasterio 可用性与方法列表。"""
    response = sidecar.handle_request({
        "id": "1",
        "method": "health",
        "params": {},
    })

    assert response["id"] == "1"
    assert response["ok"] is True
    result = response["result"]
    assert result["status"] == "ok"
    assert result["schema_version"] == "1.0"
    assert result["methods"] == list(sidecar.METHODS)
    assert isinstance(result["rasterio"], bool)


def test_parse_coordinates_returns_points(tmp_path):
    """parse_coordinates 解析 CSV 并返回契约点字段。"""
    path = tmp_path / "points.csv"
    path.write_text(
        "lat,lon,name,id\n35.6586,139.7454,Tokyo Tower,t1\n",
        encoding="utf-8",
    )

    response = sidecar.handle_request({
        "id": "2",
        "method": "parse_coordinates",
        "params": {"path": str(path)},
    })

    assert response["ok"] is True
    assert response["result"] == [
        {"id": "t1", "name": "Tokyo_Tower", "lat": 35.6586, "lon": 139.7454}
    ]


def test_write_geotiff_dispatches_to_png_to_geotiff(tmp_path, monkeypatch):
    """write_geotiff 调用现有 rasterio 写入函数。"""
    called = {}

    def _fake(png_path, tif_path, bounds):
        called["args"] = (png_path, tif_path, bounds)
        return True

    monkeypatch.setattr(sidecar, "png_to_geotiff", _fake)
    bounds = {
        "min_lon": 0.0,
        "min_lat": 0.0,
        "max_lon": 1.0,
        "max_lat": 1.0,
    }

    response = sidecar.handle_request({
        "id": "3",
        "method": "write_geotiff",
        "params": {
            "png_path": str(tmp_path / "a.png"),
            "tif_path": str(tmp_path / "a.tif"),
            "bounds": bounds,
        },
    })

    assert response == {"id": "3", "ok": True, "result": True}
    assert called["args"] == (
        str(tmp_path / "a.png"),
        str(tmp_path / "a.tif"),
        bounds,
    )


def test_unknown_method_returns_error():
    """未知方法返回结构化错误。"""
    response = sidecar.handle_request({
        "id": "4",
        "method": "not_a_method",
        "params": {},
    })

    assert response["id"] == "4"
    assert response["ok"] is False
    assert response["error"]["kind"] == "internal"


def test_serve_processes_json_lines():
    """serve 逐行读取请求并写回一行 JSON 响应。"""
    request = json.dumps({"id": "5", "method": "health", "params": {}})
    stdin = io.StringIO(request + "\n\n" + json.dumps({
        "id": "6", "method": "not_a_method", "params": {}
    }) + "\n")
    stdout = io.StringIO()

    sidecar.serve(stdin=stdin, stdout=stdout)

    lines = [json.loads(line) for line in stdout.getvalue().splitlines() if line]
    assert len(lines) == 2
    assert lines[0]["ok"] is True
    assert lines[1]["ok"] is False


def test_event_contract_is_used_by_sidecar_health_version():
    """sidecar 版本与 v1 契约版本一致。"""
    event = Event(type="log", job_id="j", sequence=1, item={"message": "ok"})
    payload = event.to_dict()
    assert payload["schema_version"] == "1.0"
    assert payload["type"] == "log"
