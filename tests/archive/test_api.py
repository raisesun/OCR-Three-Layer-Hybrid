#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API接口测试 — 测试所有HTTP端点

使用FastAPI TestClient进行接口级别测试。
不依赖外部VLM服务（mock掉OCRService）。
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# 构建测试用mock结果
def _mock_process_single_result(doc_type="身份证", layer="rule"):
    return {
        "classification": {
            "doc_type": doc_type,
            "doc_type_label": doc_type,
            "confidence": 0.95,
            "route": "standard_certificate",
            "route_name": "阶段1: 标准证件强信号",
            "signal": "公民身份号码",
            "primary_signals": ["公民身份号码"],
            "vlm_result": "",
            "is_attachment": False,
        },
        "extraction": {
            "success": True,
            "layer": layer,
            "fields": {"姓名": "张三", "公民身份号码": "34032320030616491X"},
            "error_message": None,
        },
        "pipeline_flow": {
            "stages": [],
            "active_stage": "stage1",
            "stage_match_info": "公民身份号码",
            "extraction_layer": layer,
            "layer_color": "#10b981",
            "doc_type": doc_type,
        },
        "timing": {"classify_ms": 5.0, "extract_ms": 10.0, "total_ms": 15.0},
        "ocr_text": "姓名 张三 公民身份号码 34032320030616491X",
        "image_path": "/tmp/test.jpg",
    }


@pytest.fixture
def client():
    """创建测试客户端"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    sys.path.insert(0, str(Path(__file__).parent.parent / "demo"))

    from fastapi.testclient import TestClient

    with patch("demo.server.ocr_service") as mock_service:
        mock_result = _mock_process_single_result()
        mock_service.process_image.return_value = mock_result
        mock_service.process_single.return_value = mock_result
        mock_service.process_batch.return_value = []
        mock_service.process_directory.return_value = {"results": [], "stats": {"total": 0, "total_time_s": 0, "ocr_time_s": 0, "pipeline_time_s": 0, "avg_time_ms": 0, "type_distribution": {}}}
        mock_service.run_ocr.return_value = "test ocr text"

        from demo.server import app
        with TestClient(app) as c:
            yield c, mock_service


class TestHealthEndpoints:
    def test_index_page(self, client):
        c, _ = client
        resp = c.get("/")
        assert resp.status_code == 200
        assert "OCR" in resp.text

    def test_baseline_cases(self, client):
        c, _ = client
        resp = c.get("/api/baseline/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "cases" in data["data"]


class TestProcessEndpoint:
    def test_process_single(self, client, tmp_path):
        c, mock_svc = client
        # 创建临时图片文件
        test_img = tmp_path / "test.jpg"
        test_img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        resp = c.post("/api/process", json={
            "image_path": str(test_img),
            "ocr_text": "test text"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["classification"]["doc_type"] == "身份证"

    def test_process_nonexistent_image(self, client):
        c, _ = client
        resp = c.post("/api/process", json={
            "image_path": "/nonexistent/path.jpg",
            "ocr_text": ""
        })
        assert resp.status_code == 404


class TestBatchEndpoints:
    def test_batch_directory(self, client):
        c, mock_svc = client
        resp = c.post("/api/process/batch/directory", json={
            "dir_path": "/tmp/test_dir"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    def test_batch_directory_not_found(self, client):
        c, mock_svc = client
        mock_svc.process_directory.return_value = {"error": "目录不存在: /fake"}
        resp = c.post("/api/process/batch/directory", json={
            "dir_path": "/fake"
        })
        assert resp.status_code == 404
