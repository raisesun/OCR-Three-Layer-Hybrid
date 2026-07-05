"""
OCR文本预处理模块

功能：
1. 文本清理（移除多余空格、特殊字符）
2. 格式标准化（日期、金额、标点符号）
3. 常见OCR错误纠正

目标：提升字段提取准确率5-10%
"""

import re
from typing import Dict, List, Optional, Tuple


class OCRTextPreprocessor:
    """OCR文本预处理器"""

    def __init__(
        self, enable_cleaning: bool = True, enable_standardization: bool = True
    ):
        """
        初始化预处理器

        Args:
            enable_cleaning: 是否启用文本清理
            enable_standardization: 是否启用格式标准化
        """
        self.enable_cleaning = enable_cleaning
        self.enable_standardization = enable_standardization

    def preprocess(self, text: str) -> str:
        """
        预处理OCR文本

        Args:
            text: 原始OCR文本

        Returns:
            预处理后的文本
        """
        if not text:
            return text

        result = text

        # 步骤1: 文本清理
        if self.enable_cleaning:
            result = self._clean_text(result)

        # 步骤2: 格式标准化
        if self.enable_standardization:
            result = self._standardize_format(result)

        return result

    def _clean_text(self, text: str) -> str:
        """
        文本清理

        1. 移除多余空格
        2. 规范化空白字符
        3. 移除特殊控制字符
        """
        result = text

        # 1. 移除零宽字符和控制字符
        result = re.sub(r"[​‌‍﻿]", "", result)

        # 2. 将全角空格转换为半角空格
        result = result.replace("　", " ")

        # 3. 规范化空白字符（制表符、换页符等转为空格）
        result = re.sub(r"[\t\f\v]", " ", result)

        # 4. 移除行首行尾多余空格（保留换行符）
        lines = result.split("\n")
        lines = [line.strip() for line in lines]
        result = "\n".join(lines)

        # 5. 压缩连续多个空格为单个空格
        result = re.sub(r" {2,}", " ", result)

        # 6. 压缩连续多个换行为单个换行
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result

    def _standardize_format(self, text: str) -> str:
        """
        格式标准化

        1. 日期格式统一
        2. 金额格式统一
        3. 标点符号统一
        """
        result = text

        # 1. 日期格式标准化
        result = self._standardize_dates(result)

        # 2. 金额格式标准化
        result = self._standardize_amounts(result)

        # 3. 标点符号标准化
        result = self._standardize_punctuation(result)

        return result

    def _standardize_dates(self, text: str) -> str:
        """
        日期格式标准化

        将各种日期格式统一为标准格式
        """
        result = text

        # 1. "2026年 1月 14日" → "2026年1月14日"（移除日期中的空格）
        result = re.sub(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", r"\1年\2月\3日", result
        )

        # 2. "2026- 01- 14" → "2026-01-14"
        result = re.sub(r"(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})", r"\1-\2-\3", result)

        # 3. "2026/ 01/ 14" → "2026/01/14"
        result = re.sub(r"(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})", r"\1/\2/\3", result)

        return result

    def _standardize_amounts(self, text: str) -> str:
        """
        金额格式标准化

        统一金额表示方式
        """
        result = text

        # 1. "¥ 40000.00" → "¥40000.00"（移除货币符号后的空格）
        result = re.sub(r"[¥￥]\s*(\d)", r"¥\1", result)

        # 2. "40,000.00" → "40000.00"（移除千位分隔符，可选）
        # 注意：这个可能会影响其他数字，暂时不启用
        # result = re.sub(r'(\d),(\d{3})', r'\1\2', result)

        return result

    def _standardize_punctuation(self, text: str) -> str:
        """
        标点符号标准化

        统一标点符号（保持中文标点）
        """
        result = text

        # 1. 统一冒号（保留中文冒号）
        # 不替换，因为中文文档应该用中文冒号

        # 2. 统一括号（保留中文括号）
        # 不替换，因为中文文档应该用中文括号

        # 3. 移除标点符号后的多余空格
        result = re.sub(r"([，。；：！？])\s+", r"\1", result)

        return result

    def preprocess_batch(self, texts: List[str]) -> List[str]:
        """
        批量预处理文本

        Args:
            texts: 文本列表

        Returns:
            预处理后的文本列表
        """
        return [self.preprocess(text) for text in texts]


class FieldExtractorEnhancer:
    """字段提取增强器（使用预处理后的文本）"""

    def __init__(self, preprocessor: Optional[OCRTextPreprocessor] = None):
        """
        初始化增强器

        Args:
            preprocessor: OCR文本预处理器
        """
        self.preprocessor = preprocessor or OCRTextPreprocessor()

    def enhance_text_for_extraction(self, text: str) -> str:
        """
        为字段提取增强文本

        Args:
            text: 原始OCR文本

        Returns:
            增强后的文本
        """
        return self.preprocessor.preprocess(text)


# 全局预处理器实例（供pipeline使用）
_global_preprocessor = OCRTextPreprocessor()


def get_preprocessor() -> OCRTextPreprocessor:
    """获取全局预处理器实例"""
    return _global_preprocessor


def preprocess_text(text: str) -> str:
    """
    便捷函数：预处理单个文本

    Args:
        text: 原始OCR文本

    Returns:
        预处理后的文本
    """
    return get_preprocessor().preprocess(text)


def preprocess_batch(texts: List[str]) -> List[str]:
    """
    便捷函数：批量预处理文本

    Args:
        texts: 文本列表

    Returns:
        预处理后的文本列表
    """
    return get_preprocessor().preprocess_batch(texts)
