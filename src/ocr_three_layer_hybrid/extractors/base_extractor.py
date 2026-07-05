# -*- coding: utf-8 -*-
"""提取器基类"""

import re
from typing import Dict, List


class BaseExtractor:
    """字段提取器基类

    提供通用的正则表达式提取工具方法。
    """

    @staticmethod
    def extract_pattern(text: str, pattern: str, default: str = "") -> str:
        """使用正则表达式提取单个值

        Args:
            text: 源文本
            pattern: 正则表达式模式（必须包含一个捕获组）
            default: 未匹配时的默认值

        Returns:
            提取的值或默认值
        """
        match = re.search(pattern, text)
        return match.group(1).strip() if match else default

    @staticmethod
    def extract_all_patterns(text: str, patterns: Dict[str, str]) -> Dict[str, str]:
        """使用多个正则表达式模式提取多个字段

        Args:
            text: 源文本
            patterns: {字段名: 正则表达式模式} 字典

        Returns:
            {字段名: 提取值} 字典
        """
        result = {}
        for field, pattern in patterns.items():
            match = re.search(pattern, text)
            result[field] = match.group(1).strip() if match else ""
        return result

    @staticmethod
    def clean_value(value: str) -> str:
        """清理提取的值

        移除多余空白、换行符等。

        Args:
            value: 原始值

        Returns:
            清理后的值
        """
        if not value:
            return ""
        # 移除多余空白
        value = re.sub(r'\s+', ' ', value)
        return value.strip()
