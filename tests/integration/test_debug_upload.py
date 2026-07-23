#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Debug 路由安全修复（S2 / S5 / S7）

覆盖：
- S2: debug 路由在认证启用时要求 API Key
- S5: /api/upload 扩展名白名单 + 大小限制 + UUID 文件名（防存储型 XSS）
- S7: /api/debug/ocr/async 文件数量 / 大小 / 扩展名校验
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 确保 src/ 在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# 复用 conftest 的 OCR_API_KEYS 设置
TEST_API_KEY = "test-key-12345"
os.environ.setdefault("OCR_API_KEYS", TEST_API_KEY)

import pytest
from fastapi.testclient import TestClient

from ocr_api.ocr.server import create_app


@pytest.fixture
def debug_app(mock_ocr_service, task_manager, authenticator, tmp_upload_dir, monkeypatch):
    """debug=True 的测试应用（加载 debug 路由，上传目录隔离）"""
    # 让 server 模块把 debug 路由的 upload_dir 指向临时目录
    import ocr_api.ocr.server as server_module
    monkeypatch.setattr(server_module, "UPLOAD_DIR", tmp_upload_dir)

    mock_baseline = MagicMock()
    app = create_app(
        ocr_service=mock_ocr_service,
        task_manager=task_manager,
        authenticator=authenticator,
        baseline_service=mock_baseline,
        debug=True,
    )
    return app


@pytest.fixture
def debug_client(debug_app):
    with TestClient(debug_app) as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


class TestDebugRouteAuth:
    """S2: debug 路由鉴权（认证启用时要求 API Key）"""

    def test_upload_requires_auth(self, debug_client):
        """无认证上传 -> 401"""
        resp = debug_client.post(
            "/api/upload",
            files={"file": ("test.jpg", b"content", "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_upload_with_auth_passes_auth(self, debug_client, auth_headers):
        """带认证上传合法文件 -> 通过鉴权（200）"""
        resp = debug_client.post(
            "/api/upload",
            headers=auth_headers,
            files={"file": ("test.jpg", b"fake-jpeg", "image/jpeg")},
        )
        assert resp.status_code == 200


class TestUploadSecurity:
    """S5: /api/upload 上传安全校验"""

    def test_rejects_html_extension(self, debug_client, auth_headers):
        """上传 .html 被拒（防存储型 XSS）"""
        resp = debug_client.post(
            "/api/upload",
            headers=auth_headers,
            files={"file": ("evil.html", b"<script>alert(1)</script>", "text/html")},
        )
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, debug_client, auth_headers):
        """上传超 20MB 被拒"""
        big = b"x" * (20 * 1024 * 1024 + 1)
        resp = debug_client.post(
            "/api/upload",
            headers=auth_headers,
            files={"file": ("big.jpg", big, "image/jpeg")},
        )
        assert resp.status_code == 413

    def test_accepts_valid_image_with_uuid_name(self, debug_client, auth_headers, tmp_upload_dir):
        """合法 jpg 上传成功，文件名用 UUID（防枚举）"""
        resp = debug_client.post(
            "/api/upload",
            headers=auth_headers,
            files={"file": ("test.jpg", b"fake-jpeg-content", "image/jpeg")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        file_name = body["data"]["file_name"]
        # UUID 文件名：upload_<hex>.jpg
        assert file_name.startswith("upload_")
        assert file_name.endswith(".jpg")
        assert "evil" not in file_name  # 不含原始名

    def test_rejects_exe_extension(self, debug_client, auth_headers):
        """上传 .exe 被拒"""
        resp = debug_client.post(
            "/api/upload",
            headers=auth_headers,
            files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        assert resp.status_code == 400


class TestDebugAsyncUploadSecurity:
    """S7: /api/debug/ocr/async 异步上传安全校验"""

    def test_rejects_html_extension(self, debug_client, auth_headers):
        """异步上传 .html 被拒"""
        resp = debug_client.post(
            "/api/debug/ocr/async",
            headers=auth_headers,
            files=[("files", ("evil.html", b"<script>", "text/html"))],
        )
        assert resp.status_code == 400

    def test_rejects_too_many_files(self, debug_client, auth_headers):
        """超过 500 个文件被拒"""
        files = [
            ("files", (f"img{i}.jpg", b"x", "image/jpeg"))
            for i in range(501)
        ]
        resp = debug_client.post(
            "/api/debug/ocr/async",
            headers=auth_headers,
            files=files,
        )
        assert resp.status_code == 400

    def test_rejects_empty_files(self, debug_client, auth_headers):
        """空文件列表被拒"""
        resp = debug_client.post(
            "/api/debug/ocr/async",
            headers=auth_headers,
            files=[],
        )
        # FastAPI 对 File(...) 必填会返回 422；若绕过则我们的校验返回 400
        assert resp.status_code in (400, 422)


class TestPathTraversalGuard:
    """S3: 路径遍历防护（is_relative_to 替代 startswith）"""

    def test_directories_rejects_sibling_prefix(self, debug_client, auth_headers):
        """同前缀同级目录 sample-OCR-backup 被拒 403（startswith 会误放行）"""
        resp = debug_client.get(
            "/api/directories",
            headers=auth_headers,
            params={"parent": "/Users/dongsun/Github/sample-OCR-backup"},
        )
        assert resp.status_code == 403

    def test_directories_rejects_dotdot_traversal(self, debug_client, auth_headers):
        """../ 遍历到白名单外被拒 403"""
        resp = debug_client.get(
            "/api/directories",
            headers=auth_headers,
            params={"parent": "/Users/dongsun/Github/sample-OCR/../../etc"},
        )
        assert resp.status_code == 403
