#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成测试共享 fixtures

提供：
- mock_ocr_service: Mock 的 OCRService（不依赖真实 OCR/VLM 服务）
- test_client: FastAPI TestClient（使用临时 DB + Mock 服务）
- auth_headers: 带有效 API Key 的请求头
- sample_image_path: 测试图片路径
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 确保 src/ 在 Python 路径中
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# 在导入 API 模块之前设置环境变量（必须在 import server 之前）
TEST_API_KEY = "test-key-12345"
os.environ["OCR_API_KEYS"] = TEST_API_KEY

from fastapi.testclient import TestClient
from ocr_api.ocr.server import create_app
from ocr_api.common.task_manager import TaskManager
from ocr_api.common.auth import APIKeyAuthenticator
from ocr_three_layer_hybrid.service import OCRService
from ocr_three_layer_hybrid.config import OCRConfig


@pytest.fixture(autouse=True)
def mock_background_worker():
    """阻止后台 Worker 实际执行（避免真实 OCR 调用）"""
    import asyncio

    original_create_task = asyncio.create_task
    created_tasks = []

    def fake_create_task(coro, **kwargs):
        # 关闭协程以避免 RuntimeWarning
        coro.close()
        # 返回一个已完成的 Future（不实际执行）
        future = asyncio.Future()
        future.set_result(None)
        created_tasks.append(future)
        return future

    with patch("asyncio.create_task", side_effect=fake_create_task):
        yield

    # 清理未完成的 tasks
    for t in created_tasks:
        if not t.done():
            t.cancel()


# 测试图片路径
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def tmp_upload_dir(tmp_path, monkeypatch):
    """临时上传目录（替换 config.UPLOAD_DIR）"""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    # monkeypatch config 模块中的 UPLOAD_DIR
    import ocr_three_layer_hybrid.config as config_module
    import ocr_api.ocr.routes.ocr as ocr_route_module
    monkeypatch.setattr(config_module, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(ocr_route_module, "UPLOAD_DIR", upload_dir)
    return upload_dir


@pytest.fixture
def mock_ocr_service():
    """Mock 的 OCRService（不依赖真实 OCR/VLM 服务）"""
    service = MagicMock(spec=OCRService)
    service.process_single.return_value = {
        "doc_type": "身份证",
        "layer": "rule",
        "fields": {"姓名": "张三", "公民身份号码": "340321199001011234"},
        "success": True,
        "confidence": 0.95,
        "timing_ms": 1234,
    }
    service.config = OCRConfig()
    return service


@pytest.fixture
def task_manager(tmp_path):
    """临时 SQLite 数据库的 TaskManager"""
    db_path = str(tmp_path / "test_tasks.db")
    return TaskManager(db_path=db_path)


@pytest.fixture
def authenticator():
    """使用测试 API Key 的认证器"""
    # OCR_API_KEYS 已在模块顶部设置
    return APIKeyAuthenticator()


@pytest.fixture
def test_app(mock_ocr_service, task_manager, authenticator, tmp_upload_dir):
    """配置好的 FastAPI 测试应用"""
    app = create_app(
        ocr_service=mock_ocr_service,
        task_manager=task_manager,
        authenticator=authenticator,
        debug=False,
    )
    return app


@pytest.fixture
def client(test_app):
    """FastAPI TestClient"""
    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def auth_headers():
    """带有效 API Key 的请求头"""
    return {"Authorization": f"Bearer {TEST_API_KEY}"}


@pytest.fixture
def sample_image_path():
    """测试图片路径（不动产权证书）"""
    path = FIXTURES_DIR / "sample_property.jpg"
    assert path.exists(), f"测试图片不存在: {path}"
    return path


@pytest.fixture
def sample_contract_path():
    """测试合同图片路径"""
    path = FIXTURES_DIR / "sample_contract.jpeg"
    assert path.exists(), f"测试图片不存在: {path}"
    return path
