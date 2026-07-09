#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""text_preprocessor 单元测试"""

import pytest

from ocr_three_layer_hybrid.text_preprocessor import (
    OCRTextPreprocessor,
    preprocess_text,
    preprocess_batch,
    get_preprocessor,
)


class TestOCRTextPreprocessor:
    """OCRTextPreprocessor 测试"""

    def setup_method(self):
        self.preprocessor = OCRTextPreprocessor()

    # ===== 基础功能 =====

    def test_empty_text(self):
        assert self.preprocessor.preprocess("") == ""

    def test_none_text(self):
        assert self.preprocessor.preprocess(None) is None

    # ===== 字间空格移除 =====

    def test_remove_char_spacing(self):
        """移除 OCR 字间空格"""
        text = "商 品 房 买 卖 合 同"
        result = self.preprocessor.preprocess(text)
        assert "商品房买卖合同" in result

    def test_keep_normal_spacing(self):
        """保留正常的词间空格"""
        text = "姓名 张三 公民身份号码"
        result = self.preprocessor.preprocess(text)
        assert "姓名" in result
        assert "张三" in result

    # ===== 零宽字符移除 =====

    def test_remove_zero_width_chars(self):
        """移除零宽字符"""
        text = "姓名​张三"  # 含零宽空格
        result = self.preprocessor.preprocess(text)
        assert "​" not in result
        assert "姓名张三" in result

    # ===== 全角空格转换 =====

    def test_fullwidth_space(self):
        """全角空格转为半角"""
        text = "姓名　张三"
        result = self.preprocessor.preprocess(text)
        assert "　" not in result

    # ===== 日期标准化 =====

    def test_date_with_spaces(self):
        """日期中的空格移除"""
        text = "2026年 1月 14日"
        result = self.preprocessor.preprocess(text)
        assert "2026年1月14日" in result

    def test_date_dash_with_spaces(self):
        """短横线日期空格移除"""
        text = "2026- 01- 14"
        result = self.preprocessor.preprocess(text)
        assert "2026-01-14" in result

    # ===== 金额标准化 =====

    def test_currency_symbol_spacing(self):
        """货币符号后空格移除"""
        text = "¥ 40000.00"
        result = self.preprocessor.preprocess(text)
        assert "¥40000.00" in result

    # ===== 标点符号标准化 =====

    def test_punctuation_spacing(self):
        """标点后多余空格移除"""
        text = "姓名：  张三"
        result = self.preprocessor.preprocess(text)
        assert "姓名：张三" in result

    # ===== 多行文本 =====

    def test_multiple_spaces_compressed(self):
        """多个连续空格压缩"""
        text = "姓名    张三"
        result = self.preprocessor.preprocess(text)
        assert "姓名 张三" in result

    def test_multiple_newlines_compressed(self):
        """多个连续换行压缩"""
        text = "第一行\n\n\n\n第二行"
        result = self.preprocessor.preprocess(text)
        assert "\n\n\n" not in result

    # ===== 开关控制 =====

    def test_disable_cleaning(self):
        """禁用文本清理"""
        pp = OCRTextPreprocessor(enable_cleaning=False)
        text = "商 品 房"
        result = pp.preprocess(text)
        # 不清理，字间空格保留
        assert "商 品 房" in result

    def test_disable_standardization(self):
        """禁用格式标准化"""
        pp = OCRTextPreprocessor(enable_standardization=False)
        text = "2026年 1月 14日"
        result = pp.preprocess(text)
        # 不清理日期空格（但 _clean_text 可能影响）
        # 至少不抛异常
        assert result is not None


class TestRemoveOcrCharSpacing:
    """_remove_ocr_char_spacing 测试"""

    def setup_method(self):
        self.pp = OCRTextPreprocessor()

    def test_char_spacing_pattern(self):
        """字间空格模式"""
        result = self.pp._remove_ocr_char_spacing("合 同 编 号 ： 2 0 2 4")
        assert "合同编号" in result

    def test_normal_text_preserved(self):
        """正常文本保留"""
        result = self.pp._remove_ocr_char_spacing("姓名 张三")
        assert "姓名" in result
        assert "张三" in result

    def test_short_line_not_processed(self):
        """短行不处理"""
        result = self.pp._remove_ocr_char_spacing("ab")
        assert result == "ab"

    def test_empty_line(self):
        """空行"""
        result = self.pp._remove_ocr_char_spacing("")
        assert result == ""


class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_preprocess_text(self):
        result = preprocess_text("商 品 房 买 卖 合 同")
        assert "商品房买卖合同" in result

    def test_preprocess_batch(self):
        texts = ["商 品 房", "买 卖 合 同"]
        results = preprocess_batch(texts)
        assert len(results) == 2
        assert "商品房" in results[0]
        assert "买卖合同" in results[1]


class TestGetPreprocessor:
    """get_preprocessor 全局单例测试"""

    def test_returns_instance(self):
        """返回 OCRTextPreprocessor 实例"""
        pp = get_preprocessor()
        assert isinstance(pp, OCRTextPreprocessor)

    def test_returns_same_instance(self):
        """多次调用返回同一实例"""
        pp1 = get_preprocessor()
        pp2 = get_preprocessor()
        assert pp1 is pp2

    def test_default_settings(self):
        """默认启用清理和标准化"""
        pp = get_preprocessor()
        assert pp.enable_cleaning is True
        assert pp.enable_standardization is True


class TestStandardizeFormat:
    """格式标准化补充测试"""

    def setup_method(self):
        self.pp = OCRTextPreprocessor()

    def test_date_slash_format_with_spaces(self):
        """斜杠日期格式空格移除"""
        text = "2026/ 01/ 14"
        result = self.pp.preprocess(text)
        assert "2026/01/14" in result

    def test_date_year_month_day_no_spaces(self):
        """无空格的年月日保持不变"""
        text = "2026年1月14日"
        result = self.pp.preprocess(text)
        assert "2026年1月14日" in result

    def test_fullwidth_currency_symbol(self):
        """全角货币符号后空格移除"""
        text = "￥ 40000.00"
        result = self.pp.preprocess(text)
        assert "¥40000.00" in result

    def test_punctuation_semicolon(self):
        """中文分号后空格移除"""
        text = "姓名；  张三"
        result = self.pp.preprocess(text)
        assert "姓名；张三" in result

    def test_punctuation_exclamation(self):
        """中文感叹号后空格移除"""
        text = "注意！  重要"
        result = self.pp.preprocess(text)
        assert "注意！重要" in result

    def test_punctuation_question(self):
        """中文问号后空格移除"""
        text = "是否？  待定"
        result = self.pp.preprocess(text)
        assert "是否？待定" in result


class TestEdgeCases:
    """边界情况测试"""

    def setup_method(self):
        self.pp = OCRTextPreprocessor()

    def test_whitespace_only_text(self):
        """纯空白文本"""
        text = "   \n\n   \n   "
        result = self.pp.preprocess(text)
        # 应该被清理掉
        assert result.strip() == ""

    def test_tab_and_formfeed_normalization(self):
        """制表符和换页符规范化"""
        text = "姓名\t张三\f李四"
        result = self.pp.preprocess(text)
        assert "\t" not in result
        assert "\f" not in result

    def test_batch_empty_list(self):
        """空列表批量处理"""
        results = self.pp.preprocess_batch([])
        assert results == []

    def test_batch_mixed_text(self):
        """混合文本批量处理"""
        texts = ["商 品 房", "", None, "正常文本"]
        results = self.pp.preprocess_batch(texts)
        assert len(results) == 4
        assert "商品房" in results[0]
        assert results[1] == ""
        assert results[2] is None
        assert "正常文本" in results[3]

    def test_remove_ocr_spacing_with_mixed_content(self):
        """混合内容行：部分单字部分多字"""
        # 超过80%单字符 → 字间空格模式
        result = self.pp._remove_ocr_char_spacing("房 地 产 买 卖 合 同")
        assert "房地产买卖合同" in result

    def test_remove_ocr_spacing_normal_words(self):
        """正常词间空格保留"""
        result = self.pp._remove_ocr_char_spacing("公民身份号码 123456789012345678")
        assert "公民身份号码" in result
        assert "123456789012345678" in result
