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

        1. 移除OCR输出的字间空格（PaddleOCR-VL等模型的常见输出格式）
        2. 移除多余空格
        3. 规范化空白字符
        4. 移除特殊控制字符
        """
        result = text

        # 1. 移除零宽字符和控制字符
        result = re.sub(r"[​‌‍﻿]", "", result)

        # 2. 将全角空格转换为半角空格
        result = result.replace("　", " ")

        # 3. 规范化空白字符（制表符、换页符等转为空格）
        result = re.sub(r"[\t\f\v]", " ", result)

        # 4. 移除OCR输出的字间空格（逐行处理，只处理"字间空格模式"的行）
        # 字间空格模式：一行中大部分中文字符之间都有单空格
        # 例如："商 品 房 买 卖 合 同" → "商品房买卖合同"
        # 但对于："姓名 张三" → 保留（不是字间空格模式）
        lines = result.split("\n")
        processed_lines = []
        for line in lines:
            processed_lines.append(self._remove_ocr_char_spacing(line))
        result = "\n".join(processed_lines)

        # 5. 移除行首行尾多余空格（保留换行符）
        lines = result.split("\n")
        lines = [line.strip() for line in lines]
        result = "\n".join(lines)

        # 6. 压缩连续多个空格为单个空格
        result = re.sub(r" {2,}", " ", result)

        # 7. 压缩连续多个换行为单个换行
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result

    def _remove_ocr_char_spacing(self, line: str) -> str:
        """移除OCR输出的字间空格（仅当行呈现"字间空格模式"时）

        字间空格模式：行内用空格分隔后，大部分"部分"都是单字符
        例如："商 品 房 买 卖 合 同" → 分割后每个部分都是单字 → "商品房买卖合同"
        例如："合 同 编 号 ： 2 0 2 4" → 分割后每个部分都是单字/标点 → "合同编号：2024"
        但对于："姓名 张三" → 分割后"姓名"是2字 → 保留
        但对于："姓名 张三 公民身份号码" → 分割后"姓名"、"公民身份号码"是多字 → 保留
        """
        if not line or len(line.strip()) < 3:
            return line

        # 按空格分割（包括多个空格）
        parts = line.split()

        if len(parts) < 3:
            # 部分太少，不处理
            return line.strip()

        # 统计"单字符部分"vs"多字符部分"
        single_char_parts = 0
        multi_char_parts = 0

        for part in parts:
            # 计算内容字符数（去除标点）
            content_chars = re.findall(r"[一-鿿\d]", part)
            if len(content_chars) <= 1:
                single_char_parts += 1
            else:
                multi_char_parts += 1

        total = single_char_parts + multi_char_parts
        if total == 0:
            return line.strip()

        # 如果超过80%的部分都是单字符，且至少有3个单字符部分，认为是字间空格模式
        ratio = single_char_parts / total
        # H9: 多字段行（>=2 冒号）不执行全空格移除，避免合并字段（运行时验证 0% 触发，防御性）
        colon_count = line.count("：") + line.count(":")
        if ratio >= 0.8 and single_char_parts >= 3 and colon_count < 2:
            # 移除所有空格
            return re.sub(r"\s+", "", line)
        else:
            return line.strip()

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
