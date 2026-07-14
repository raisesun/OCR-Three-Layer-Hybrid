#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vlm_fallback 单元测试"""

import json
import pytest
from unittest.mock import MagicMock, patch

from ocr_three_layer_hybrid.vlm_fallback import VLMFieldRetryHandler
from ocr_three_layer_hybrid.interfaces import DocumentType
from ocr_three_layer_hybrid.field_validator import ValidationStatus


class MockVLMClient:
    """Mock VLM 客户端"""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    def call(self, prompt, image_path, max_tokens=512):
        if self._error:
            raise self._error
        return self._response


class TestVLMFieldRetryHandler:
    """VLMFieldRetryHandler 测试"""

    # ===== get_failed_fields =====

    def test_get_failed_fields_with_invalid(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        fields = {"户号": "abc", "性别": "男"}
        failed = handler.get_failed_fields(fields)
        assert "户号" in failed
        assert "性别" not in failed

    def test_get_failed_fields_all_valid(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        fields = {"户号": "005300251", "性别": "男"}
        failed = handler.get_failed_fields(fields)
        assert failed == []

    # ===== should_fallback =====

    def test_should_fallback_true(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        fields = {"户号": "abc"}
        assert handler.should_fallback(fields) is True

    def test_should_fallback_false(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        fields = {"户号": "005300251"}
        assert handler.should_fallback(fields) is False

    # ===== _build_prompt =====

    def test_build_prompt_household(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        prompt = handler._build_prompt(
            DocumentType.HOUSEHOLD_REGISTER,
            ["户号", "住址"],
        )
        assert "户号" in prompt
        assert "住址" in prompt
        assert "户口" in prompt  # 使用户口本专用模板

    def test_build_prompt_unknown_type(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        prompt = handler._build_prompt(
            DocumentType.UNKNOWN,
            ["字段1", "字段2"],
        )
        assert "字段1" in prompt
        assert "字段2" in prompt

    # ===== _parse_response =====

    def test_parse_valid_json(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        response = json.dumps({"户号": "005300251", "住址": "安徽省蚌埠市"})
        result = handler._parse_response(response, ["户号", "住址"])
        assert result["户号"] == "005300251"
        assert result["住址"] == "安徽省蚌埠市"

    def test_parse_json_with_extra_fields(self):
        """多余字段应被过滤"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        response = json.dumps({"户号": "123", "年龄": "30"})
        result = handler._parse_response(response, ["户号"])
        assert "户号" in result
        assert "年龄" not in result

    def test_parse_invalid_json(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        result = handler._parse_response("not json", ["户号"])
        assert result == {}

    def test_parse_non_string_value(self):
        """非字符串值应被转为字符串"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        response = json.dumps({"户号": 12345})
        result = handler._parse_response(response, ["户号"])
        assert result["户号"] == "12345"

    # ===== fallback_extract =====

    def test_fallback_extract_success(self):
        response = json.dumps({"户号": "005300251"})
        client = MockVLMClient(response=response)
        handler = VLMFieldRetryHandler(vlm_client=client)

        result = handler.fallback_extract(
            "/fake/image.jpg",
            ["户号"],
            DocumentType.HOUSEHOLD_REGISTER,
        )
        assert result["户号"] == "005300251"

    def test_fallback_extract_empty_fields(self):
        """空字段列表直接返回空"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        result = handler.fallback_extract("/fake/image.jpg", [], DocumentType.UNKNOWN)
        assert result == {}

    def test_fallback_extract_vlm_error(self):
        """VLM 调用失败返回空"""
        client = MockVLMClient(error=ConnectionError("connection refused"))
        handler = VLMFieldRetryHandler(vlm_client=client)

        result = handler.fallback_extract(
            "/fake/image.jpg",
            ["户号"],
            DocumentType.HOUSEHOLD_REGISTER,
        )
        assert result == {}

    # ===== stats =====

    def test_stats_initial(self):
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        stats = handler.stats
        assert stats["call_count"] == 0
        assert stats["total_time_s"] == 0.0

    def test_stats_after_call(self):
        response = json.dumps({"户号": "123"})
        client = MockVLMClient(response=response)
        handler = VLMFieldRetryHandler(vlm_client=client)

        handler.fallback_extract("/fake.jpg", ["户号"], DocumentType.HOUSEHOLD_REGISTER)
        stats = handler.stats
        assert stats["call_count"] == 1
        assert stats["total_time_s"] >= 0


class TestVLMFieldRetryHandlerInit:
    """VLMFieldRetryHandler 初始化测试"""

    def test_init_with_vlm_client(self):
        """使用 vlm_client 初始化"""
        client = MockVLMClient()
        handler = VLMFieldRetryHandler(vlm_client=client)
        assert handler.vlm_client is client

    def test_init_with_vlm_config(self):
        """使用 vlm_config 初始化（应创建新 VLMClient）"""
        from ocr_three_layer_hybrid.config import VLMServiceConfig
        config = VLMServiceConfig(base_url="http://test:9999/v1")
        handler = VLMFieldRetryHandler(vlm_config=config)
        assert handler.vlm_client is not None
        assert handler.vlm_client.config.base_url == "http://test:9999/v1"
        handler.vlm_client.close()

    def test_init_default(self):
        """不传参数使用默认配置"""
        handler = VLMFieldRetryHandler()
        assert handler.vlm_client is not None
        handler.vlm_client.close()


class TestVLMFieldRetryHandlerPrompts:
    """Prompt 模板测试"""

    def test_build_prompt_marriage(self):
        """结婚证专用模板"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        prompt = handler._build_prompt(
            DocumentType.MARRIAGE_CERTIFICATE,
            ["结婚证字号", "持证人"],
        )
        assert "结婚证" in prompt
        assert "结婚证字号" in prompt
        assert "持证人" in prompt

    def test_build_prompt_id_card(self):
        """身份证专用模板"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        prompt = handler._build_prompt(
            DocumentType.ID_CARD,
            ["姓名", "公民身份号码"],
        )
        assert "身份证" in prompt
        assert "姓名" in prompt
        assert "公民身份号码" in prompt

    def test_build_prompt_contains_json_template(self):
        """Prompt 中包含 JSON 模板"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        prompt = handler._build_prompt(
            DocumentType.HOUSEHOLD_REGISTER,
            ["户号", "住址"],
        )
        # JSON 模板应包含字段名作为键
        assert '"户号"' in prompt
        assert '"住址"' in prompt


class TestVLMFieldRetryHandlerEdgeCases:
    """VLMFieldRetryHandler 边界情况测试"""

    def test_fallback_extract_missing_field_in_response(self):
        """VLM 返回的 JSON 缺少期望字段"""
        response = json.dumps({"户号": "123"})  # 只返回户号，不含住址
        client = MockVLMClient(response=response)
        handler = VLMFieldRetryHandler(vlm_client=client)

        result = handler.fallback_extract(
            "/fake/image.jpg",
            ["户号", "住址"],
            DocumentType.HOUSEHOLD_REGISTER,
        )
        assert result["户号"] == "123"
        assert result["住址"] == ""  # 缺失字段返回空字符串

    def test_fallback_extract_multiple_calls_accumulate_stats(self):
        """多次调用累加统计"""
        response = json.dumps({"户号": "123"})
        client = MockVLMClient(response=response)
        handler = VLMFieldRetryHandler(vlm_client=client)

        handler.fallback_extract("/fake.jpg", ["户号"], DocumentType.HOUSEHOLD_REGISTER)
        handler.fallback_extract("/fake.jpg", ["户号"], DocumentType.HOUSEHOLD_REGISTER)
        handler.fallback_extract("/fake.jpg", ["户号"], DocumentType.HOUSEHOLD_REGISTER)

        stats = handler.stats
        assert stats["call_count"] == 3
        assert stats["total_time_s"] >= 0
        assert stats["avg_time_s"] >= 0

    def test_should_fallback_empty_dict(self):
        """空字典不需要 fallback"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        assert handler.should_fallback({}) is False

    def test_get_failed_fields_empty_dict(self):
        """空字典没有失败字段"""
        handler = VLMFieldRetryHandler(vlm_client=MockVLMClient())
        failed = handler.get_failed_fields({})
        assert failed == []
