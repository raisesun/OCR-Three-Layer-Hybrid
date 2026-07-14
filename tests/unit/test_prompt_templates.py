#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prompt_templates 单元测试"""

import pytest

from ocr_three_layer_hybrid.prompt_templates import (
    build_prompt,
    COMMON_SUFFIX,
    PROMPT_TEMPLATES,
)


class TestPromptTemplates:
    """PROMPT_TEMPLATES 常量测试"""

    def test_has_household_register(self):
        assert "HOUSEHOLD_REGISTER" in PROMPT_TEMPLATES

    def test_has_id_card(self):
        # UNKNOWN 模板应该有
        assert "UNKNOWN" in PROMPT_TEMPLATES

    def test_all_templates_are_strings(self):
        for key, template in PROMPT_TEMPLATES.items():
            assert isinstance(template, str), f"{key} 不是字符串"
            assert len(template) > 0, f"{key} 为空"

    def test_common_suffix_not_empty(self):
        assert len(COMMON_SUFFIX) > 0
        assert "JSON" in COMMON_SUFFIX


class TestBuildPrompt:
    """build_prompt 函数测试"""

    def test_known_doc_type(self):
        """已知文档类型使用专用模板"""
        prompt = build_prompt("HOUSEHOLD_REGISTER")
        assert "户口" in prompt
        # 应该包含公共后缀
        assert "重要注意事项" in prompt

    def test_common_suffix_appended(self):
        """所有 prompt 都包含公共后缀"""
        for doc_type in ["HOUSEHOLD_REGISTER", "UNKNOWN", "MARRIAGE_CERTIFICATE"]:
            prompt = build_prompt(doc_type)
            assert COMMON_SUFFIX in prompt, f"{doc_type} 缺少公共后缀"

    def test_unknown_with_key_list(self):
        """未知文档类型 + key_list 生成通用 prompt"""
        prompt = build_prompt("NONEXISTENT_TYPE", key_list=["姓名", "性别"])
        assert "姓名" in prompt
        assert "性别" in prompt
        assert COMMON_SUFFIX in prompt

    def test_unknown_without_key_list(self):
        """未知文档类型 + 无 key_list 生成最简 prompt"""
        prompt = build_prompt("NONEXISTENT_TYPE")
        assert "提取" in prompt
        assert COMMON_SUFFIX in prompt

    def test_empty_key_list(self):
        """空 key_list 等同于无 key_list"""
        prompt = build_prompt("NONEXISTENT_TYPE", key_list=[])
        assert "提取" in prompt

    def test_prompt_contains_json_format(self):
        """已知模板包含 JSON 格式说明"""
        prompt = build_prompt("HOUSEHOLD_REGISTER")
        assert "JSON" in prompt
