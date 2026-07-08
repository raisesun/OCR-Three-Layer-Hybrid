#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR API 服务包

提供可复用的 API 服务基础设施和 OCR API 实现。

子包:
    common  — 通用服务组件（认证、任务管理、响应模型），可独立复用
    ocr     — OCR API 业务层（路由、服务入口、Demo UI）

复用示例:
    from ocr_api.common.auth import APIKeyAuthenticator
    from ocr_api.common.task_manager import TaskManager
"""

__version__ = "1.1.0"
