#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用服务组件（可复用）

提供与 OCR 业务无关的服务基础设施：
- auth: API Key 认证、鉴权、签名
- task_manager: 异步任务管理（SQLite 持久化）
- schemas: 统一请求/响应模型
"""

from .auth import APIKeyAuthenticator, PermissionChecker, RequestSigner
from .task_manager import TaskManager, TaskWorker
from .schemas import APIResponse, APIErrorResponse

__all__ = [
    "APIKeyAuthenticator",
    "PermissionChecker",
    "RequestSigner",
    "TaskManager",
    "TaskWorker",
    "APIResponse",
    "APIErrorResponse",
]
