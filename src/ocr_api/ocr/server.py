#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR API 服务 — 主入口

启动: python -m ocr_api.ocr.server
  或: cd src && python -m ocr_api.ocr.server
端口: 8888

环境变量:
    OCR_API_KEYS=key1,key2    — API Key 列表（逗号分隔）
    DEBUG=true                — 启用调试路由（Demo UI、基线对比等）
    OCR_DB_PATH=/path/to.db   — SQLite 数据库路径（默认 /tmp/ocr_tasks.db）

架构:
    src/ocr_api/
    ├── common/
    │   ├── auth.py           ← API Key 认证
    │   ├── task_manager.py   ← 异步任务管理（SQLite 持久化）
    │   └── schemas.py        ← 请求/响应模型
    └── ocr/
        ├── server.py         ← 本文件：初始化服务、加载路由、启动 HTTP
        ├── debug_routes.py   ← DEBUG=true 时加载的内部调试路由
        └── routes/
            ├── health.py     ← GET  /health
            ├── ocr.py        ← POST /api/v1/ocr/async
            ├── task.py       ← GET  /api/v1/task/{id} + POST .../cancel
            └── quota.py      ← GET  /api/v1/quota
"""

import os
import sys
import time
import tempfile
import logging
from pathlib import Path

# ========== 路径设置 ==========

# 确保 src/ 在 sys.path 中（支持直接 python server.py 启动）
_OCR_DIR = Path(__file__).parent          # src/ocr_api/ocr/
_API_DIR = _OCR_DIR.parent                # src/ocr_api/
_SRC_DIR = _API_DIR.parent                # src/
_PROJECT_DIR = _SRC_DIR.parent            # 项目根目录
sys.path.insert(0, str(_SRC_DIR))
sys.path.insert(0, str(_PROJECT_DIR))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from ocr_three_layer_hybrid.service import setup_logging, OCRService

# 通用组件（可复用）
from ocr_api.common.auth import APIKeyAuthenticator
from ocr_api.common.task_manager import TaskManager

# OCR 业务模块
from ocr_api.ocr.baseline_service import BaselineService
from ocr_api.ocr.routes.health import create_health_router
from ocr_api.ocr.routes.ocr import create_ocr_router
from ocr_api.ocr.routes.task import create_task_router
from ocr_api.ocr.routes.quota import create_quota_router
from ocr_api.ocr.debug_routes import create_debug_routes


# ========== 配置 ==========

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
PORT = int(os.getenv("OCR_PORT", "8888"))
DB_PATH = os.getenv("OCR_DB_PATH", "/tmp/ocr_tasks.db")


# ========== 初始化日志 ==========

setup_logging(level="DEBUG" if DEBUG else "INFO")
server_logger = logging.getLogger("ocr_three_layer_hybrid.server")


# ========== 初始化服务 ==========

ocr_service = OCRService()
baseline_service = BaselineService()
authenticator = APIKeyAuthenticator()
task_manager = TaskManager(db_path=DB_PATH)

# 临时上传目录
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="ocr_demo_"))


# ========== FastAPI 应用 ==========

app = FastAPI(
    title="OCR API 服务",
    version="1.0.0",
    description="文档识别和字段提取 API — 支持异步批量处理",
)

# CORS（允许前端跨域调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 请求日志中间件 ==========

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed_ms = round((time.time() - start) * 1000, 1)
    path = request.url.path
    if path.startswith("/api/") or path == "/health":
        server_logger.info(
            "[API] %s %s | %d | %.1fms",
            request.method, path, response.status_code, elapsed_ms,
        )
    return response


# ========== 加载正式 API 路由（始终启用） ==========

# 1. 健康检查
app.include_router(create_health_router(ocr_service))

# 2. 异步 OCR 提交
app.include_router(create_ocr_router(task_manager, ocr_service, authenticator))

# 3. 任务管理（查询 + 取消）
app.include_router(create_task_router(task_manager, authenticator))

# 4. 配额查询
app.include_router(create_quota_router(task_manager, authenticator))


# ========== 加载调试路由（仅 DEBUG=true） ==========

if DEBUG:
    server_logger.info("[Debug] 调试模式已启用，加载 Demo 路由...")
    debug_router, static_mounts = create_debug_routes(
        ocr_service, baseline_service, _OCR_DIR, UPLOAD_DIR
    )
    app.include_router(debug_router)

    # 挂载静态文件
    for mount_path, mount_dir, mount_name in static_mounts:
        app.mount(mount_path, StaticFiles(directory=mount_dir), name=mount_name)
else:
    server_logger.info("[Debug] 调试模式未启用，仅开放正式 API 接口")


# ========== 启动 ==========

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("  OCR API 服务 v1.0.0")
    print("=" * 60)
    print(f"  访问地址:  http://localhost:{PORT}")
    print(f"  API 文档:  http://localhost:{PORT}/docs")
    print(f"  调试模式:  {'✅ 已启用' if DEBUG else '❌ 未启用 (设置 DEBUG=true 启用)'}")
    print(f"  认证状态:  {'✅ 已启用' if authenticator.is_enabled() else '⚠️  未配置 (设置 OCR_API_KEYS)'}")
    print(f"  数据库:    {DB_PATH}")
    print("=" * 60)

    # 打印路由列表
    print("\n  已注册路由:")
    for route in app.routes:
        if hasattr(route, "methods"):
            for method in route.methods:
                print(f"    {method:6s} {route.path}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=PORT)
