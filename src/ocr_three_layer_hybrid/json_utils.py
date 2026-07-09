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

    # 第 3 层：正则提取 JSON 块
    json_match = re.search(r"\{[^{}]*\}", clean_response, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    return None
