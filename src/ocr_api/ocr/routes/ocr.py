#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步 OCR 提交路由

POST /api/v1/ocr/async — 提交大批量异步处理任务
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, Request, Depends, HTTPException

from ocr_api.common.auth import APIKeyAuthenticator
from ocr_api.common.schemas import APIResponse
from ocr_api.common.task_manager import TaskManager, TaskWorker
from ocr_three_layer_hybrid.config import SUPPORTED_FILE_EXTENSIONS, UPLOAD_DIR

logger = logging.getLogger(__name__)

# 文件大小限制
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def create_ocr_router(
    task_manager: TaskManager,
    ocr_service,
    authenticator: APIKeyAuthenticator,
) -> APIRouter:
    """创建异步 OCR 提交路由

    Args:
        task_manager: 任务管理器实例
        ocr_service: OCRService 实例
        authenticator: 认证器实例
    """
    router = APIRouter(prefix="/api/v1/ocr", tags=["OCR"])

    @router.post("/async", status_code=202, response_model=APIResponse)
    async def submit_async_task(
        request: Request,
        files: List[UploadFile] = File(..., description="图片/PDF 文件列表，最多 500 个"),
        callback_url: Optional[str] = Form(None, description="结果回调 URL"),
        priority: str = Form("normal", description="优先级：normal / urgent"),
        enable_vlm: bool = Form(True, description="是否启用 VLM 层"),
    ):
        """提交异步批量处理任务

        接收文件后立即返回 task_id，后台异步处理。
        使用 GET /api/v1/task/{task_id} 查询进度和结果。

        **限制**:
        - 文件数量: ≤ 500 个
        - 单文件大小: ≤ 20MB
        - 总大小: ≤ 500MB
        """
        # 1. 认证
        api_key = authenticator.verify(request)

        # 2. 记录 API 调用
        task_manager.record_api_call(api_key, "POST /api/v1/ocr/async")

        # 3. 校验文件数量
        if len(files) > 500:
            raise HTTPException(
                status_code=400,
                detail=f"文件数量超限：最多 500 个，当前 {len(files)} 个",
            )

        if len(files) == 0:
            raise HTTPException(
                status_code=400,
                detail="未上传任何文件",
            )

        # 4. 先校验所有文件格式和大小（避免部分保存后校验失败导致文件泄漏）
        file_data = []
        for f in files:
            # 校验扩展名
            suffix = Path(f.filename or "").suffix.lower()
            if suffix not in SUPPORTED_FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"文件格式不支持: {f.filename}，仅支持 {', '.join(SUPPORTED_FILE_EXTENSIONS)}",
                )

            # 读取文件内容并校验大小
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"文件过大: {f.filename}，单文件最大 20MB",
                )

            file_data.append((f, content, suffix))

        # 5. 校验通过，保存所有文件
        saved_files = []
        try:
            for f, content, suffix in file_data:
                import time
                import uuid
                safe_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
                file_path = UPLOAD_DIR / safe_name
                with open(file_path, "wb") as fp:
                    fp.write(content)

                saved_files.append({
                    "file_name": f.filename or safe_name,
                    "file_path": str(file_path),
                })
        except Exception as e:
            # 保存过程中出错，清理已保存的文件
            for sf in saved_files:
                try:
                    Path(sf["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            raise HTTPException(
                status_code=500,
                detail=f"文件保存失败: {str(e)}",
            )

        # 6. 创建任务
        task_id = task_manager.create_task(
            file_count=len(saved_files),
            priority=priority,
            callback_url=callback_url,
            api_key=api_key,
        )

        # 7. 记录文件关联
        for sf in saved_files:
            task_manager.add_file_result(
                task_id=task_id,
                file_name=sf["file_name"],
                file_path=sf["file_path"],
            )

        # 7. 启动后台处理
        worker = TaskWorker(task_manager, ocr_service)
        asyncio.create_task(worker.process(task_id, saved_files))

        # 8. 返回响应
        from datetime import datetime
        estimated_time = len(saved_files) * 12  # 预估每文件 12 秒

        return APIResponse(
            code=202,
            data={
                "task_id": task_id,
                "status": "pending",
                "submitted_at": datetime.now().isoformat(),
                "estimated_time": estimated_time,
                "file_count": len(saved_files),
                "priority": priority,
            },
            message="任务已提交",
        )

    return router
