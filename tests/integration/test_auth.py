#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认证集成测试

测试 API Key 认证的各种场景（成功/失败）
"""

import pytest
from unittest.mock import Mock
from fastapi import HTTPException


class TestAuthMissing:
    """缺少认证信息"""

    def test_no_auth_header_returns_401(self, client):
        """无 Authorization 头返回 401"""
        resp = client.get("/api/v1/quota")
        assert resp.status_code == 401

    def test_no_auth_error_message(self, client):
        """错误信息包含明确说明"""
        resp = client.get("/api/v1/quota")
        data = resp.json()
        assert "认证" in data.get("detail", {}).get("message", "") or \
               "Missing" in str(data)


class TestAuthWrongFormat:
    """认证格式错误"""

    def test_non_bearer_scheme(self, client):
        """非 Bearer 认证方案"""
        resp = client.get(
            "/api/v1/quota",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401

    def test_empty_bearer_token(self, client):
        """Bearer 后为空"""
        resp = client.get(
            "/api/v1/quota",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    def test_bearer_only_no_token(self, client):
        """只有 Bearer 没有 token"""
        resp = client.get(
            "/api/v1/quota",
            headers={"Authorization": "Bearer"},
        )
        assert resp.status_code == 401


class TestAuthInvalidKey:
    """无效 API Key"""

    def test_invalid_key_returns_401(self, client):
        """无效 Key 返回 401"""
        resp = client.get(
            "/api/v1/quota",
            headers={"Authorization": "Bearer invalid-key-xyz"},
        )
        assert resp.status_code == 401

    def test_invalid_key_error_detail(self, client):
        """无效 Key 错误包含详情"""
        resp = client.get(
            "/api/v1/quota",
            headers={"Authorization": "Bearer wrong-key"},
        )
        data = resp.json()
        detail = data.get("detail", {})
        # 应包含 Invalid 相关提示
        assert "Invalid" in str(detail) or "无效" in str(detail)


class TestAuthSuccess:
    """认证成功"""

    def test_valid_key_returns_200(self, client, auth_headers):
        """有效 Key 返回 200"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        assert resp.status_code == 200

    def test_valid_key_on_task_endpoint(self, client, auth_headers):
        """有效 Key 在 task 端点也通过"""
        resp = client.get(
            "/api/v1/task/nonexistent-task-id",
            headers=auth_headers,
        )
        # 404 是因为任务不存在，但认证已通过
        assert resp.status_code == 404


class TestRateLimit:
    """T5: 暴力破解防护（IP 级限流）"""

    def test_rate_limit_after_5_failures(self):
        """5 次失败后第 6 次返回 429（限流）"""
        from ocr_api.common.auth import APIKeyAuthenticator

        auth = APIKeyAuthenticator()
        auth._api_keys = {"valid-key"}

        mock_request = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"Authorization": "Bearer invalid"}

        # 5 次失败（401）
        for _ in range(5):
            with pytest.raises(HTTPException) as exc:
                auth.verify(mock_request)
            assert exc.value.status_code == 401

        # 第 6 次应 429（限流）
        with pytest.raises(HTTPException) as exc:
            auth.verify(mock_request)
        assert exc.value.status_code == 429

    def test_valid_key_not_limited(self):
        """有效 key 不受限流影响"""
        from ocr_api.common.auth import APIKeyAuthenticator

        auth = APIKeyAuthenticator()
        auth._api_keys = {"valid-key"}

        mock_request = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"Authorization": "Bearer valid-key"}

        for _ in range(10):
            result = auth.verify(mock_request)
            assert result == "valid-key"
