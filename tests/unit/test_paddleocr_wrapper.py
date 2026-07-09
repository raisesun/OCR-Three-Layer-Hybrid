#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""paddleocr_wrapper 单元测试

注意：完整测试需要 PaddleOCR，这里只测试数据结构和引擎选择逻辑。
"""

import json
import numpy as np
import pytest

from ocr_three_layer_hybrid.paddleocr_wrapper import (
    LayoutRegion,
    OCRResult,
    PaddleOCRWrapper,
    LAYOUT_LABELS,
    OCR_REGION_LABELS,
    SKIP_REGION_LABELS,
)


class TestLayoutRegion:
    """LayoutRegion 数据类测试"""

    def test_creation(self):
        region = LayoutRegion(
            label="text",
            score=0.95,
            coordinate=[10, 20, 100, 50],
            order=1,
            polygon_points=[[10, 20], [100, 20], [100, 50], [10, 50]],
        )
        assert region.label == "text"
        assert region.score == 0.95
        assert region.order == 1

    def test_to_dict(self):
        region = LayoutRegion(
            label="table",
            score=0.87654321,
            coordinate=[0, 0, 100, 100],
            order=0,
            polygon_points=[],
        )
        d = region.to_dict()
        assert d["label"] == "table"
        assert d["score"] == 0.8765  # 四舍五入到4位
        assert d["coordinate"] == [0, 0, 100, 100]
        assert d["order"] == 0


class TestOCRResult:
    """OCRResult 数据类测试"""

    def test_full_text_simple(self):
        """简单文本拼接"""
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=["第一行", "第二行", "第三行"],
            rec_scores=[0.9, 0.8, 0.7],
        )
        assert result.full_text == "第一行\n第二行\n第三行"

    def test_full_text_with_grouped_blocks(self):
        """带分组块的文本拼接"""
        region = LayoutRegion("text", 0.9, [0, 0, 1, 1], 0, [])
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=[],
            rec_scores=[],
            grouped_blocks=[
                {"region": region, "texts": ["文本1", "文本2"]},
                {"region": region, "texts": ["文本3"]},
            ],
        )
        assert "文本1" in result.full_text
        assert "文本3" in result.full_text

    def test_full_text_skip_seal_region(self):
        """跳过印章区域"""
        seal_region = LayoutRegion("seal", 0.9, [0, 0, 1, 1], 0, [])
        text_region = LayoutRegion("text", 0.9, [0, 0, 1, 1], 0, [])
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=[],
            rec_scores=[],
            grouped_blocks=[
                {"region": text_region, "texts": ["正常文本"]},
                {"region": seal_region, "texts": ["印章内容"]},
            ],
        )
        assert "正常文本" in result.full_text
        assert "印章内容" not in result.full_text

    def test_blocks_property(self):
        """blocks 属性"""
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=["文本1", "文本2"],
            rec_scores=[0.9, 0.8],
            rec_polys=[np.array([[10, 20], [100, 20], [100, 50], [10, 50]]),
                       np.array([[10, 60], [100, 60], [100, 90], [10, 90]])],
        )
        blocks = result.blocks
        assert len(blocks) == 2
        assert blocks[0]["text"] == "文本1"
        assert blocks[0]["score"] == 0.9
        assert len(blocks[0]["bbox"]) == 4  # [x1, y1, x2, y2]

    def test_to_dict(self):
        """to_dict 转换"""
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=["文本"],
            rec_scores=[0.9],
            rec_polys=[np.array([[0, 0], [10, 0], [10, 10], [0, 10]])],
        )
        d = result.to_dict()
        assert d["input_path"] == "test.jpg"
        assert "文本" in d["full_text"]
        assert len(d["texts"]) == 1

    def test_to_json(self):
        """to_json 序列化"""
        result = OCRResult(
            input_path="test.jpg",
            rec_texts=["测试"],
            rec_scores=[0.95],
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["input_path"] == "test.jpg"
        assert "测试" in parsed["full_text"]

    def test_get_text_by_region(self):
        """按区域获取文本"""
        text_region = LayoutRegion("text", 0.9, [0, 0, 100, 100], 0, [])
        table_region = LayoutRegion("table", 0.9, [0, 100, 100, 200], 1, [])

        result = OCRResult(
            input_path="test.jpg",
            rec_texts=["普通文本", "表格内容"],
            rec_scores=[0.9, 0.8],
            rec_polys=[np.array([[10, 10], [90, 10], [90, 90], [10, 90]]),
                       np.array([[10, 110], [90, 110], [90, 190], [10, 190]])],
            layout_regions=[text_region, table_region],
        )
        text_blocks = result.get_text_by_region("text")
        assert "普通文本" in text_blocks


class TestConstants:
    """常量测试"""

    def test_layout_labels_not_empty(self):
        assert len(LAYOUT_LABELS) > 0

    def test_ocr_region_labels_subset(self):
        """OCR 区域标签是版面标签的子集"""
        assert OCR_REGION_LABELS.issubset(LAYOUT_LABELS)

    def test_skip_region_labels_subset(self):
        """跳过区域标签是版面标签的子集"""
        assert SKIP_REGION_LABELS.issubset(LAYOUT_LABELS)

    def test_ocr_and_skip_disjoint(self):
        """OCR 区域和跳过区域不重叠"""
        assert OCR_REGION_LABELS.isdisjoint(SKIP_REGION_LABELS)


class TestPaddleOCRWrapperSelectEngine:
    """PaddleOCRWrapper._select_engine 引擎选择测试"""

    def test_default_engine_override(self):
        """指定默认引擎"""
        wrapper = PaddleOCRWrapper(default_engine="vlm")
        assert wrapper._select_engine("身份证") == "vlm"

    def test_auto_select_fast_doc(self):
        """自动选择：快速文档类型 → ppocr"""
        wrapper = PaddleOCRWrapper(default_engine="auto")
        assert wrapper._select_engine("身份证") == "ppocr"
        assert wrapper._select_engine("户口本") == "ppocr"
        assert wrapper._select_engine("结婚证") == "ppocr"

    def test_auto_select_slow_doc(self):
        """自动选择：慢速文档类型 → vlm"""
        wrapper = PaddleOCRWrapper(default_engine="auto")
        assert wrapper._select_engine("购房合同") == "vlm"
        assert wrapper._select_engine("离婚协议") == "vlm"

    def test_auto_select_none_doc_type(self):
        """自动选择：未知文档类型 → vlm"""
        wrapper = PaddleOCRWrapper(default_engine="auto")
        assert wrapper._select_engine(None) == "vlm"
        assert wrapper._select_engine("未知") == "vlm"
