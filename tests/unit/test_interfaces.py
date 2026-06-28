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
        assert ProcessingLayer.LLM == "llm"


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
