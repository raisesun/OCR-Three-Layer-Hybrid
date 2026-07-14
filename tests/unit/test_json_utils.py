#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_utils 单元测试"""

import json
import pytest

from ocr_three_layer_hybrid.json_utils import (
    parse_json_from_response,
    _extract_json_block,
    merge_fields_first_nonempty,
)


class TestParseJsonFromResponse:
    """parse_json_from_response 测试"""

    def test_direct_json(self):
        """直接 JSON 字符串"""
        resp = '{"姓名": "张三", "性别": "男"}'
        result = parse_json_from_response(resp)
        assert result == {"姓名": "张三", "性别": "男"}

    def test_json_with_whitespace(self):
        """带前后空白的 JSON"""
        resp = '  \n{"姓名": "张三"}\n  '
        result = parse_json_from_response(resp)
        assert result == {"姓名": "张三"}

    def test_markdown_code_block(self):
        """markdown 代码块包裹的 JSON"""
        resp = '```json\n{"姓名": "张三"}\n```'
        result = parse_json_from_response(resp)
        assert result == {"姓名": "张三"}

    def test_markdown_without_language(self):
        """不带语言标识的代码块"""
        resp = '```\n{"姓名": "张三"}\n```'
        result = parse_json_from_response(resp)
        assert result == {"姓名": "张三"}

    def test_embedded_json_in_text(self):
        """文本中嵌入的 JSON"""
        resp = '根据图片识别结果：\n{"姓名": "张三", "性别": "男"}\n以上是提取结果。'
        result = parse_json_from_response(resp)
        assert result is not None
        assert result["姓名"] == "张三"

    def test_nested_json(self):
        """嵌套 JSON 对象"""
        resp = '{"doc_type": "身份证", "fields": {"姓名": "张三", "性别": "男"}}'
        result = parse_json_from_response(resp)
        assert result["fields"]["姓名"] == "张三"

    def test_invalid_json_returns_none(self):
        """无效 JSON 返回 None"""
        assert parse_json_from_response("这不是JSON") is None

    def test_empty_string_returns_none(self):
        """空字符串返回 None"""
        assert parse_json_from_response("") is None

    def test_non_string_returns_none(self):
        """非字符串输入返回 None"""
        assert parse_json_from_response(123) is None
        assert parse_json_from_response(None) is None
        assert parse_json_from_response(["list"]) is None

    def test_json_array_returns_none(self):
        """JSON 数组（非对象）返回 None"""
        assert parse_json_from_response('[1, 2, 3]') is None


class TestExtractJsonBlock:
    """_extract_json_block 测试"""

    def test_simple_json(self):
        """简单 JSON"""
        text = 'result: {"name": "test"}'
        result = _extract_json_block(text)
        assert result == '{"name": "test"}'

    def test_nested_json(self):
        """嵌套 JSON"""
        text = '{"a": {"b": {"c": 1}}}'
        result = _extract_json_block(text)
        assert result == text

    def test_json_with_strings_containing_braces(self):
        """字符串中包含花括号"""
        text = '{"key": "value {with} braces"}'
        result = _extract_json_block(text)
        assert result == text
        assert json.loads(result) == {"key": "value {with} braces"}

    def test_json_with_escaped_quotes(self):
        """转义引号"""
        text = r'{"key": "value \"quoted\""}'
        result = _extract_json_block(text)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["key"] == 'value "quoted"'

    def test_no_json_returns_none(self):
        """无 JSON 返回 None"""
        assert _extract_json_block("no json here") is None

    def test_unmatched_brace_returns_none(self):
        """未匹配的花括号返回 None"""
        assert _extract_json_block('{"incomplete') is None

    def test_json_after_text(self):
        """文本后的 JSON"""
        text = '一些说明文字\n{"字段": "值"}'
        result = _extract_json_block(text)
        assert result == '{"字段": "值"}'


class TestMergeFieldsFirstNonempty:
    """merge_fields_first_nonempty 测试"""

    def test_merge_new_values(self):
        """合并新值到空字段"""
        merged = {"姓名": "", "性别": ""}
        new = {"姓名": "张三", "性别": "男"}
        count = merge_fields_first_nonempty(merged, new)
        assert count == 2
        assert merged["姓名"] == "张三"
        assert merged["性别"] == "男"

    def test_skip_existing_values(self):
        """不覆盖已有值"""
        merged = {"姓名": "李四", "性别": ""}
        new = {"姓名": "张三", "性别": "男"}
        count = merge_fields_first_nonempty(merged, new)
        assert count == 1  # 只合并了性别
        assert merged["姓名"] == "李四"  # 未被覆盖
        assert merged["性别"] == "男"

    def test_skip_empty_new_values(self):
        """跳过空的新值"""
        merged = {"姓名": "", "性别": ""}
        new = {"姓名": "", "性别": "男"}
        count = merge_fields_first_nonempty(merged, new)
        assert count == 1
        assert merged["姓名"] == ""  # 仍为空
        assert merged["性别"] == "男"

    def test_skip_whitespace_values(self):
        """跳过纯空白值"""
        merged = {"姓名": ""}
        new = {"姓名": "  "}
        count = merge_fields_first_nonempty(merged, new)
        assert count == 0

    def test_extra_keys_merged(self):
        """新字段中多余的键也会被合并"""
        merged = {"姓名": ""}
        new = {"姓名": "张三", "年龄": "30"}
        count = merge_fields_first_nonempty(merged, new)
        assert count == 2  # 姓名 + 年龄 都合并了
        assert merged["姓名"] == "张三"
        assert merged["年龄"] == "30"
