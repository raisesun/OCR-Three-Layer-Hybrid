#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务管理路由

GET  /api/v1/tasks                   — 列出任务（分页）
GET  /api/v1/task/{task_id}          — 查询任务状态
POST /api/v1/task/{task_id}/cancel   — 取消任务
"""

import logging
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query

from ocr_api.common.auth import APIKeyAuthenticator
from ocr_api.common.schemas import APIResponse
from ocr_api.common.task_manager import TaskManager
from ocr_api.common.logger import set_log_context, clear_log_context

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
    router = APIRouter(prefix="/api/v1", tags=["Task"])

    @router.get("/tasks")
    async def list_tasks(
        request: Request,
        status: Optional[str] = Query(None, description="状态过滤: pending, processing, completed, failed, cancelled"),
        page: int = Query(1, ge=1, description="页码（从 1 开始）"),
        size: int = Query(20, ge=1, le=100, description="每页大小（1-100）"),
    ):
        """列出当前租户的异步任务

        支持按状态过滤和分页查询。

        **状态说明**:
        - pending: 等待处理
        - processing: 处理中
        - completed: 已完成
        - failed: 失败
        - cancelled: 已取消

        **分页**:
        - page: 页码，从 1 开始
        - size: 每页大小，1-100，默认 20
        """
        # 认证
        api_key = authenticator.verify(request)
        set_log_context(api_key=f"{api_key[:8]}...")
        task_manager.record_api_call(api_key, "GET /api/v1/tasks")

        # 查询任务列表
        result = task_manager.list_tasks(
            api_key=api_key,
            status_filter=status,
            page=page,
            size=size,
        )

        logger.info("列出任务 | status=%s | page=%d | size=%d | total=%d",
                     status, page, size, result["total"])

        return APIResponse(
            code=200,
            data=result,
            message="success",
        )

    @router.get("/task/{task_id}")
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
        set_log_context(api_key=f"{api_key[:8]}...", task_id=task_id)
        task_manager.record_api_call(api_key, f"GET /api/v1/task/{task_id}")

        # 查询任务
        status = task_manager.get_task_status(task_id)
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"任务不存在: {task_id}",
            )

        return APIResponse(
            code=200,
            data=status,
            message="success",
        )

    @router.post("/task/{task_id}/cancel")
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
        set_log_context(api_key=f"{api_key[:8]}...", task_id=task_id)
        task_manager.record_api_call(api_key, f"POST /api/v1/task/{task_id}/cancel")

        # 检查任务是否存在
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(
                status_code=404,
                detail=f"任务不存在: {task_id}",
            )

        # 原子取消：SQL WHERE 守卫保证不会覆盖已完成/已取消的任务
        success = task_manager.mark_cancelled(task_id)
        if not success:
            # 取消失败，重新读取最新状态以返回准确的错误信息
            current_task = task_manager.get_task(task_id)
            current_status = current_task["status"] if current_task else "不存在"
            raise HTTPException(
                status_code=400,
                detail=f"任务状态为 {current_status}，无法取消（仅 pending/processing 可取消）",
            )

        logger.info("任务已取消 | processed=%d/%d", task["processed_count"], task["file_count"])

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
