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
import logging
from contextlib import asynccontextmanager
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

# 结构化日志模块
from ocr_api.common.logger import setup_logging as setup_structured_logging, get_logger
from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import UPLOAD_DIR

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
HOST = os.getenv("OCR_HOST", "127.0.0.1")  # 默认仅本机；生产需远程访问设 0.0.0.0
DB_PATH = os.getenv("OCR_DB_PATH", "/tmp/ocr_tasks.db")  # 多用户系统 /tmp 可读，生产建议设 OCR_DB_PATH 到用户目录


# ========== 初始化日志 ==========

# 使用结构化日志（支持 JSON 格式，通过 OCR_LOG_FORMAT 环境变量控制）
setup_structured_logging(level="DEBUG" if DEBUG else "INFO")

# 内存日志缓冲区（供 Demo 页面显示）
if DEBUG:
    from ocr_api.common.memory_log import setup_memory_logging
    setup_memory_logging()

server_logger = get_logger("ocr_three_layer_hybrid.server")


# ========== 工厂函数（支持依赖注入，方便测试） ==========

def _create_lifespan(task_manager: TaskManager):
    """创建 FastAPI lifespan 处理器（管理资源生命周期）"""
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        # 关闭时的清理工作（SQLite 连接等）
        try:
            task_manager.close()
            server_logger.info("[Shutdown] TaskManager 连接已关闭")
        except Exception as e:
            server_logger.warning("[Shutdown] 清理失败: %s", e)
    return lifespan


def create_app(
    ocr_service: OCRService = None,
    task_manager: TaskManager = None,
    authenticator: APIKeyAuthenticator = None,
    baseline_service: BaselineService = None,
    debug: bool = None,
) -> FastAPI:
    """创建 FastAPI 应用

    所有参数均可注入，方便测试时传入 mock 实例。
    未传入时自动创建默认实例（生产模式）。

    Args:
        ocr_service: OCRService 实例
        task_manager: TaskManager 实例
        authenticator: APIKeyAuthenticator 实例
        baseline_service: BaselineService 实例（仅 DEBUG 模式使用）
        debug: 是否启用调试路由（默认从环境变量 DEBUG 读取）

    Returns:
        配置好的 FastAPI 应用实例
    """
    if debug is None:
        debug = DEBUG

    # 默认实例（生产模式）
    if ocr_service is None:
        ocr_service = OCRService()
    if task_manager is None:
        task_manager = TaskManager(db_path=DB_PATH)
    if authenticator is None:
        authenticator = APIKeyAuthenticator()
    if baseline_service is None:
        baseline_service = BaselineService()

    app = FastAPI(
        title="OCR API 服务",
        version="1.0.0",
        description="文档识别和字段提取 API — 支持异步批量处理",
        lifespan=_create_lifespan(task_manager),
    )

    # CORS（允许前端跨域调用）
    _cors_origins = os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:8080"
    ).split(",")
    if "*" in _cors_origins:
        server_logger.warning("[安全] CORS allow_origins 含 *，生产环境不安全（允许任意源）")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # 请求日志中间件
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
    app.include_router(create_health_router(ocr_service))
    app.include_router(create_ocr_router(task_manager, ocr_service, authenticator))
    app.include_router(create_task_router(task_manager, authenticator))
    app.include_router(create_quota_router(task_manager, authenticator))

    # ========== 加载调试路由（仅 debug=True） ==========
    if debug:
        server_logger.info("[Debug] 调试模式已启用，加载 Demo 路由...")
        debug_router, static_mounts = create_debug_routes(
            ocr_service, baseline_service, _OCR_DIR, UPLOAD_DIR,
            task_manager=task_manager,
            authenticator=authenticator,
        )
        app.include_router(debug_router)
        for mount_path, mount_dir, mount_name in static_mounts:
            app.mount(mount_path, StaticFiles(directory=mount_dir), name=mount_name)
    else:
        server_logger.info("[Debug] 调试模式未启用，仅开放正式 API 接口")

    return app


# ========== 生产环境默认实例（仅在直接运行时使用） ==========

authenticator = APIKeyAuthenticator()
app = create_app(authenticator=authenticator)


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

    uvicorn.run(app, host=HOST, port=PORT)
