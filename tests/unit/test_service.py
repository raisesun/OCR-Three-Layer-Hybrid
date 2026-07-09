#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 OCRService 多页处理逻辑（#1 修复核心）

覆盖：
- _get_base_doc_type(): 细分类型 → 基础类型映射
- _extract_multi_page_merge(): 逐页独立分类 + field_config 驱动 + VLM 兜底
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
)


class TestGetBaseDocType:
    """测试 _get_base_doc_type(): 细分类型映射到基础类型"""

    @pytest.fixture
    def service(self):
        """创建一个不初始化外部依赖的 service mock"""
        with patch("ocr_three_layer_hybrid.service.VLMClient"), \
             patch("ocr_three_layer_hybrid.service.KeywordDocumentClassifier"), \
             patch("ocr_three_layer_hybrid.service.VLMExtractionLayer"), \
             patch("ocr_three_layer_hybrid.service.PlanEPlusPipeline"), \
             patch("ocr_three_layer_hybrid.rule_layer.RuleExtractionLayer"):
            from ocr_three_layer_hybrid.service import OCRService
            svc = OCRService.__new__(OCRService)
            return svc

    def test_base_type_unchanged(self, service):
        """基础类型传入时返回自身"""
        assert service._get_base_doc_type(DocumentType.ID_CARD) == DocumentType.ID_CARD
        assert service._get_base_doc_type(DocumentType.MARRIAGE_CERTIFICATE) == DocumentType.MARRIAGE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.DIVORCE_CERTIFICATE) == DocumentType.DIVORCE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.HOUSEHOLD_REGISTER) == DocumentType.HOUSEHOLD_REGISTER
        assert service._get_base_doc_type(DocumentType.PROPERTY_CERTIFICATE) == DocumentType.PROPERTY_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.PURCHASE_CONTRACT) == DocumentType.PURCHASE_CONTRACT
        assert service._get_base_doc_type(DocumentType.STOCK_CONTRACT) == DocumentType.STOCK_CONTRACT
        assert service._get_base_doc_type(DocumentType.FUND_SUPERVISION) == DocumentType.FUND_SUPERVISION

    def test_id_card_subtypes(self, service):
        """身份证子类型 → ID_CARD"""
        assert service._get_base_doc_type(DocumentType.ID_CARD_FRONT) == DocumentType.ID_CARD
        assert service._get_base_doc_type(DocumentType.ID_CARD_BACK) == DocumentType.ID_CARD

    def test_marriage_subtypes(self, service):
        """结婚证子类型 → MARRIAGE_CERTIFICATE"""
        assert service._get_base_doc_type(DocumentType.MARRIAGE_CERTIFICATE_COVER) == DocumentType.MARRIAGE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.MARRIAGE_CERTIFICATE_CONTENT) == DocumentType.MARRIAGE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.MARRIAGE_CERTIFICATE_STAMP) == DocumentType.MARRIAGE_CERTIFICATE

    def test_divorce_subtypes(self, service):
        """离婚证子类型 → DIVORCE_CERTIFICATE"""
        assert service._get_base_doc_type(DocumentType.DIVORCE_CERTIFICATE_COVER) == DocumentType.DIVORCE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.DIVORCE_CERTIFICATE_CONTENT) == DocumentType.DIVORCE_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.DIVORCE_CERTIFICATE_STAMP) == DocumentType.DIVORCE_CERTIFICATE

    def test_household_subtypes(self, service):
        """户口本子类型 → HOUSEHOLD_REGISTER"""
        assert service._get_base_doc_type(DocumentType.HOUSEHOLD_REGISTER_COVER) == DocumentType.HOUSEHOLD_REGISTER
        assert service._get_base_doc_type(DocumentType.HOUSEHOLD_REGISTER_CONTENT) == DocumentType.HOUSEHOLD_REGISTER

    def test_property_subtypes(self, service):
        """不动产权证书子类型 → PROPERTY_CERTIFICATE"""
        assert service._get_base_doc_type(DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE) == DocumentType.PROPERTY_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.PROPERTY_CERTIFICATE_CONTENT) == DocumentType.PROPERTY_CERTIFICATE
        assert service._get_base_doc_type(DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT) == DocumentType.PROPERTY_CERTIFICATE

    def test_purchase_contract_subtypes(self, service):
        """购房合同子类型 → PURCHASE_CONTRACT"""
        assert service._get_base_doc_type(DocumentType.PURCHASE_CONTRACT_FIRST_PAGE) == DocumentType.PURCHASE_CONTRACT
        assert service._get_base_doc_type(DocumentType.PURCHASE_CONTRACT_CONTENT) == DocumentType.PURCHASE_CONTRACT
        assert service._get_base_doc_type(DocumentType.PURCHASE_CONTRACT_STAMP) == DocumentType.PURCHASE_CONTRACT

    def test_stock_contract_subtypes(self, service):
        """存量房合同子类型 → STOCK_CONTRACT"""
        assert service._get_base_doc_type(DocumentType.STOCK_CONTRACT_FIRST_PAGE) == DocumentType.STOCK_CONTRACT
        assert service._get_base_doc_type(DocumentType.STOCK_CONTRACT_CONTENT) == DocumentType.STOCK_CONTRACT
        assert service._get_base_doc_type(DocumentType.STOCK_CONTRACT_STAMP) == DocumentType.STOCK_CONTRACT

    def test_fund_supervision_subtypes(self, service):
        """资金监管协议子类型 → FUND_SUPERVISION"""
        assert service._get_base_doc_type(DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE) == DocumentType.FUND_SUPERVISION
        assert service._get_base_doc_type(DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE) == DocumentType.FUND_SUPERVISION
        assert service._get_base_doc_type(DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP) == DocumentType.FUND_SUPERVISION
        assert service._get_base_doc_type(DocumentType.FUND_SUPERVISION_CERTIFICATE) == DocumentType.FUND_SUPERVISION

    def test_unknown_returns_self(self, service):
        """UNKNOWN 类型返回自身"""
        assert service._get_base_doc_type(DocumentType.UNKNOWN) == DocumentType.UNKNOWN

    def test_all_subtypes_mapped(self, service):
        """验证所有已知的细分类型都有映射"""
        # 所有带后缀的子类型都应该有映射到基础类型
        subtypes = [
            DocumentType.ID_CARD_FRONT, DocumentType.ID_CARD_BACK,
            DocumentType.MARRIAGE_CERTIFICATE_COVER, DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP,
            DocumentType.DIVORCE_CERTIFICATE_COVER, DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            DocumentType.DIVORCE_CERTIFICATE_STAMP,
            DocumentType.HOUSEHOLD_REGISTER_COVER, DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE, DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.PURCHASE_CONTRACT_FIRST_PAGE, DocumentType.PURCHASE_CONTRACT_CONTENT,
            DocumentType.PURCHASE_CONTRACT_STAMP,
            DocumentType.STOCK_CONTRACT_FIRST_PAGE, DocumentType.STOCK_CONTRACT_CONTENT,
            DocumentType.STOCK_CONTRACT_STAMP,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
            DocumentType.FUND_SUPERVISION_CERTIFICATE,
        ]
        for subtype in subtypes:
            base = service._get_base_doc_type(subtype)
            assert base != subtype, f"{subtype} 应该映射到不同的基础类型"
            # 基础类型不应在子类型列表中
            assert base not in subtypes


class TestVlmFallbackForPage:
    """测试 _vlm_fallback_for_page: 单页 VLM 兜底"""

    @pytest.fixture
    def service(self):
        """创建一个带 mock pipeline 的 service"""
        with patch("ocr_three_layer_hybrid.service.VLMClient"), \
             patch("ocr_three_layer_hybrid.service.KeywordDocumentClassifier"), \
             patch("ocr_three_layer_hybrid.service.VLMExtractionLayer"), \
             patch("ocr_three_layer_hybrid.rule_layer.RuleExtractionLayer"):
            from ocr_three_layer_hybrid.service import OCRService
            svc = OCRService.__new__(OCRService)
            # Mock pipeline
            mock_pipeline = Mock()
            mock_vlm_layer = Mock()
            mock_pipeline._get_layer.return_value = mock_vlm_layer
            svc._pipeline = mock_pipeline
            svc._vlm_fallback_handler = None
            return svc

    def test_vlm_fallback_success(self, service):
        """VLM 兜底成功"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            ocr_texts=["离婚证字号 L12345"],
        )
        vlm_result = ExtractionResult(
            doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            layer=ProcessingLayer.VLM,
            fields={"离婚证字号": "L12345", "持证人身份证件号": "340123199001011234"},
            success=True,
        )
        service._pipeline._get_layer.return_value.extract.return_value = vlm_result

        result = service._vlm_fallback_for_page(doc_info, ["离婚证字号", "持证人身份证件号"])
        assert result is not None
        assert result.success is True
        assert result.fields["离婚证字号"] == "L12345"

    def test_vlm_fallback_no_vlm_layer(self, service):
        """没有 VLM 层时返回 None"""
        doc_info = DocumentInfo(image_path="/tmp/test.jpg", doc_type=DocumentType.UNKNOWN)
        service._pipeline._get_layer.return_value = None

        result = service._vlm_fallback_for_page(doc_info, ["字段A"])
        assert result is None

    def test_vlm_fallback_exception_returns_none(self, service):
        """VLM 兜底异常时返回 None"""
        doc_info = DocumentInfo(image_path="/tmp/test.jpg", doc_type=DocumentType.UNKNOWN)
        service._pipeline._get_layer.return_value.extract.side_effect = Exception("VLM 超时")

        result = service._vlm_fallback_for_page(doc_info, ["字段A"])
        assert result is None


class TestProcessMultiPageEmpty:
    """测试 process_multi_page 空输入处理"""

    @pytest.fixture
    def service(self):
        with patch("ocr_three_layer_hybrid.service.VLMClient"), \
             patch("ocr_three_layer_hybrid.service.KeywordDocumentClassifier"), \
             patch("ocr_three_layer_hybrid.service.VLMExtractionLayer"), \
             patch("ocr_three_layer_hybrid.service.PlanEPlusPipeline"), \
             patch("ocr_three_layer_hybrid.rule_layer.RuleExtractionLayer"):
            from ocr_three_layer_hybrid.service import OCRService
            svc = OCRService.__new__(OCRService)
            return svc

    def test_empty_image_paths(self, service):
        """空图片列表返回失败"""
        result = service.process_multi_page([])
        assert result["extraction"]["success"] is False
        assert result["extraction"]["error_message"] == "没有图片"
        assert result["timing"]["total_ms"] == 0
