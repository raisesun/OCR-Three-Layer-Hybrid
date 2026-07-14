#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务管理集成测试

GET  /api/v1/tasks                   — 列出任务（分页）
GET  /api/v1/task/{task_id}          — 查询任务状态
POST /api/v1/task/{task_id}/cancel   — 取消任务
"""

import pytest


class TestListTasks:
    """GET /api/v1/tasks 测试"""

    def test_list_tasks_requires_auth(self, client):
        """列出任务需要认证"""
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 401

    def test_list_tasks_returns_200(self, client, auth_headers):
        """列出任务返回 200"""
        resp = client.get("/api/v1/tasks", headers=auth_headers)
        assert resp.status_code == 200

    def test_list_tasks_response_structure(self, client, auth_headers):
        """列出任务响应包含必要字段"""
        resp = client.get("/api/v1/tasks", headers=auth_headers)
        data = resp.json()["data"]

        # 分页字段
        assert "tasks" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert "pages" in data

        # tasks 是列表
        assert isinstance(data["tasks"], list)

    def test_list_tasks_empty_when_no_tasks(self, client, auth_headers):
        """无任务时返回空列表"""
        resp = client.get("/api/v1/tasks", headers=auth_headers)
        data = resp.json()["data"]

        assert data["tasks"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pages"] == 0

    def test_list_tasks_after_submit(
        self, client, auth_headers, sample_image_path
    ):
        """提交任务后可在列表中查询到"""
        # 提交任务
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]

        # 列出任务
        resp = client.get("/api/v1/tasks", headers=auth_headers)
        data = resp.json()["data"]

        assert data["total"] >= 1
        task_ids = [t["task_id"] for t in data["tasks"]]
        assert task_id in task_ids

    def test_list_tasks_with_status_filter(
        self, client, auth_headers, sample_image_path
    ):
        """按状态过滤任务"""
        # 提交任务
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]

        # 取消任务
        client.post(f"/api/v1/task/{task_id}/cancel", headers=auth_headers)

        # 过滤 cancelled 状态
        resp = client.get(
            "/api/v1/tasks?status=cancelled",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        task_ids = [t["task_id"] for t in data["tasks"]]
        assert task_id in task_ids

        # 过滤 pending 状态（不应包含已取消的任务）
        resp = client.get(
            "/api/v1/tasks?status=pending",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        task_ids = [t["task_id"] for t in data["tasks"]]
        assert task_id not in task_ids

    def test_list_tasks_pagination(
        self, client, auth_headers, sample_image_path
    ):
        """分页参数生效"""
        # 提交多个任务
        task_ids = []
        for i in range(3):
            with open(sample_image_path, "rb") as f:
                resp = client.post(
                    "/api/v1/ocr/async",
                    headers=auth_headers,
                    files={"files": (f"test{i}.jpg", f, "image/jpeg")},
                )
            task_ids.append(resp.json()["data"]["task_id"])

        # 查询第 1 页，每页 2 个
        resp = client.get(
            "/api/v1/tasks?page=1&size=2",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        assert len(data["tasks"]) == 2
        assert data["page"] == 1
        assert data["size"] == 2
        assert data["total"] >= 3
        assert data["pages"] >= 2

        # 查询第 2 页
        resp = client.get(
            "/api/v1/tasks?page=2&size=2",
            headers=auth_headers,
        )
        data = resp.json()["data"]
        assert len(data["tasks"]) >= 1
        assert data["page"] == 2

    def test_list_tasks_isolation_between_tenants(
        self, client, sample_image_path
    ):
        """不同租户的任务相互隔离"""
        # 租户 A 提交任务
        headers_a = {"Authorization": "Bearer test-key-12345"}
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=headers_a,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id_a = resp.json()["data"]["task_id"]

        # 租户 A 查询列表
        resp = client.get("/api/v1/tasks", headers=headers_a)
        data_a = resp.json()["data"]
        task_ids_a = [t["task_id"] for t in data_a["tasks"]]
        assert task_id_a in task_ids_a


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
