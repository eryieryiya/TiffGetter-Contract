"""影像获取核心实现包。

子模块职责：
- geo     : 瓦片坐标、WGS84 边界与 PNG 裁剪等纯几何逻辑
- dedup   : 字节级 MD5 / 感知 dHash 去重
- release : metadata 读取与 release 日期筛选
- fetch   : ImageFetcher 下载编排、拼接与 GeoTIFF 输出

日志统一写入 ``tiffgetter`` 日志命名空间，默认由 NullHandler 吸收，
不会直接写 stdout/stderr；调用方可注入 EventSink 消费日志事件。
"""
