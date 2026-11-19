"""Client 单点、批量、去重、GeoTIFF 降级、状态码与取消测试。

全部离线：用实现 TileSource 的假数据源替换注册表，瓦片为内存生成的 PNG。
"""
from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest
from PIL import Image

import core.fetch
import providers.registry as registry
import utils.cleanup as cleanup_utils
from core.errors import FailureKind, TileResult
from core.fetch import ImageFetcher
from providers.base import SourceInfo, TileSource
from tiffgetter import (
    CancelToken,
    Client,
    Event,
    FetchOptions,
    FetchRequest,
    OutputOptions,
    Point,
)


def _png_bytes(color=(40, 80, 120), size=(256, 256)) -> bytes:
    """生成内存 PNG 字节，作为假瓦片内容。"""
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeSource(TileSource):
    """固定 release 列表的假数据源，不发起任何网络请求。"""

    def __init__(self, dates, cancel_token=None):
        self.info = SourceInfo(
            name="wayback",
            display_name="Fake Wayback",
            supports_history=True,
            min_zoom=1,
            max_zoom=20,
            max_concurrency=4,
            attribution="Fake",
        )
        self._dates = list(dates)
        self._cancel_token = cancel_token
        self._tile_bytes = _png_bytes()
        self.tile_calls = 0

    def available_releases(self, lat, lon, zoom):
        """返回按输入顺序排列的假 release。"""
        return [
            {
                "id": f"rel-{date}",
                "date": date,
                "name": f"Fake {date}",
                "source": self.info.name,
                "attribution": self.info.attribution,
                "metadata_source": "native",
            }
            for date in self._dates
        ]

    def fetch_tile(self, z, x, y, release):
        """返回固定 PNG 字节；可选在首次调用时触发取消。"""
        if self._cancel_token is not None and self.tile_calls == 0:
            self._cancel_token.cancel()
        self.tile_calls += 1
        return TileResult.success(self._tile_bytes)


@pytest.fixture
def offline_env(monkeypatch, tmp_path, no_cleanup):
    """把临时目录、睡眠、中心瓦片预筛隔离到测试环境中。"""
    work = tmp_path / "_mkdtemp"
    work.mkdir()
    real_mkdtemp = tempfile.mkdtemp
    monkeypatch.setattr(
        cleanup_utils.tempfile,
        "mkdtemp",
        lambda prefix=None, dir=None: real_mkdtemp(prefix=prefix, dir=str(work)),
    )
    monkeypatch.setattr(core.fetch.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ImageFetcher, "_fetch_center_tile_dhash", lambda self, *a, **k: None
    )
    return work


@pytest.fixture
def install_fake(monkeypatch, offline_env):
    """安装假数据源，返回工厂函数。"""

    def _install(dates, cancel_token=None):
        source = FakeSource(dates, cancel_token=cancel_token)
        monkeypatch.setattr(core.fetch, "get_source", lambda name=None: source)
        monkeypatch.setattr(registry, "get_source", lambda name=None: source)
        return source

    return _install


def _request(tmp_path, points, dates_options=None, output="out"):
    """构造指向 tmp_path 的 FetchRequest。"""
    return FetchRequest(
        source="wayback",
        points=points,
        options=dates_options or FetchOptions(zoom=18, buffer_radius_m=500),
        output=OutputOptions(root=str(tmp_path / output), layout="explicit"),
    )


def test_single_point_success_with_png_and_metadata(
    install_fake, tmp_path, monkeypatch
):
    """单点成功：输出 PNG、metadata，tif 降级为 null，事件完整。"""
    install_fake(["2024-01-01"])
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)
    events = []
    token = CancelToken()

    result = Client().fetch(
        _request(
            tmp_path,
            [Point("p1", "Tokyo", 35.6586, 139.7454)],
            FetchOptions(zoom=18, buffer_radius_m=500),
        ),
        on_event=events.append,
        cancel=token,
    )

    assert result.status == "success"
    assert result.exit_code == 0
    assert len(result.items) == 1
    item = result.items[0]
    assert item.point_id == "p1"
    assert item.point_name == "Tokyo"
    assert item.status == "success"
    assert item.effective_zoom == 18
    assert item.assets["png"] is not None
    assert Path(item.assets["png"]).exists()
    assert item.assets["tif"] is None
    assert item.assets["metadata"] is not None
    metadata = json.loads(
        Path(item.assets["metadata"]).read_text(encoding="utf-8")
    )
    assert metadata["schema_version"] == "1.0"
    assert metadata["source"] == "wayback"
    assert set(item.bounds) == {"min_lon", "min_lat", "max_lon", "max_lat"}

    assert all(isinstance(event, Event) for event in events)
    types = [event.type for event in events]
    assert "log" in types
    assert "progress" in types
    assert "date_result" in types
    assert "run_summary" in types
    date_events = [event for event in events if event.type == "date_result"]
    assert date_events[0].item["point_id"] == "p1"
    assert date_events[0].item["point_name"] == "Tokyo"
    assert [event.sequence for event in events] == sorted(
        event.sequence for event in events
    )
    assert _assert_result_roundtrip(result)


def _assert_result_roundtrip(result):
    """辅助断言：FetchResult 字典可 JSON 序列化并原样还原。"""
    from tiffgetter import FetchResult

    payload = result.to_dict()
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload
    restored = FetchResult.from_dict(payload).to_dict()
    assert restored == payload
    return True


def test_batch_coordinates_emit_coordinate_result(install_fake, tmp_path, monkeypatch):
    """批量：每个坐标独立子目录，并产生 coordinate_result 事件。"""
    install_fake(["2024-01-01"])
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)
    events = []

    result = Client().fetch(
        _request(
            tmp_path,
            [
                Point("a", "Point A", 35.0, 139.0),
                Point("b", "Point B", 36.0, 140.0),
            ],
            FetchOptions(zoom=18, buffer_radius_m=500, coord_concurrency=2),
            output="batch",
        ),
        on_event=events.append,
    )

    assert result.status == "success"
    assert result.exit_code == 0
    assert len(result.items) == 2
    assert {item.point_id for item in result.items} == {"a", "b"}
    assert (tmp_path / "batch" / "a").is_dir()
    assert (tmp_path / "batch" / "b").is_dir()
    coordinate_events = [e for e in events if e.type == "coordinate_result"]
    assert len(coordinate_events) == 2
    assert sorted(e.item["index"] for e in coordinate_events) == [1, 2]


def test_dedup_keeps_only_earliest_date(install_fake, tmp_path, monkeypatch):
    """相同影像的多个 release 仅保留最早日期，其余标记 duplicate。"""
    install_fake(["2015-06-01", "2016-06-01", "2017-06-01"])
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)

    result = Client().fetch(
        _request(
            tmp_path,
            [Point("p1", "Tokyo", 35.0, 139.0)],
            FetchOptions(zoom=18, buffer_radius_m=500, dedup=True),
        )
    )

    assert [item.status for item in result.items] == [
        "success", "duplicate", "duplicate"
    ]
    date_dirs = sorted(
        path.name
        for path in (tmp_path / "out").iterdir()
        if path.is_dir() and not path.name.startswith("_probe")
    )
    assert date_dirs == ["2015-06-01"]


def test_dedup_disabled_outputs_every_date(install_fake, tmp_path, monkeypatch):
    """dedup=False 时每个日期都完整输出。"""
    install_fake(["2015-06-01", "2016-06-01"])
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)

    result = Client().fetch(
        _request(
            tmp_path,
            [Point("p1", "Tokyo", 35.0, 139.0)],
            FetchOptions(zoom=18, buffer_radius_m=500, dedup=False),
        )
    )

    assert [item.status for item in result.items] == ["success", "success"]
    assert (tmp_path / "out" / "2015-06-01" / "2015-06-01.png").exists()
    assert (tmp_path / "out" / "2016-06-01" / "2016-06-01.png").exists()


def test_geotiff_unavailable_returns_false(tmp_path, monkeypatch, sample_png):
    """rasterio 不可用时 GeoTIFF 写入降级返回 False。"""
    png = sample_png(tmp_path / "a.png")
    monkeypatch.setattr(core.fetch, "_RASTERIO_AVAILABLE", False)

    ok = core.fetch.png_to_geotiff(
        str(png),
        str(tmp_path / "a.tif"),
        {
            "min_lon": 0.0,
            "min_lat": 0.0,
            "max_lon": 1.0,
            "max_lat": 1.0,
        },
    )

    assert ok is False


def test_parameter_error_for_date_range_on_non_history_source(install_fake, tmp_path):
    """非历史源携带日期范围返回参数错误与退出码 2。"""
    events = []
    request = FetchRequest(
        source="esri",
        points=[Point("p1", "Tokyo", 35.0, 139.0)],
        options=FetchOptions(
            zoom=10,
            buffer_radius_m=500,
            date_start="2020-01-01",
            date_end="2020-12-31",
        ),
        output=OutputOptions(root=str(tmp_path / "out"), layout="explicit"),
    )

    result = Client().fetch(request, on_event=events.append)

    assert result.status == "failed"
    assert result.exit_code == 2
    assert result.items == []
    assert any(event.type == "run_summary" and event.item["exit_code"] == 2
               for event in events)


def test_all_interface_changed_returns_exit_5(install_fake, tmp_path):
    """全部失败且均为 interface_changed 时退出码为 5。"""
    source = install_fake(["2024-01-01"])

    def _fetch_tile(z, x, y, release):
        return TileResult.failure(FailureKind.INTERFACE_CHANGED, "接口变更")

    source.fetch_tile = _fetch_tile

    result = Client().fetch(
        _request(tmp_path, [Point("p1", "Tokyo", 35.0, 139.0)])
    )

    assert all(item.status == "failed" for item in result.items)
    assert all(item.failure_kind == "interface_changed" for item in result.items)
    assert result.status == "failed"
    assert result.exit_code == 5


def test_partial_failure_returns_exit_3(install_fake, tmp_path, monkeypatch):
    """部分日期失败时返回 partial 与退出码 3。"""
    install_fake(["2024-01-01", "2024-02-01"])
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)

    from core.fetch import ImageFetcher as RealFetcher

    original = RealFetcher.download_image

    def _download(self, lat, lon, zoom, date_info, output_dir,
                  buffer_size=500, probe_root=None, dedup=True):
        if date_info["date"] == "2024-02-01":
            return {
                "status": "failed",
                "date": date_info["date"],
                "release_id": date_info.get("id"),
                "failure_kind": FailureKind.FORBIDDEN,
                "detail": "HTTP 403",
                "failures": [],
            }
        return original(
            self, lat, lon, zoom, date_info, output_dir,
            buffer_size, probe_root, dedup,
        )

    monkeypatch.setattr(RealFetcher, "download_image", _download)

    result = Client().fetch(
        _request(tmp_path, [Point("p1", "Tokyo", 35.0, 139.0)])
    )

    assert [item.status for item in result.items] == ["success", "failed"]
    assert result.status == "partial"
    assert result.exit_code == 3


def test_cancel_stops_after_completed_release(install_fake, tmp_path, monkeypatch):
    """取消发生在首个 release 后：保留已完成资产，状态 cancelled / 6。"""
    token = CancelToken()
    install_fake(["2024-01-01", "2024-02-01"], cancel_token=token)
    monkeypatch.setattr(ImageFetcher, "png_to_geotiff", lambda *a, **k: False)

    result = Client().fetch(
        _request(
            tmp_path,
            [Point("p1", "Tokyo", 35.0, 139.0)],
            FetchOptions(zoom=10, buffer_radius_m=50),
        ),
        cancel=token,
    )

    assert token.is_cancelled()
    assert result.status == "cancelled"
    assert result.exit_code == 6
    assert len(result.items) == 1
    assert result.items[0].status == "success"
    assert Path(result.items[0].assets["png"]).exists()
    assert not (tmp_path / "out" / "2024-02-01").exists()
