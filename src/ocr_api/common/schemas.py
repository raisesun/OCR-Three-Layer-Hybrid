#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR API 服务 — 数据模型定义

统一的请求/响应格式，遵循 RESTful 规范。
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ========== 统一响应格式 ==========

class APIResponse(BaseModel):
    """统一 API 响应格式"""
    code: int = 200
    data: Optional[Any] = None
    message: str = "success"
    request_id: Optional[str] = None


class APIErrorDetail(BaseModel):
    """错误详情"""
    field: Optional[str] = None
    issue: Optional[str] = None


class APIErrorResponse(BaseModel):
    """统一错误响应格式"""
    code: int
    data: None = None
    message: str
    details: Optional[Dict[str, str]] = None
    request_id: Optional[str] = None


# ========== 健康检查 ==========

class HealthCheckData(BaseModel):
    """健康检查响应数据"""
    status: str = "healthy"
    version: str = "1.0.0"
    uptime: float = 0
    checks: Dict[str, str] = {}


# ========== 异步任务 ==========

class AsyncSubmitResponse(BaseModel):
    """异步任务提交响应"""
    task_id: str
    status: str = "pending"
    submitted_at: str
    estimated_time: Optional[int] = None
    file_count: int
    priority: str = "normal"


class TaskStatusResponse(BaseModel):
    """任务状态查询响应"""
    task_id: str
    status: str
    progress: int = 0
    processed: int = 0
    total: int = 0
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    estimated_remaining: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskCancelResponse(BaseModel):
    """任务取消响应"""
    task_id: str
    status: str
    processed: int
    total: int


# ========== 配额 ==========

class QuotaUsage(BaseModel):
    """单项配额使用情况"""
    used: int
    limit: int
    reset_at: Optional[str] = None


class QuotaResponse(BaseModel):
    """配额查询响应"""
    api_calls: QuotaUsage
    storage: Dict[str, float]
    async_tasks: Dict[str, int]


# ========== 文件处理结果 ==========

class FileResult(BaseModel):
    """单个文件的处理结果"""
    file_name: str
    status: str
    classification: Optional[Dict[str, Any]] = None
    extraction: Optional[Dict[str, Any]] = None
    timing: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskResultSummary(BaseModel):
    """任务结果汇总"""
    results: List[FileResult]
    summary: Dict[str, Any]
