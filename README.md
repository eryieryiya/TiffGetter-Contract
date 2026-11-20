# TiffGetter-Contract

这是 **库，不是应用**。`tiffgetter` 提供 v1 契约对象与无界面的影像抓取客户端，不包含 CLI、GUI、tkinter 或桌面打包入口。

## 安装

```powershell
pip install -e .
# 可选：需要 GeoTIFF 输出时
pip install -e ".[geotiff]"
```

`rasterio` 是可选依赖；缺失时抓取仍会输出 PNG，`assets.tif` 为 `null`。安装后库会自动使用 rasterio 自带的 PROJ/GDAL 数据，避免系统 PostgreSQL/PostGIS 的 `proj.db` 版本冲突。

## 调用示例

```python
from tiffgetter import Client, FetchRequest, Point, FetchOptions

client = Client()
result = client.fetch(FetchRequest(source="wayback", points=[Point("p1", "Tokyo", 35.6586, 139.7454)]))
print(result.status, result.exit_code, len(result.items))
```

请求/结果/事件契约位于 `contract/v1/`，`schema_version` 固定为 `"1.0"`。事件通过 `on_event` 回调或 `EventSink` 流出，类型为 `log`、`progress`、`date_result`、`coordinate_result`、`run_summary`。`CancelToken` 支持协作式取消。

## 测试

```powershell
python -m pytest
```

测试全部离线，不访问真实数据源。

## sidecar（内部 API）

`tiffgetter.sidecar.serve()` 通过 stdin/stdout JSON 行提供 `health`、`parse_coordinates`、`write_geotiff`、`google.releases`、`google.download_release`，供方案 B 的 Go 进程调用。它不是用户 CLI。
