#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR三层混合架构 — 演示服务

启动: python server.py
访问: http://localhost:8888
"""

import sys
import time
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional, List

# 添加路径
DEMO_DIR = Path(__file__).parent
PROJECT_DIR = DEMO_DIR.parent
sys.path.insert(0, str(DEMO_DIR))
sys.path.insert(0, str(PROJECT_DIR / "src"))

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from ocr_service import OCRService
from baseline_service import BaselineService
from ocr_three_layer_hybrid.service import setup_logging


# ========== 初始化日志 ==========

setup_logging(level="INFO")

# ========== 初始化服务 ==========

ocr_service = OCRService(enable_vlm_fallback=True)
baseline_service = BaselineService()

# 临时上传目录
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="ocr_demo_"))

# ========== FastAPI 应用 ==========

app = FastAPI(title="OCR三层混合架构演示", version="1.0.0")

# 请求日志中间件（记录 API 调用耗时）
server_logger = logging.getLogger("ocr_three_layer_hybrid.server")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed_ms = round((time.time() - start) * 1000, 1)
    path = request.url.path
    # 只记录 API 请求，跳过静态资源
    if path.startswith("/api/"):
        server_logger.info(
            "[API] %s %s | %d | %.1fms",
            request.method, path, response.status_code, elapsed_ms,
        )
    return response

# 静态文件
app.mount("/static", StaticFiles(directory=str(DEMO_DIR / "static")), name="static")

# 基线图片目录（提供图片预览）
SAMPLE_OCR_DIR = Path("/Users/dongsun/Github/sample-OCR")
if SAMPLE_OCR_DIR.exists():
    app.mount("/sample-images", StaticFiles(directory=str(SAMPLE_OCR_DIR)), name="sample_images")

# 上传文件目录
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# 模板目录
TEMPLATES_DIR = DEMO_DIR / "templates"


# ========== 请求/响应模型 ==========

class ProcessRequest(BaseModel):
    image_path: str
    ocr_text: str = ""


class BatchRequest(BaseModel):
    case_id: str


class DirectoryBatchRequest(BaseModel):
    dir_path: str


# ========== 页面路由 ==========

@app.get("/", response_class=HTMLResponse)
async def index():
    """主页"""
    html_path = TEMPLATES_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ========== API: 单图处理 ==========

@app.post("/api/process")
async def process_single(req: ProcessRequest):
    """处理单张图片"""
    if not Path(req.image_path).exists():
        raise HTTPException(status_code=404, detail=f"图片不存在: {req.image_path}")

    try:
        result = await asyncio.to_thread(ocr_service.process_image, req.image_path, req.ocr_text)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ========== API: 批量处理 ==========

@app.post("/api/process/batch")
async def process_batch(req: BatchRequest):
    """批量处理一个业务Case的所有图片"""
    case = baseline_service.get_case(req.case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"业务不存在: {req.case_id}")

    images = case["images"]
    start_time = time.time()
    # 在线程池中运行，避免阻塞事件循环
    results = await asyncio.to_thread(ocr_service.process_batch, images)
    total_time = time.time() - start_time

    # 统计
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


# ========== API: 目录扫描与批量处理 ==========

SAMPLE_OCR_BASE = "/Users/dongsun/Github/sample-OCR"


@app.get("/api/directories")
async def list_directories(parent: str = ""):
    """列出指定父目录下的子目录（用于目录选择器）"""
    base = parent if parent else SAMPLE_OCR_BASE
    base_path = Path(base)
    if not base_path.exists():
        return {"success": False, "error": f"目录不存在: {base}"}

    dirs = []
    for item in sorted(base_path.iterdir()):
        if item.is_dir() and not item.name.startswith('.'):
            # 统计图片数量
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
            "parent_path": str(base_path.parent) if str(base_path) != "/" else "",
            "directories": dirs,
        },
    }


@app.post("/api/process/batch/directory")
async def process_batch_directory(req: DirectoryBatchRequest):
    """批量处理指定目录下的所有图片（OCR→分类→提取）"""
    result = await asyncio.to_thread(ocr_service.process_directory, req.dir_path)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return {
        "success": True,
        "data": {
            "dir_path": req.dir_path,
            **result,
        },
    }


# ========== API: 基线数据 ==========

@app.get("/api/baseline/cases")
async def list_cases():
    """获取业务列表"""
    cases = baseline_service.list_cases()
    stats = baseline_service.get_stats()
    return {"success": True, "data": {"cases": cases, "stats": stats}}


@app.get("/api/baseline/cases/{case_id}")
async def get_case(case_id: str):
    """获取业务详情"""
    case = baseline_service.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"业务不存在: {case_id}")
    return {"success": True, "data": case}


# ========== API: 基线对比 ==========

@app.post("/api/baseline/compare")
async def baseline_compare():
    """全量基线对比"""
    all_images = baseline_service.get_all_images()
    start_time = time.time()
    results = await asyncio.to_thread(ocr_service.process_batch, all_images)
    total_time = time.time() - start_time

    # 统计
    total = len(results)
    correct = sum(1 for r in results if r.get("is_correct", False))
    errors = [r for r in results if not r.get("is_correct", False)]

    # 按类型统计
    type_stats = {}
    layer_stats = {"rule": 0, "vlm": 0, "llm": 0}

    for r in results:
        actual = r.get("classification", {}).get("doc_type", "未知")
        expected = r.get("expected_type", "")
        layer = r.get("extraction", {}).get("layer", "none")

        # 类型统计
        if expected not in type_stats:
            type_stats[expected] = {"total": 0, "correct": 0}
        type_stats[expected]["total"] += 1
        if r.get("is_correct", False):
            type_stats[expected]["correct"] += 1

        # 层统计
        if layer in layer_stats:
            layer_stats[layer] += 1

    # 各类型准确率
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


# ========== API: 统计面板 ==========

@app.get("/api/stats/dashboard")
async def stats_dashboard():
    """统计面板数据"""
    baseline_stats = baseline_service.get_stats()
    all_images = baseline_service.get_all_images()

    # 运行一次完整测试获取统计
    start_time = time.time()
    results = await asyncio.to_thread(ocr_service.process_batch, all_images)
    total_time = time.time() - start_time

    total = len(results)
    correct = sum(1 for r in results if r.get("is_correct", False))
    vlm_calls = sum(
        1 for r in results
        if r.get("classification", {}).get("route") in ("vlm_fallback_required", "vlm_classification")
    )

    # 类型分布
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

    # 耗时分布
    timing_buckets = {"0-10ms": 0, "10-50ms": 0, "50-100ms": 0, "100-500ms": 0, "500ms+": 0}
    for t in timing_list:
        if t <= 10:
            timing_buckets["0-10ms"] += 1
        elif t <= 50:
            timing_buckets["10-50ms"] += 1
        elif t <= 100:
            timing_buckets["50-100ms"] += 1
        elif t <= 500:
            timing_buckets["100-500ms"] += 1
        else:
            timing_buckets["500ms+"] += 1

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


# ========== API: 图片上传 ==========

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """上传图片"""
    # 生成安全的文件名
    suffix = Path(file.filename).suffix if file.filename else ".jpg"
    safe_name = f"upload_{int(time.time())}{suffix}"
    file_path = UPLOAD_DIR / safe_name

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


# ========== 启动 ==========

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("OCR三层混合架构 — 演示服务")
    print("=" * 50)
    print(f"访问地址: http://localhost:8888")
    print(f"基线数据: {baseline_service.baseline_file}")
    print(f"上传目录: {UPLOAD_DIR}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8888)
