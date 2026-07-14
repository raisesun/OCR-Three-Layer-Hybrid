#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试接口和基础数据结构
"""

import pytest
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    ProcessingLayer,
    DocumentInfo,
    ExtractionResult,
    FieldStatus,
    FieldDetail,
    FieldConflict,
)


class TestDocumentType:
    def test_document_type_values(self):
        assert DocumentType.ID_CARD == "身份证"
        assert DocumentType.MARRIAGE_CERTIFICATE == "结婚证"
        assert DocumentType.HOUSEHOLD_REGISTER == "户口本"
        assert DocumentType.PURCHASE_CONTRACT == "购房合同"


class TestProcessingLayer:
    def test_processing_layer_values(self):
        assert ProcessingLayer.RULE == "rule"
        assert ProcessingLayer.VLM == "vlm"
        # LLM 层已在 v2.0 中移除


class TestDocumentInfo:
    def test_default_values(self):
        info = DocumentInfo(image_path="/tmp/test.jpg")
        assert info.image_path == "/tmp/test.jpg"
        assert info.doc_type == DocumentType.UNKNOWN
        assert info.ocr_texts == []
        assert info.confidence == 0.0

    def test_with_ocr_texts(self):
        info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=["姓名", "张三"],
            confidence=0.95,
        )
        assert info.doc_type == DocumentType.ID_CARD
        assert info.ocr_texts == ["姓名", "张三"]
        assert info.confidence == 0.95


class TestExtractionResult:
    def test_default_values(self):
        result = ExtractionResult(
            doc_type=DocumentType.ID_CARD,
            layer=ProcessingLayer.RULE,
        )
        assert result.doc_type == DocumentType.ID_CARD
        assert result.layer == ProcessingLayer.RULE
        assert result.fields == {}
        assert result.success is True
        assert result.time_cost == 0.0

    def test_get_field(self):
        result = ExtractionResult(
            doc_type=DocumentType.ID_CARD,
            layer=ProcessingLayer.RULE,
            fields={"姓名": "张三"},
        )
        assert result.get("姓名") == "张三"
        assert result.get("不存在") == ""
        assert result.get("不存在", "默认") == "默认"


class TestFieldStatus:
    """测试 FieldStatus 枚举"""

    def test_status_values(self):
        """测试三种状态值"""
        assert FieldStatus.EXTRACTED.value == "extracted"
        assert FieldStatus.LOCATED_EMPTY.value == "located_empty"
        assert FieldStatus.NOT_FOUND.value == "not_found"

    def test_status_is_str_enum(self):
        """测试是字符串枚举"""
        assert isinstance(FieldStatus.EXTRACTED, str)
        assert FieldStatus.EXTRACTED == "extracted"


class TestFieldDetail:
    """测试 FieldDetail 数据类"""

    def test_default_values(self):
        """测试默认值"""
        detail = FieldDetail(name="姓名")
        assert detail.name == "姓名"
        assert detail.value == ""
        assert detail.status == FieldStatus.NOT_FOUND

    def test_extracted_status(self):
        """测试已提取状态"""
        detail = FieldDetail(name="姓名", value="张三", status=FieldStatus.EXTRACTED)
        assert detail.value == "张三"
        assert detail.status == FieldStatus.EXTRACTED

    def test_located_empty_status(self):
        """测试定位但值为空状态"""
        detail = FieldDetail(name="户主姓名", value="", status=FieldStatus.LOCATED_EMPTY)
        assert detail.value == ""
        assert detail.status == FieldStatus.LOCATED_EMPTY


class TestFieldConflict:
    """测试 FieldConflict 数据类"""

    def test_create_conflict(self):
        """测试创建冲突记录"""
        conflict = FieldConflict(
            field_name="总价款",
            source_a_value="100万",
            source_b_value="120万",
            source_a_page="first_page",
            source_b_page="content",
            resolved_value="100万",
        )
        assert conflict.field_name == "总价款"
        assert conflict.source_a_value == "100万"
        assert conflict.resolved_value == "100万"


class TestExtractionResultExtended:
    """测试 ExtractionResult 扩展字段"""

    def test_vlm_fallback_defaults(self):
        """测试 VLM 兜底相关默认值"""
        result = ExtractionResult(
            doc_type=DocumentType.ID_CARD,
            layer=ProcessingLayer.RULE,
        )
        assert result.vlm_fallback_triggered is False
        assert result.vlm_fallback_fields == []
        assert result.field_conflicts == []
        assert result.field_details == []

    def test_vlm_fallback_triggered(self):
        """测试 VLM 兜底触发标记"""
        result = ExtractionResult(
            doc_type=DocumentType.DIVORCE_CERTIFICATE,
            layer=ProcessingLayer.RULE,
            vlm_fallback_triggered=True,
            vlm_fallback_fields=["离婚证字号", "持证人身份证件号"],
        )
        assert result.vlm_fallback_triggered is True
        assert len(result.vlm_fallback_fields) == 2

    def test_field_details(self):
        """测试字段明细列表"""
        result = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER_COVER,
            layer=ProcessingLayer.RULE,
            field_details=[
                FieldDetail(name="户主姓名", value="张三", status=FieldStatus.EXTRACTED),
                FieldDetail(name="户号", value="", status=FieldStatus.LOCATED_EMPTY),
                FieldDetail(name="住址", value="", status=FieldStatus.NOT_FOUND),
            ],
        )
        assert len(result.field_details) == 3
        assert result.field_details[0].status == FieldStatus.EXTRACTED
        assert result.field_details[1].status == FieldStatus.LOCATED_EMPTY
        assert result.field_details[2].status == FieldStatus.NOT_FOUND

    def test_has_conflicts(self):
        """测试冲突检测"""
        result = ExtractionResult(
            doc_type=DocumentType.PURCHASE_CONTRACT,
            layer=ProcessingLayer.RULE,
            field_conflicts=[
                FieldConflict(
                    field_name="总价款",
                    source_a_value="100万",
                    source_b_value="120万",
                ),
            ],
        )
        assert result.has_conflicts() is True

    def test_get_conflict_summary(self):
        """测试冲突摘要"""
        result = ExtractionResult(
            doc_type=DocumentType.PURCHASE_CONTRACT,
            layer=ProcessingLayer.RULE,
            field_conflicts=[
                FieldConflict(
                    field_name="总价款",
                    source_a_value="100万",
                    source_b_value="120万",
                    source_a_page="first_page",
                    source_b_page="content",
                ),
            ],
        )
        summary = result.get_conflict_summary()
        assert len(summary) == 1
        assert summary[0]["field"] == "总价款"
        assert summary[0]["resolved_value"] == "100万"
