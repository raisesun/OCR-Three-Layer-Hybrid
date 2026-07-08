#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配额查询路由

GET /api/v1/quota — 查询 API 调用配额使用情况
"""

import logging
from fastapi import APIRouter, Request

from ocr_api.common.auth import APIKeyAuthenticator
from ocr_api.common.schemas import APIResponse
from ocr_api.common.task_manager import TaskManager

logger = logging.getLogger(__name__)


def create_quota_router(
    task_manager: TaskManager,
    authenticator: APIKeyAuthenticator,
) -> APIRouter:
    """创建配额查询路由

    Args:
        task_manager: 任务管理器实例
        authenticator: 认证器实例
    """
    router = APIRouter(prefix="/api/v1", tags=["Quota"])

    @router.get("/quota")
    async def get_quota(request: Request):
        """查询配额使用情况

        返回当前 API Key 的调用量、存储使用、异步任务数量等信息。

        **配额限制（默认值）**:
        - API 调用: 6000 次/小时（100 次/分钟）
        - 存储: 10GB
        - 异步任务: 100 个并发
        """
        # 认证
        api_key = authenticator.verify(request)
        task_manager.record_api_call(api_key, "GET /api/v1/quota")

        # 获取配额数据
        quota = task_manager.get_quota(api_key)

        return APIResponse(
            code=200,
            data=quota,
            message="success",
        )

    return router
