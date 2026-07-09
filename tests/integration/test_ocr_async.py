#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步 OCR 提交集成测试

POST /api/v1/ocr/async — 文件上传 + 任务创建
"""

import pytest


class TestOCRAsyncUpload:
    """POST /api/v1/ocr/async — 文件上传测试"""

    def test_submit_single_file(self, client, auth_headers, sample_image_path):
        """提交单个文件"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == "pending"
        assert data["file_count"] == 1
        assert "task_id" in data
        assert data["task_id"].startswith("task_")

    def test_submit_multiple_files(
        self, client, auth_headers, sample_image_path, sample_contract_path
    ):
        """提交多个文件"""
        with open(sample_image_path, "rb") as f1, \
             open(sample_contract_path, "rb") as f2:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files=[
                    ("files", ("property.jpg", f1, "image/jpeg")),
                    ("files", ("contract.jpeg", f2, "image/jpeg")),
                ],
            )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["file_count"] == 2

    def test_task_created_in_db(
        self, client, auth_headers, sample_image_path, task_manager
    ):
        """任务已写入数据库"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        task_id = resp.json()["data"]["task_id"]
        task = task_manager.get_task(task_id)
        assert task is not None
        assert task["status"] in ("pending", "processing")
        assert task["file_count"] == 1

    def test_file_saved_to_upload_dir(
        self, client, auth_headers, sample_image_path, tmp_upload_dir
    ):
        """文件保存到上传目录"""
        with open(sample_image_path, "rb") as f:
            client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        # 上传目录应有文件
        saved_files = list(tmp_upload_dir.iterdir())
        assert len(saved_files) == 1
        assert saved_files[0].suffix == ".jpg"

    def test_response_includes_estimated_time(
        self, client, auth_headers, sample_image_path
    ):
        """响应包含预估时间"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        data = resp.json()["data"]
        assert "estimated_time" in data
        assert isinstance(data["estimated_time"], int)
        assert data["estimated_time"] > 0

    def test_priority_normal_default(
        self, client, auth_headers, sample_image_path
    ):
        """默认优先级为 normal"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        data = resp.json()["data"]
        assert data["priority"] == "normal"

    def test_priority_urgent(self, client, auth_headers, sample_image_path):
        """指定 urgent 优先级"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.jpg", f, "image/jpeg")},
                data={"priority": "urgent"},
            )
        data = resp.json()["data"]
        assert data["priority"] == "urgent"


class TestOCRAsyncValidation:
    """POST /api/v1/ocr/async — 文件校验测试"""

    def test_unsupported_format_returns_400(
        self, client, auth_headers, tmp_path
    ):
        """不支持的文件格式返回 400"""
        bad_file = tmp_path / "test.txt"
        bad_file.write_text("not an image")
        with open(bad_file, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": ("test.txt", f, "text/plain")},
            )
        assert resp.status_code == 400
        assert "不支持" in resp.json().get("detail", "")

    def test_no_files_returns_422(self, client, auth_headers):
        """未上传文件返回 422 (FastAPI 校验)"""
        resp = client.post(
            "/api/v1/ocr/async",
            headers=auth_headers,
            files=[],
        )
        # FastAPI 对缺少必填文件参数返回 422（非 400）
        assert resp.status_code == 422

    def test_no_auth_returns_401(self, client, sample_image_path):
        """未认证返回 401"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        assert resp.status_code == 401

    def test_invalid_api_key_returns_401(
        self, client, sample_image_path
    ):
        """无效 API Key 返回 401"""
        with open(sample_image_path, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers={"Authorization": "Bearer wrong-key"},
                files={"files": ("test.jpg", f, "image/jpeg")},
            )
        assert resp.status_code == 401


class TestOCRAsyncFormats:
    """POST /api/v1/ocr/async — 支持格式测试"""

    @pytest.mark.parametrize("ext,mime", [
        (".jpg", "image/jpeg"),
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
        (".bmp", "image/bmp"),
        (".tiff", "image/tiff"),
        (".pdf", "application/pdf"),
    ])
    def test_supported_formats(
        self, client, auth_headers, tmp_path, ext, mime
    ):
        """各种支持格式均可上传"""
        test_file = tmp_path / f"test{ext}"
        # 写入最小有效内容（不需要是真正的图片）
        test_file.write_bytes(b"\x00" * 100)
        with open(test_file, "rb") as f:
            resp = client.post(
                "/api/v1/ocr/async",
                headers=auth_headers,
                files={"files": (f"test{ext}", f, mime)},
            )
        assert resp.status_code == 202
