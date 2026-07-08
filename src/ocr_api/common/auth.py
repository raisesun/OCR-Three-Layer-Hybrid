#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR API 服务 — 认证模块

支持多种认证方式：
1. API Key 认证（默认）
2. 预留扩展：签名认证、OAuth2 等

认证逻辑与业务逻辑解耦，方便其他项目复用。
"""

import os
import logging
from typing import Optional
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class APIKeyAuthenticator:
    """API Key 认证器

    从环境变量加载允许的 Key 列表：
        OCR_API_KEYS=key1,key2,key3

    使用方式：
        auth = APIKeyAuthenticator()
        # 在路由中调用
        api_key = auth.verify(request)
    """

    def __init__(self, api_keys_env: str = "OCR_API_KEYS"):
        keys_str = os.getenv(api_keys_env, "")
        if keys_str:
            self._api_keys = {k.strip() for k in keys_str.split(",") if k.strip()}
        else:
            self._api_keys = set()
        logger.info(f"[Auth] 已加载 {len(self._api_keys)} 个 API Key")

    def verify(self, request: Request) -> str:
        """验证 API Key，返回有效的 Key

        Raises:
            HTTPException: 认证失败时抛出 401
        """
        auth_header = request.headers.get("Authorization", "")

        if not auth_header:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": 401,
                    "message": "缺少认证信息",
                    "details": {"field": "Authorization", "issue": "Missing API Key"},
                },
            )

        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": 401,
                    "message": "认证格式错误",
                    "details": {"field": "Authorization", "issue": "Expected 'Bearer {key}'"},
                },
            )

        api_key = auth_header[7:].strip()

        if not api_key:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": 401,
                    "message": "API Key 为空",
                    "details": {"field": "Authorization", "issue": "Empty API Key"},
                },
            )

        if api_key not in self._api_keys:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": 401,
                    "message": "API Key 无效",
                    "details": {"field": "Authorization", "issue": "Invalid API Key"},
                },
            )

        return api_key

    def is_enabled(self) -> bool:
        """是否启用了认证"""
        return len(self._api_keys) > 0


# ========== 鉴权（权限检查） ==========

class PermissionChecker:
    """权限检查器

    预留扩展：支持基于角色的权限控制
    当前版本不做权限检查，所有有效 API Key 都有完整权限。
    """

    def __init__(self):
        pass

    def check(self, api_key: str, permission: str) -> bool:
        """检查 API Key 是否有指定权限

        Args:
            api_key: 已验证的 API Key
            permission: 权限名称（如 'ocr.read', 'task.read'）

        Returns:
            True 表示有权限
        """
        # 当前版本：所有有效 Key 都有完整权限
        return True


# ========== 参数签名（预留） ==========

class RequestSigner:
    """请求签名验证器

    预留扩展：支持 HMAC 签名验证
    当前版本不实现签名验证。
    """

    def __init__(self, secret_key: Optional[str] = None):
        self._secret_key = secret_key or os.getenv("OCR_SIGN_SECRET", "")

    def verify(self, request: Request) -> bool:
        """验证请求签名

        Returns:
            True 表示签名有效
        """
        # 当前版本：不验证签名
        if not self._secret_key:
            return True

        # 预留：HMAC 签名验证逻辑
        # signature = request.headers.get("X-Signature", "")
        # timestamp = request.headers.get("X-Timestamp", "")
        # ... 验证逻辑 ...
        return True


# ========== 认证依赖（FastAPI Depends） ==========

async def verify_api_key(request: Request) -> str:
    """FastAPI 依赖注入：验证 API Key

    用法：
        @router.get("/api/v1/example")
        async def example(api_key: str = Depends(verify_api_key)):
            ...
    """
    auth = APIKeyAuthenticator()
    return auth.verify(request)
