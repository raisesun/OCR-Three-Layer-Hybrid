#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试VLM层（GLM-OCR多模态模型）

注意：需要Ollama服务的测试标记为slow/integration/vlm
"""

import base64
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo, ProcessingLayer


class TestVLMExtractionLayerUnit:
    """VLM层单元测试（不依赖外部服务）"""

    def _create_layer(self, **kwargs):
        """延迟导入避免循环依赖"""
        from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
        return VLMExtractionLayer(**kwargs)

    def test_supported_doc_types(self):
        layer = self._create_layer()
        # VLM层支持所有文档类型（有专用Prompt的用专用，无的用通用模板）
        assert DocumentType.HOUSEHOLD_REGISTER in layer.supported_doc_types
        assert DocumentType.UNKNOWN in layer.supported_doc_types  # VLM兜底支持UNKNOWN
        assert DocumentType.ID_CARD in layer.supported_doc_types  # 已扩展支持所有类型
        assert DocumentType.PURCHASE_CONTRACT in layer.supported_doc_types

    def test_can_process_household_register(self):
        layer = self._create_layer()
        info = DocumentInfo(
            image_path="/tmp/hukou.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        assert layer.can_process(info) is True

    def test_can_process_unknown(self):
        layer = self._create_layer()
        info = DocumentInfo(
            image_path="/tmp/unknown.jpg",
            doc_type=DocumentType.UNKNOWN,
        )
        assert layer.can_process(info) is True  # VLM现在支持UNKNOWN文档兜底

    def test_default_config(self):
        layer = self._create_layer()
        assert layer.model_name == "qwen2.5-vl-7b"
        assert layer.base_url == "http://localhost:8082/v1"
        assert layer.timeout == 120.0

    def test_custom_config(self):
        layer = self._create_layer(
            model_name="custom-model",
            base_url="http://custom:8080/v1",
            timeout=60.0,
        )
        assert layer.model_name == "custom-model"
        assert layer.base_url == "http://custom:8080/v1"
        assert layer.timeout == 60.0

    def test_encode_image_base64(self, tmp_path):
        layer = self._create_layer()
        test_image = tmp_path / "test.jpg"
        test_image.write_bytes(b"fake image content")

        encoded = layer._encode_image_base64(str(test_image))
        # base64解码后应该是原始字节
        decoded = base64.b64decode(encoded)
        assert decoded == b"fake image content"

    def test_build_prompt_household_register(self):
        layer = self._create_layer()
        key_list = ["姓名", "户主", "出生日期", "民族"]
        # 创建DocumentInfo对象
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            ocr_texts=[],
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            confidence=0.9,
        )
        prompt = layer._build_prompt(doc_info, key_list)

        # 验证Prompt包含关键字段
        assert "户口本" in prompt or "户" in prompt
        assert "JSON" in prompt or "json" in prompt
        # 验证包含请求的字段
        for key in key_list:
            assert key in prompt

    def test_build_prompt_with_image_path(self):
        layer = self._create_layer()
        key_list = ["姓名"]
        # 创建DocumentInfo对象
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            ocr_texts=[],
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            confidence=0.9,
        )
        prompt = layer._build_prompt(doc_info, key_list)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_parse_json_response_dict(self):
        layer = self._create_layer()
        response = {"姓名": "张三", "户主": "李四"}
        fields = layer._parse_json_response(response, ["姓名", "户主"])
        assert fields["姓名"] == "张三"
        assert fields["户主"] == "李四"

    def test_parse_json_response_string(self):
        layer = self._create_layer()
        response = '{"姓名": "王五", "户主": "赵六"}'
        fields = layer._parse_json_response(response, ["姓名", "户主"])
        assert fields["姓名"] == "王五"
        assert fields["户主"] == "赵六"

    def test_parse_json_response_with_markdown(self):
        layer = self._create_layer()
        response = '```json\n{"姓名": "张三"}\n```'
        fields = layer._parse_json_response(response, ["姓名"])
        assert fields["姓名"] == "张三"

    def test_parse_json_response_invalid(self):
        layer = self._create_layer()
        response = "不是JSON"
        fields = layer._parse_json_response(response, ["姓名"])
        assert fields["姓名"] == ""

    def test_parse_json_response_missing_keys(self):
        layer = self._create_layer()
        response = {"姓名": "张三"}
        fields = layer._parse_json_response(response, ["姓名", "户主"])
        assert fields["姓名"] == "张三"
        assert fields["户主"] == ""

    @patch("ocr_three_layer_hybrid.vlm_layer.VLMExtractionLayer._call_vlm")
    def test_extract_success(self, mock_call_vlm, tmp_path):
        """模拟VLM成功提取"""
        layer = self._create_layer()
        mock_call_vlm.return_value = {
            "姓名": "张三",
            "户主": "李四",
            "出生日期": "1990年1月1日",
        }

        # 创建临时测试图片
        test_image = tmp_path / "hukou.jpg"
        test_image.write_bytes(b"fake image content")

        info = DocumentInfo(
            image_path=str(test_image),
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        result = layer.extract(info, ["姓名", "户主", "出生日期", "民族"])

        assert result.success is True
        assert result.doc_type == DocumentType.HOUSEHOLD_REGISTER
        assert result.layer == ProcessingLayer.VLM
        assert result.fields["姓名"] == "张三"
        assert result.fields["户主"] == "李四"
        assert result.fields["出生日期"] == "1990年1月1日"
        assert result.fields["民族"] == ""

        # 验证_call_vlm被正确调用（传递图片路径而非base64）
        mock_call_vlm.assert_called_once()
        call_args = mock_call_vlm.call_args
        assert len(call_args[0]) == 2
        assert call_args[0][1] == str(test_image)

    @patch("ocr_three_layer_hybrid.vlm_layer.VLMExtractionLayer._call_vlm")
    def test_extract_failure(self, mock_call_vlm, tmp_path):
        """模拟VLM失败"""
        layer = self._create_layer()
        mock_call_vlm.side_effect = Exception("Ollama服务不可用")

        # 创建临时测试图片
        test_image = tmp_path / "hukou.jpg"
        test_image.write_bytes(b"fake image content")

        info = DocumentInfo(
            image_path=str(test_image),
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        result = layer.extract(info, ["姓名"])

        assert result.success is False
        assert "Ollama服务不可用" in result.error_message
        assert result.fields["姓名"] == ""

    def test_image_not_found(self):
        """图片不存在时应返回失败"""
        layer = self._create_layer()
        info = DocumentInfo(
            image_path="/nonexistent/path/image.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        result = layer.extract(info, ["姓名"])

        assert result.success is False
        assert "不存在" in result.error_message or "not found" in result.error_message.lower()

    @patch("ocr_three_layer_hybrid.vlm_layer.VLMExtractionLayer._call_vlm")
    def test_extract_unknown_with_doc_type_feedback(self, mock_call_vlm, tmp_path):
        """轻量修复: UNKNOWN文档VLM返回的doc_type应被反馈到结果中"""
        layer = self._create_layer()
        mock_call_vlm.return_value = {
            "doc_type": "HOUSEHOLD_REGISTER",
            "confidence": 0.95,
            "fields": {"姓名": "张三", "户主姓名": "李四"},
        }

        test_image = tmp_path / "unknown.jpg"
        test_image.write_bytes(b"fake image content")

        info = DocumentInfo(
            image_path=str(test_image),
            doc_type=DocumentType.UNKNOWN,
        )
        result = layer.extract(info, ["文档类型", "编号", "日期"])

        assert result.success is True
        # 原始doc_type保持不变
        assert result.doc_type == DocumentType.UNKNOWN
        # VLM分类结果反馈到vlm_classified_type
        assert result.vlm_classified_type == DocumentType.HOUSEHOLD_REGISTER
        # 嵌套字段被正确提取
        assert result.fields["姓名"] == "张三"
        assert result.fields["户主姓名"] == "李四"


@pytest.mark.slow
@pytest.mark.vlm
@pytest.mark.integration
class TestVLMExtractionLayerIntegration:
    """VLM层集成测试（需要Ollama服务）"""

    def test_real_extraction(self):
        """真实调用GLM-OCR"""
        from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer

        layer = VLMExtractionLayer()
        info = DocumentInfo(
            image_path="/Users/dongsun/Github/sample-OCR/增量房图片资料/202403080014/2bebb1f8eca747d68fdfee98b4456be2.jpeg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        result = layer.extract(info, ["姓名", "户主", "出生日期", "民族"])

        assert result.success is True
        assert result.time_cost < 120
        # 至少有一个字段被提取
        assert any(v for v in result.fields.values() if v)
