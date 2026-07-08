#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务管理路由

GET  /api/v1/task/{task_id}          — 查询任务状态
POST /api/v1/task/{task_id}/cancel   — 取消任务
"""

import logging
from fastapi import APIRouter, Request

from ocr_api.common.auth import APIKeyAuthenticator
from ocr_api.common.schemas import APIResponse
from ocr_api.common.task_manager import TaskManager

logger = logging.getLogger(__name__)


def create_task_router(
    task_manager: TaskManager,
    authenticator: APIKeyAuthenticator,
) -> APIRouter:
    """创建任务管理路由

    Args:
        task_manager: 任务管理器实例
        authenticator: 认证器实例
    """
    router = APIRouter(prefix="/api/v1/task", tags=["Task"])

    @router.get("/{task_id}")
    async def get_task_status(task_id: str, request: Request):
        """查询异步任务状态

        返回任务进度、处理结果等信息。

        **任务状态**:
        - pending: 等待处理
        - processing: 处理中（含 progress 进度百分比）
        - completed: 已完成（含完整结果）
        - failed: 失败（含错误信息）
        - cancelled: 已取消
        """
        # 认证
        api_key = authenticator.verify(request)
        task_manager.record_api_call(api_key, f"GET /api/v1/task/{task_id}")

        # 查询任务
        status = task_manager.get_task_status(task_id)
        if not status:
            return APIResponse(
                code=404,
                data=None,
                message=f"任务不存在: {task_id}",
            )

        return APIResponse(
            code=200,
            data=status,
            message="success",
        )

    @router.post("/{task_id}/cancel")
    async def cancel_task(task_id: str, request: Request):
        """取消异步任务

        只能取消 pending 或 processing 状态的任务。
        已处理的部分结果不会返回。

        **注意**:
        - 取消是异步的，可能不会立即停止当前正在处理的文件
        - 已完成的文件结果会被保留但不返回
        """
        # 认证
        api_key = authenticator.verify(request)
        task_manager.record_api_call(api_key, f"POST /api/v1/task/{task_id}/cancel")

        # 获取任务当前状态
        task = task_manager.get_task(task_id)
        if not task:
            return APIResponse(
                code=404,
                data=None,
                message=f"任务不存在: {task_id}",
            )

        if task["status"] not in ("pending", "processing"):
            return APIResponse(
                code=400,
                data=None,
                message=f"任务状态为 {task['status']}，无法取消（仅 pending/processing 可取消）",
            )

        # 执行取消
        success = task_manager.mark_cancelled(task_id)
        if not success:
            return APIResponse(
                code=500,
                data=None,
                message="取消失败，请稍后重试",
            )

        return APIResponse(
            code=200,
            data={
                "task_id": task_id,
                "status": "cancelled",
                "processed": task["processed_count"],
                "total": task["file_count"],
            },
            message="任务已取消",
        )

    return router
