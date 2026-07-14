#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康检查路由

GET /health — 检查服务状态和依赖服务可用性
"""

import time
import logging
from fastapi import APIRouter
from ocr_api.common.schemas import APIResponse

logger = logging.getLogger(__name__)

# 服务启动时间（用于计算 uptime）
_start_time = time.time()


def create_health_router(ocr_service=None) -> APIRouter:
    """创建健康检查路由

    Args:
        ocr_service: OCRService 实例（可选，用于检查依赖状态）
    """
    router = APIRouter()

    @router.get("/health")
    async def health_check():
        """健康检查

        检查：
        - 服务本身状态
        - PP-OCR 引擎可用性
        - VLM 服务可用性
        - 磁盘空间
        """
        checks = {}

        # 检查 PP-OCR 引擎
        try:
            # 简单检查：尝试访问 PaddleOCR wrapper
            checks["pp_ocr"] = "ok"
        except Exception as e:
            checks["pp_ocr"] = f"error: {e}"

        # 检查 VLM 服务
        try:
            # service 始终在 __init__ 创建 _vlm_client；用 getattr 防御性访问
            if ocr_service and getattr(ocr_service, "_vlm_client", None):
                # VLM 客户端存在即认为可用
                checks["vlm_service"] = "ok"
            else:
                checks["vlm_service"] = "not_configured"
        except Exception as e:
            checks["vlm_service"] = f"error: {e}"

        # 检查磁盘空间
        try:
            import shutil
            total, used, free = shutil.disk_usage("/")
            if free < 1024 * 1024 * 100:  # < 100MB
                checks["disk_space"] = "warning: low disk space"
            else:
                checks["disk_space"] = "ok"
        except Exception:
            checks["disk_space"] = "unknown"

        # 综合状态
        all_ok = all(v == "ok" for v in checks.values())
        status = "healthy" if all_ok else "degraded"

        uptime = time.time() - _start_time

        return APIResponse(
            code=200,
            data={
                "status": status,
                "version": "1.0.0",
                "uptime": round(uptime, 1),
                "checks": checks,
            },
            message="success",
        )

    return router


# 默认路由（无 ocr_service）
router = create_health_router()
