#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务管理集成测试

GET  /api/v1/task/{task_id}          — 查询任务状态
POST /api/v1/task/{task_id}/cancel   — 取消任务
"""

import pytest


class TestTaskStatus:
    """GET /api/v1/task/{task_id} 测试"""

    def test_nonexistent_task_returns_404(self, client, auth_headers):
        """不存在的任务返回 404"""
        resp = client.get(
            "/api/v1/task/task_nonexistent",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_pending_task_status(self, client, auth_headers, sample_image_path):
        """新创建的任务状态为 pending"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]

        # 查询任务状态
        resp = client.get(f"/api/v1/task/{task_id}", headers=auth_headers)
        assert resp.status_code == 200

        data = resp.json()["data"]
        assert data["task_id"] == task_id
        assert data["status"] in ("pending", "processing")
        assert data["total"] == 1

    def test_task_status_has_required_fields(
        self, client, auth_headers, sample_image_path
    ):
        """任务状态包含所有必要字段"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]
        resp = client.get(f"/api/v1/task/{task_id}", headers=auth_headers)
        data = resp.json()["data"]

        # 必要字段
        assert "task_id" in data
        assert "status" in data
        assert "progress" in data
        assert "processed" in data
        assert "total" in data
        assert "submitted_at" in data

    def test_task_status_progress_is_int(
        self, client, auth_headers, sample_image_path
    ):
        """progress 为整数百分比"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]
        resp = client.get(f"/api/v1/task/{task_id}", headers=auth_headers)
        progress = resp.json()["data"]["progress"]
        assert isinstance(progress, int)
        assert 0 <= progress <= 100

    def test_task_status_requires_auth(self, client, sample_image_path):
        """任务状态查询需要认证"""
        resp = client.get("/api/v1/task/some-task-id")
        assert resp.status_code == 401


class TestTaskCancel:
    """POST /api/v1/task/{task_id}/cancel 测试"""

    def test_cancel_nonexistent_returns_404(self, client, auth_headers):
        """取消不存在的任务返回 404"""
        resp = client.post(
            "/api/v1/task/task_nonexistent/cancel",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_cancel_pending_task(self, client, auth_headers, sample_image_path):
        """取消 pending 状态的任务"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]

        # 取消任务
        resp = client.post(
            f"/api/v1/task/{task_id}/cancel",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "cancelled"
        assert data["task_id"] == task_id

    def test_cancel_response_has_counts(
        self, client, auth_headers, sample_image_path
    ):
        """取消响应包含 processed/total 计数"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]
        resp = client.post(
            f"/api/v1/task/{task_id}/cancel",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        assert "processed" in data
        assert "total" in data
        assert isinstance(data["processed"], int)
        assert isinstance(data["total"], int)

    def test_cancel_task_status_reflects_cancelled(
        self, client, auth_headers, sample_image_path
    ):
        """取消后查询状态应为 cancelled"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]

        # 取消
        client.post(f"/api/v1/task/{task_id}/cancel", headers=auth_headers)

        # 查询状态
        resp = client.get(f"/api/v1/task/{task_id}", headers=auth_headers)
        assert resp.json()["data"]["status"] == "cancelled"

    def test_cancel_requires_auth(self, client, sample_image_path):
        """取消任务需要认证"""
        resp = client.post("/api/v1/task/some-task-id/cancel")
        assert resp.status_code == 401
