"""v1 契约 JSON Schema 与对象序列化测试。"""
from __future__ import annotations

import json
from pathlib import Path

from core.errors import FailureKind
from tiffgetter import (
    CancelToken,
    Event,
    FetchItem,
    FetchOptions,
    FetchRequest,
    FetchResult,
    OutputOptions,
    Point,
)

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contract" / "v1"

SCHEMA_FILES = [
    "fetch_request.schema.json",
    "fetch_result.schema.json",
    "event.schema.json",
    "source_info.schema.json",
    "coordinate_preview.schema.json",
    "cleanup.schema.json",
    "metadata.schema.json",
]


def _load(name):
    """读取并解析指定 Schema 文件。"""
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def test_all_contract_files_exist_and_are_versioned():
    """七份契约存在，且版本固定为 1.0。"""
    for name in SCHEMA_FILES:
        schema = _load(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for name in ("fetch_request.schema.json", "fetch_result.schema.json",
                 "event.schema.json", "coordinate_preview.schema.json"):
        schema = _load(name)
        assert schema["properties"]["schema_version"]["const"] == "1.0"


def test_fetch_request_schema_constraints():
    """请求契约包含 zoom/buffer/并发/日期/输出布局约束。"""
    schema = _load("fetch_request.schema.json")
    options = schema["properties"]["options"]["properties"]
    assert options["zoom"]["minimum"] == 0
    assert options["zoom"]["maximum"] == 20
    assert options["buffer_radius_m"]["minimum"] == 50
    assert options["buffer_radius_m"]["maximum"] == 5000
    assert options["coord_concurrency"]["minimum"] == 1
    assert options["coord_concurrency"]["maximum"] == 16
    assert options["dedup"]["default"] is True
    assert schema["properties"]["points"]["minItems"] == 1
    assert schema["properties"]["output"]["properties"]["layout"]["enum"] == [
        "auto", "explicit"
    ]


def test_fetch_result_schema_status_and_exit_codes():
    """结果契约状态、退出码与失败类型覆盖完整。"""
    schema = _load("fetch_result.schema.json")
    assert schema["properties"]["status"]["enum"] == [
        "success", "partial", "failed", "cancelled"
    ]
    assert schema["properties"]["exit_code"]["enum"] == [0, 2, 3, 4, 5, 6]
    failure_enum = set(schema["$defs"]["failure_kind"]["enum"])
    failure_enum.discard(None)
    assert failure_enum == {kind.value for kind in FailureKind}
    assert "cancelled" in failure_enum


def test_event_schema_types():
    """事件契约包含五类事件。"""
    schema = _load("event.schema.json")
    assert schema["properties"]["type"]["enum"] == [
        "log", "progress", "date_result", "coordinate_result", "run_summary"
    ]


def test_fetch_request_roundtrip_is_json_serializable():
    """FetchRequest 字典可 JSON 序列化并原样还原。"""
    request = FetchRequest(
        source="wayback",
        points=[Point("p1", "Tokyo", 35.6586, 139.7454)],
        options=FetchOptions(
            zoom=18,
            buffer_radius_m=500,
            date_start=None,
            date_end=None,
            dedup=True,
            coord_concurrency=1,
        ),
        output=OutputOptions(root=None, layout="auto"),
    )

    payload = request.to_dict()

    assert json.loads(json.dumps(payload)) == payload
    assert FetchRequest.from_dict(payload).to_dict() == payload
    assert payload["schema_version"] == "1.0"
    assert payload["points"][0] == {
        "id": "p1", "name": "Tokyo", "lat": 35.6586, "lon": 139.7454
    }


def test_fetch_result_roundtrip_and_event_roundtrip():
    """FetchResult 与 Event 的字典序列化保持字段一致。"""
    item = FetchItem(
        point_id="p1",
        point_name="Tokyo",
        date="2024-01-01",
        release_id="123",
        status="success",
        failure_kind=None,
        detail=None,
        effective_zoom=18,
        assets={
            "png": "out/2024-01-01/2024-01-01.png",
            "tif": None,
            "metadata": "out/2024-01-01/metadata.json",
        },
        bounds={
            "min_lon": 139.74,
            "min_lat": 35.65,
            "max_lon": 139.75,
            "max_lat": 35.66,
        },
        diagnostics={"by_kind": {}, "failed_tiles": 0, "samples": []},
        metadata_source="online",
        metadata_fetched_at="2026-01-01T00:00:00+00:00",
    )
    result = FetchResult(
        request_id="req-1",
        status="success",
        exit_code=0,
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        items=[item],
        diagnostics={"by_kind": {}, "failed_tiles": 0, "samples": []},
    )
    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert FetchResult.from_dict(payload).to_dict() == payload

    event = Event(
        type="date_result",
        job_id="req-1",
        sequence=1,
        timestamp="2026-01-01T00:00:00+00:00",
        item={"point_id": "p1"},
    )
    event_payload = event.to_dict()
    assert json.loads(json.dumps(event_payload)) == event_payload
    assert Event.from_dict(event_payload).to_dict() == event_payload


def test_cancel_token_lifecycle():
    """CancelToken 初始未取消，cancel 后永久取消。"""
    token = CancelToken()
    assert token.is_cancelled() is False
    token.cancel()
    assert token.is_cancelled() is True
    token.cancel()
    assert token.is_cancelled() is True
