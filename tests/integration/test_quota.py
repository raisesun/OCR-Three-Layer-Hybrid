#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配额查询集成测试

GET /api/v1/quota — 验证租户配额查询
"""

import pytest


class TestQuotaEndpoint:
    """GET /api/v1/quota 测试"""

    def test_quota_returns_200(self, client, auth_headers):
        """配额查询返回 200"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        assert resp.status_code == 200

    def test_quota_response_structure(self, client, auth_headers):
        """响应结构符合规范"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        quota = data["data"]
        assert "api_calls" in quota
        assert "storage" in quota
        assert "async_tasks" in quota

    def test_quota_api_calls_structure(self, client, auth_headers):
        """api_calls 包含 used/limit"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        api_calls = resp.json()["data"]["api_calls"]
        assert "used" in api_calls
        assert "limit" in api_calls
        assert isinstance(api_calls["used"], int)
        assert isinstance(api_calls["limit"], int)

    def test_quota_storage_structure(self, client, auth_headers):
        """storage 包含使用量信息"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        storage = resp.json()["data"]["storage"]
        assert isinstance(storage, dict)

    def test_quota_async_tasks_structure(self, client, auth_headers):
        """async_tasks 包含任务数量"""
        resp = client.get("/api/v1/quota", headers=auth_headers)
        async_tasks = resp.json()["data"]["async_tasks"]
        assert isinstance(async_tasks, dict)

    def test_quota_records_api_call(self, client, auth_headers, task_manager):
        """配额查询会记录 API 调用"""
        # 查询一次配额
        client.get("/api/v1/quota", headers=auth_headers)
        # 通过 task_manager 直接查询确认 API 调用已记录
        quota = task_manager.get_quota("test-key-12345")
        assert quota["api_calls"]["used"] >= 1

    def test_quota_requires_auth(self, client):
        """配额查询需要认证"""
        resp = client.get("/api/v1/quota")
        assert resp.status_code == 401
