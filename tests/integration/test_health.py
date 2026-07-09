#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
健康检查集成测试

GET /health — 验证服务状态端点
"""

import pytest


class TestHealthEndpoint:
    """GET /health 测试"""

    def test_health_returns_200(self, client):
        """健康检查返回 200"""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_structure(self, client):
        """响应结构符合 APIResponse 规范"""
        resp = client.get("/health")
        data = resp.json()
        assert data["code"] == 200
        assert data["message"] == "success"
        assert "data" in data

    def test_health_data_fields(self, client):
        """健康检查数据包含必要字段"""
        resp = client.get("/health")
        health_data = resp.json()["data"]
        assert "status" in health_data
        assert "version" in health_data
        assert "uptime" in health_data
        assert "checks" in health_data

    def test_health_status_values(self, client):
        """status 为 healthy 或 degraded"""
        resp = client.get("/health")
        status = resp.json()["data"]["status"]
        assert status in ("healthy", "degraded")

    def test_health_no_auth_required(self, client):
        """健康检查不需要认证"""
        # 不带 Authorization 头
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_version_is_string(self, client):
        """version 是字符串"""
        resp = client.get("/health")
        version = resp.json()["data"]["version"]
        assert isinstance(version, str)
        assert len(version) > 0

    def test_health_uptime_is_positive(self, client):
        """uptime 为正数"""
        resp = client.get("/health")
        uptime = resp.json()["data"]["uptime"]
        assert isinstance(uptime, (int, float))
        assert uptime >= 0

    def test_health_checks_is_dict(self, client):
        """checks 是字典"""
        resp = client.get("/health")
        checks = resp.json()["data"]["checks"]
        assert isinstance(checks, dict)
