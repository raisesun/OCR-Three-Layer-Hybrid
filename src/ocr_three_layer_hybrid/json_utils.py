#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON 解析工具函数

提取 VLM 响应中 JSON 的公共逻辑，避免多处重复。
"""

import json
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def parse_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """从 VLM 响应中解析 JSON

    3 层 fallback：
    1. 直接 json.loads()
    2. 去除 markdown 代码块后解析
    3. 正则提取 JSON 块

    Args:
        response: VLM 返回的原始字符串

    Returns:
        解析后的 dict，失败返回 None
    """
    if not isinstance(response, str):
        return None

    clean_response = response.strip()

    # 第 1 层：直接解析
    try:
        parsed = json.loads(clean_response)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    # 第 2 层：去除 markdown 代码块
    if clean_response.startswith("```"):
        lines = clean_response.split("\n")
        # 去除第一行和最后一行（如果是```）
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean_response = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_response)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    # 第 3 层：正则提取 JSON 块（支持嵌套）
    json_str = _extract_json_block(clean_response)
    if json_str:
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _extract_json_block(text: str) -> Optional[str]:
    """从文本中提取 JSON 对象块（支持嵌套）

    使用括号匹配算法，而非正则表达式，以支持嵌套的 JSON 对象。

    Args:
        text: 可能包含 JSON 的文本

    Returns:
        提取的 JSON 字符串，如果未找到则返回 None
    """
    # 找到第一个 {
    start = text.find('{')
    if start == -1:
        return None

    # 使用栈匹配括号
    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == '\\':
            escape_next = True
            continue

        if char == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return text[start:i+1]

    return None


def merge_fields_first_nonempty(
    merged_fields: Dict[str, str],
    new_fields: Dict[str, str],
) -> int:
    """合并字段：取第一个非空值

    用于多页文档提取时合并各页的字段结果。

    Args:
        merged_fields: 已合并的字段字典（会被修改）
        new_fields: 新页面的字段字典

    Returns:
        从 new_fields 中合并的字段数量
    """
    merged_count = 0
    for key, value in new_fields.items():
        if value and value.strip() and not merged_fields.get(key):
            merged_fields[key] = value
            merged_count += 1
    return merged_count
