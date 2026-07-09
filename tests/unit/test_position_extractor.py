#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""position_extractor 单元测试

注意：完整的位置标注提取需要 PaddleOCR，这里只测试不依赖 OCR 的纯逻辑。
"""

import pytest

from ocr_three_layer_hybrid.position_extractor import (
    OcrItem,
    HouseholdPositionExtractor,
)


class TestOcrItem:
    """OcrItem 数据类测试"""

    def test_basic_creation(self):
        item = OcrItem(text="测试", score=0.9, x1=0.1, y1=0.2, x2=0.3, y2=0.4)
        assert item.text == "测试"
        assert item.score == 0.9

    def test_default_relative_coords(self):
        item = OcrItem(text="测试", score=0.9, x1=0.1, y1=0.2, x2=0.3, y2=0.4)
        assert item.rx1 == 0.0
        assert item.ry1 == 0.0

    def test_rcx(self):
        """文档相对 X 中心"""
        item = OcrItem(
            text="测试", score=0.9,
            x1=0.1, y1=0.2, x2=0.3, y2=0.4,
            rx1=0.2, ry1=0.3, rx2=0.6, ry2=0.7,
        )
        assert item.rcx == pytest.approx(0.4)  # (0.2 + 0.6) / 2

    def test_rcy(self):
        """文档相对 Y 中心"""
        item = OcrItem(
            text="测试", score=0.9,
            x1=0.1, y1=0.2, x2=0.3, y2=0.4,
            rx1=0.2, ry1=0.3, rx2=0.6, ry2=0.7,
        )
        assert item.rcy == pytest.approx(0.5)  # (0.3 + 0.7) / 2


class TestStripLabel:
    """_strip_label 标签剥离测试"""

    def setup_method(self):
        self.extractor = HouseholdPositionExtractor()

    def test_strip_huzhu_xingming(self):
        """剥离「户主姓名」前缀"""
        assert self.extractor._strip_label("户主姓名张三") == "张三"

    def test_strip_huhao(self):
        """剥离「户号」前缀"""
        assert self.extractor._strip_label("户号7314") == "7314"

    def test_strip_hubie(self):
        """剥离「户别」前缀"""
        assert self.extractor._strip_label("户别非农业家庭户") == "非农业家庭户"

    def test_strip_trailing_kou(self):
        """剥离末尾「口」字"""
        result = self.extractor._strip_label("非农业家庭户口")
        assert result == "非农业家庭户"

    def test_no_strip_clean_text(self):
        """干净文本不被剥离"""
        assert self.extractor._strip_label("张三") == "张三"


class TestFixAddressOrder:
    """_fix_address_order 地址顺序修正测试"""

    def setup_method(self):
        self.extractor = HouseholdPositionExtractor()

    def test_fix_short_prefix(self):
        """短前缀移到末尾"""
        result = self.extractor._fix_address_order("曹台子74号安徽省蚌埠市蚌山区燕山乡")
        assert result == "安徽省蚌埠市蚌山区燕山乡曹台子74号"

    def test_no_fix_normal_address(self):
        """正常地址不修正"""
        addr = "安徽省蚌埠市蚌山区燕山乡定安村张庄219号"
        result = self.extractor._fix_address_order(addr)
        assert result == addr

    def test_no_fix_short_rest(self):
        """rest 太短不修正"""
        result = self.extractor._fix_address_order("74号短")
        assert result == "74号短"  # 不修正


class TestIsFirstPage:
    """is_first_page 首页检测测试"""

    def setup_method(self):
        self.extractor = HouseholdPositionExtractor()

    def test_first_page_with_keyword(self):
        """包含首页关键词"""
        items = [
            OcrItem(text="注意事项", score=0.9, x1=0, y1=0, x2=1, y2=1),
            OcrItem(text="其他内容", score=0.9, x1=0, y1=0, x2=1, y2=1),
        ]
        assert self.extractor.is_first_page(items) is True

    def test_not_first_page(self):
        """不包含首页关键词"""
        items = [
            OcrItem(text="常住人口登记卡", score=0.9, x1=0, y1=0, x2=1, y2=1),
            OcrItem(text="姓名 张三", score=0.9, x1=0, y1=0, x2=1, y2=1),
        ]
        assert self.extractor.is_first_page(items) is False

    def test_empty_items(self):
        """空列表"""
        assert self.extractor.is_first_page([]) is False


class TestIsLabel:
    """_is_label 标签判断测试"""

    def setup_method(self):
        self.extractor = HouseholdPositionExtractor()

    def test_is_label_hubie(self):
        assert self.extractor._is_label("户别") is True

    def test_is_label_huhao(self):
        assert self.extractor._is_label("户号") is True

    def test_not_label_data(self):
        assert self.extractor._is_label("非农业家庭户") is False

    def test_not_label_name(self):
        assert self.extractor._is_label("张三") is False


class TestMergeAdjacentItems:
    """_merge_adjacent_items 合并相邻文本测试"""

    def setup_method(self):
        self.extractor = HouseholdPositionExtractor()

    def test_merge_close_same_row(self):
        """同行相邻文本合并"""
        items = [
            OcrItem(text="户", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.10, ry1=0.55, rx2=0.15, ry2=0.60),
            OcrItem(text="别", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.16, ry1=0.55, rx2=0.20, ry2=0.60),
        ]
        merged = self.extractor._merge_adjacent_items(items)
        assert len(merged) == 1
        assert merged[0].text == "户别"

    def test_no_merge_different_row(self):
        """不同行不合并"""
        items = [
            OcrItem(text="户别", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.10, ry1=0.55, rx2=0.20, ry2=0.60),
            OcrItem(text="户号", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.10, ry1=0.65, rx2=0.20, ry2=0.70),
        ]
        merged = self.extractor._merge_adjacent_items(items)
        assert len(merged) == 2

    def test_no_merge_far_apart(self):
        """间距太大不合并"""
        items = [
            OcrItem(text="户别", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.10, ry1=0.55, rx2=0.15, ry2=0.60),
            OcrItem(text="户号", score=0.9, x1=0, y1=0, x2=1, y2=1,
                    rx1=0.50, ry1=0.55, rx2=0.55, ry2=0.60),
        ]
        merged = self.extractor._merge_adjacent_items(items)
        assert len(merged) == 2

    def test_empty_items(self):
        """空列表"""
        assert self.extractor._merge_adjacent_items([]) == []
