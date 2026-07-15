#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试路由 — Demo / 内部调试功能

仅在 DEBUG=true 时加载，包含：
- 主页 HTML（Demo UI）
- 单图处理（传路径）
- 批量处理（按 case_id）
- 目录批量处理
- 基线数据管理
- 统计面板
- 文件上传
- 静态文件服务

**注意**: 这些接口不应暴露给外部用户。
"""

import time
import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ========== 请求模型 ==========

class ProcessRequest(BaseModel):
    image_path: str
    ocr_text: str = ""


class BatchRequest(BaseModel):
    case_id: str


class DirectoryBatchRequest(BaseModel):
    dir_path: str


def create_debug_routes(
    ocr_service,
    baseline_service,
    demo_dir: Path,
    upload_dir: Path,
    task_manager=None,
) -> tuple:
    """创建调试路由

    Args:
        ocr_service: OCRService 实例
        baseline_service: BaselineService 实例
        demo_dir: demo 目录路径
        upload_dir: 上传目录路径
        task_manager: TaskManager 实例（可选，用于异步任务管理）

    Returns:
        (router, static_mounts)
        static_mounts: [(path, directory, name), ...] 需要挂载的静态文件
    """
    router = APIRouter(tags=["Debug"])
    TEMPLATES_DIR = demo_dir / "templates"

    # 基线图片目录
    SAMPLE_OCR_DIR = Path("/Users/dongsun/Github/sample-OCR")
    SAMPLE_OCR_BASE = str(SAMPLE_OCR_DIR)

    # 允许访问的目录白名单（resolved 路径）
    _allowed_bases = [
        Path(SAMPLE_OCR_BASE).resolve(),
        Path(upload_dir).resolve(),
    ]

    def _validate_path(raw_path: str, *, must_exist: bool = True) -> Path:
        """校验路径是否在允许的目录内，防止路径遍历

        Args:
            raw_path: 用户提供的路径
            must_exist: 是否要求路径必须存在

        Returns:
            解析后的 Path 对象

        Raises:
            HTTPException: 路径不在白名单内或不存在
        """
        resolved = Path(raw_path).resolve()
        if not any(
            str(resolved).startswith(str(base))
            for base in _allowed_bases
        ):
            raise HTTPException(
                status_code=403,
                detail=f"路径不允许访问: {raw_path}（仅限 sample-OCR 和 uploads 目录）",
            )
        if must_exist and not resolved.exists():
            raise HTTPException(status_code=404, detail=f"路径不存在: {raw_path}")
        return resolved

    # ========== 主页 ==========

    @router.get("/", response_class=HTMLResponse)
    async def index():
        """主页 — Demo UI"""
        html_path = TEMPLATES_DIR / "index.html"
        if html_path.exists():
            return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
        return HTMLResponse(content="<h1>OCR Demo</h1><p>Templates not found.</p>")

    # ========== 单图处理 ==========

    @router.post("/api/process")
    async def process_single(req: ProcessRequest):
        """处理单张图片（传路径，非文件上传）"""
        image_path = _validate_path(req.image_path)
        try:
            result = await asyncio.to_thread(ocr_service.process_image, str(image_path), req.ocr_text)
            return {"success": True, "data": result}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ========== 批量处理 ==========

    @router.post("/api/process/batch")
    async def process_batch(req: BatchRequest):
        """批量处理一个业务 Case"""
        case = baseline_service.get_case(req.case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"业务不存在: {req.case_id}")

        images = case["images"]
        start_time = time.time()
        results = await asyncio.to_thread(ocr_service.process_batch, images)
        total_time = time.time() - start_time

        correct = sum(1 for r in results if r.get("is_correct", False))
        total = len(results)

        return {
            "success": True,
            "data": {
                "case_id": req.case_id,
                "results": results,
                "stats": {
                    "total": total,
                    "correct": correct,
                    "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
                    "total_time_s": round(total_time, 2),
                    "avg_time_ms": round(total_time / total * 1000, 1) if total > 0 else 0,
                },
            },
        }

    # ========== 目录扫描与批量处理 ==========

    @router.get("/api/directories")
    async def list_directories(parent: str = ""):
        """列出子目录（用于目录选择器）"""
        # 安全检查：限制路径必须在 SAMPLE_OCR_BASE 内，防止路径遍历攻击
        base_dir = SAMPLE_OCR_BASE if not parent else parent
        base_path = Path(base_dir).resolve()
        sample_base_resolved = Path(SAMPLE_OCR_BASE).resolve()

        # 确保请求的路径在允许的基目录内
        if not str(base_path).startswith(str(sample_base_resolved)):
            raise HTTPException(
                status_code=403,
                detail=f"路径不允许访问: {base_dir}（必须在 {SAMPLE_OCR_BASE} 内）",
            )

        if not base_path.exists():
            raise HTTPException(status_code=404, detail=f"目录不存在: {base_dir}")

        dirs = []
        for item in sorted(base_path.iterdir()):
            if item.is_dir() and not item.name.startswith('.'):
                img_count = sum(
                    1 for f in item.iterdir()
                    if f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
                )
                dirs.append({
                    "path": str(item),
                    "name": item.name,
                    "image_count": img_count,
                    "has_subdirs": any(
                        d.is_dir() and not d.name.startswith('.')
                        for d in item.iterdir()
                    ),
                })

        return {
            "success": True,
            "data": {
                "current_path": str(base_path),
                "parent_path": str(base_path.parent) if str(base_path) != str(sample_base_resolved) else "",
                "directories": dirs,
            },
        }

    @router.post("/api/process/batch/directory")
    async def process_batch_directory(req: DirectoryBatchRequest):
        """批量处理目录下所有图片"""
        dir_path = _validate_path(req.dir_path, must_exist=True)
        if not dir_path.is_dir():
            raise HTTPException(status_code=400, detail=f"路径不是目录: {req.dir_path}")
        result = await asyncio.to_thread(ocr_service.process_directory, str(dir_path))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return {"success": True, "data": {"dir_path": str(dir_path), **result}}

    # ========== 基线数据 ==========

    @router.get("/api/baseline/cases")
    async def list_cases():
        """获取业务列表"""
        cases = baseline_service.list_cases()
        stats = baseline_service.get_stats()
        return {"success": True, "data": {"cases": cases, "stats": stats}}

    @router.get("/api/baseline/cases/{case_id}")
    async def get_case(case_id: str):
        """获取业务详情"""
        case = baseline_service.get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"业务不存在: {case_id}")
        return {"success": True, "data": case}

    @router.post("/api/baseline/compare")
    async def baseline_compare():
        """全量基线对比"""
        all_images = baseline_service.get_all_images()
        start_time = time.time()
        results = await asyncio.to_thread(ocr_service.process_batch, all_images)
        total_time = time.time() - start_time

        total = len(results)
        correct = sum(1 for r in results if r.get("is_correct", False))
        errors = [r for r in results if not r.get("is_correct", False)]

        type_stats = {}
        layer_stats = {"rule": 0, "vlm": 0, "llm": 0}
        for r in results:
            actual = r.get("classification", {}).get("doc_type", "未知")
            expected = r.get("expected_type", "")
            layer = r.get("extraction", {}).get("layer", "none")
            if expected not in type_stats:
                type_stats[expected] = {"total": 0, "correct": 0}
            type_stats[expected]["total"] += 1
            if r.get("is_correct", False):
                type_stats[expected]["correct"] += 1
            if layer in layer_stats:
                layer_stats[layer] += 1

        type_accuracy = {}
        for t, s in type_stats.items():
            type_accuracy[t] = {
                "total": s["total"],
                "correct": s["correct"],
                "accuracy": round(s["correct"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            }

        return {
            "success": True,
            "data": {
                "total": total,
                "correct": correct,
                "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
                "total_time_s": round(total_time, 2),
                "avg_time_ms": round(total_time / total * 1000, 1) if total > 0 else 0,
                "type_accuracy": type_accuracy,
                "layer_stats": layer_stats,
                "errors": [
                    {
                        "file_name": e.get("file_name", ""),
                        "expected": e.get("expected_type", ""),
                        "actual": e.get("classification", {}).get("doc_type", ""),
                        "page_status": e.get("page_status", ""),
                        "route": e.get("classification", {}).get("route", ""),
                    }
                    for e in errors
                ],
            },
        }

    # ========== 统计面板 ==========

    @router.get("/api/stats/dashboard")
    async def stats_dashboard():
        """统计面板数据"""
        baseline_stats = baseline_service.get_stats()
        all_images = baseline_service.get_all_images()
        start_time = time.time()
        results = await asyncio.to_thread(ocr_service.process_batch, all_images)
        total_time = time.time() - start_time

        total = len(results)
        correct = sum(1 for r in results if r.get("is_correct", False))
        vlm_calls = sum(
            1 for r in results
            if r.get("classification", {}).get("route") in ("vlm_fallback_required", "vlm_classification")
        )

        type_dist = {}
        layer_dist = {"rule": 0, "vlm": 0, "llm": 0}
        timing_list = []
        for r in results:
            actual = r.get("classification", {}).get("doc_type", "未知")
            layer = r.get("extraction", {}).get("layer", "none")
            t = r.get("timing", {}).get("total_ms", 0)
            type_dist[actual] = type_dist.get(actual, 0) + 1
            if layer in layer_dist:
                layer_dist[layer] += 1
            if t > 0:
                timing_list.append(t)

        timing_buckets = {"0-10ms": 0, "10-50ms": 0, "50-100ms": 0, "100-500ms": 0, "500ms+": 0}
        for t in timing_list:
            if t <= 10: timing_buckets["0-10ms"] += 1
            elif t <= 50: timing_buckets["10-50ms"] += 1
            elif t <= 100: timing_buckets["50-100ms"] += 1
            elif t <= 500: timing_buckets["100-500ms"] += 1
            else: timing_buckets["500ms+"] += 1

        return {
            "success": True,
            "data": {
                "kpi": {
                    "total_images": total,
                    "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
                    "avg_time_ms": round(sum(timing_list) / len(timing_list), 1) if timing_list else 0,
                    "vlm_call_rate": round(vlm_calls / total * 100, 1) if total > 0 else 0,
                },
                "type_distribution": type_dist,
                "layer_distribution": layer_dist,
                "timing_distribution": timing_buckets,
                "baseline_stats": baseline_stats,
            },
        }

    # ========== 图片上传 ==========

    @router.post("/api/upload")
    async def upload_image(file: UploadFile = File(...)):
        """上传图片"""
        suffix = Path(file.filename).suffix if file.filename else ".jpg"
        safe_name = f"upload_{int(time.time())}{suffix}"
        file_path = upload_dir / safe_name
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        return {
            "success": True,
            "data": {
                "file_path": str(file_path),
                "file_name": safe_name,
                "url": f"/uploads/{safe_name}",
            },
        }

    # ========== 异步任务管理（Debug 模式无需认证） ==========

    @router.post("/api/debug/ocr/async")
    async def debug_submit_async_task(
        files: list[UploadFile] = File(..., description="图片/PDF 文件列表"),
        callback_url: Optional[str] = None,
        priority: str = "normal",
        enable_vlm: bool = True,
    ):
        """提交异步任务（Debug 模式，无需认证）"""
        if not task_manager:
            raise HTTPException(status_code=501, detail="TaskManager 未初始化")

        import uuid
        saved_files = []
        for f in files:
            suffix = Path(f.filename or "").suffix.lower()
            safe_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{suffix}"
            file_path = upload_dir / safe_name
            content = await f.read()
            with open(file_path, "wb") as fp:
                fp.write(content)
            saved_files.append({
                "file_name": f.filename or safe_name,
                "file_path": str(file_path),
            })

        # 使用固定的 debug API key
        debug_api_key = "debug-demo-key"
        task_id = task_manager.create_task(
            file_count=len(saved_files),
            priority=priority,
            callback_url=callback_url,
            api_key=debug_api_key,
        )

        for sf in saved_files:
            task_manager.add_file_result(
                task_id=task_id,
                file_name=sf["file_name"],
                file_path=sf["file_path"],
            )

        from ocr_api.common.task_manager import TaskWorker
        worker = TaskWorker(task_manager, ocr_service)
        asyncio.create_task(worker.process(task_id, saved_files))

        from datetime import datetime
        return {
            "code": 202,
            "data": {
                "task_id": task_id,
                "status": "pending",
                "submitted_at": datetime.now().isoformat(),
                "file_count": len(saved_files),
                "priority": priority,
            },
            "message": "任务已提交",
        }

    @router.get("/api/debug/tasks")
    async def debug_list_tasks(
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        size: int = Query(10, ge=1, le=100),
    ):
        """列出任务（Debug 模式，无需认证）"""
        if not task_manager:
            raise HTTPException(status_code=501, detail="TaskManager 未初始化")
        debug_api_key = "debug-demo-key"
        result = task_manager.list_tasks(
            api_key=debug_api_key,
            status_filter=status,
            page=page,
            size=size,
        )
        return {"code": 200, "data": result, "message": "success"}

    @router.get("/api/debug/task/{task_id}")
    async def debug_get_task(task_id: str):
        """查询任务状态（Debug 模式，无需认证）"""
        if not task_manager:
            raise HTTPException(status_code=501, detail="TaskManager 未初始化")
        status = task_manager.get_task_status(task_id)
        if not status:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        return {"code": 200, "data": status, "message": "success"}

    @router.post("/api/debug/task/{task_id}/cancel")
    async def debug_cancel_task(task_id: str):
        """取消任务（Debug 模式，无需认证）"""
        if not task_manager:
            raise HTTPException(status_code=501, detail="TaskManager 未初始化")
        task = task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
        success = task_manager.mark_cancelled(task_id)
        if not success:
            raise HTTPException(status_code=400, detail="任务状态不允许取消")
        return {
            "code": 200,
            "data": {
                "task_id": task_id,
                "status": "cancelled",
                "processed": task["processed_count"],
                "total": task["file_count"],
            },
            "message": "任务已取消",
        }

    # ========== 日志 API ==========

    @router.get("/api/debug/logs")
    async def get_logs(
        level: Optional[str] = Query(None, description="日志级别过滤 (INFO/WARNING/ERROR)"),
        logger: Optional[str] = Query(None, description="Logger名称过滤"),
        limit: int = Query(100, ge=1, le=500, description="返回条数"),
    ):
        """获取内存日志缓冲区（仅 DEBUG 模式）"""
        from ocr_api.common.memory_log import log_buffer
        logs = log_buffer.get_logs(level=level, logger=logger, limit=limit)
        return {"code": 200, "data": {"logs": logs, "total": len(logs)}, "message": "success"}

    @router.post("/api/debug/logs/clear")
    async def clear_logs():
        """清空日志缓冲区"""
        from ocr_api.common.memory_log import log_buffer
        log_buffer.clear()
        return {"code": 200, "data": None, "message": "日志已清空"}

    # ========== 静态文件挂载信息 ==========

    static_mounts = [
        ("/static", str(demo_dir / "static"), "static"),
    ]
    if SAMPLE_OCR_DIR.exists():
        static_mounts.append(("/sample-images", str(SAMPLE_OCR_DIR), "sample_images"))
    static_mounts.append(("/uploads", str(upload_dir), "uploads"))

    return router, static_mounts
