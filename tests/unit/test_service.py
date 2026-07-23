#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 OCRService 多页处理逻辑（#1 修复核心）

覆盖：
- _get_base_doc_type(): 细分类型 → 基础类型映射
- _extract_multi_page_merge(): 逐页独立分类 + field_config 驱动 + VLM 兜底
"""

import os
import pytest
from pathlib import Path
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


class TestMultiPageTypeInheritance:
    """方案C: 多页协同 - UNKNOWN页从首页继承基础类型"""

    @pytest.fixture
    def service(self):
        mock_path_cls = Mock()
        mock_path_inst = Mock()
        mock_path_inst.exists.return_value = True
        mock_path_cls.return_value = mock_path_inst
        with patch("ocr_three_layer_hybrid.service.VLMClient"), \
             patch("ocr_three_layer_hybrid.service.KeywordDocumentClassifier"), \
             patch("ocr_three_layer_hybrid.service.VLMExtractionLayer"), \
             patch("ocr_three_layer_hybrid.service.PlanEPlusPipeline"), \
             patch("ocr_three_layer_hybrid.rule_layer.RuleExtractionLayer"), \
             patch("ocr_three_layer_hybrid.multi_page_utils.Path", mock_path_cls):
            from ocr_three_layer_hybrid.service import OCRService
            svc = OCRService.__new__(OCRService)
            svc._classifier = Mock()
            svc._pipeline = Mock()
            svc.run_ocr = Mock(return_value="mock ocr text")
            yield svc

    def test_unknown_page_inherits_first_page_type(self, service):
        """后续页UNKNOWN + 首页高置信度 -> 继承首页基础类型"""
        first_doc = DocumentInfo(
            image_path="img1.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.95,
        )
        service._classifier.classify.return_value = DocumentInfo(
            image_path="img2.jpg",
            doc_type=DocumentType.UNKNOWN,
            confidence=0.0,
        )
        service._pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )
        service._extract_multi_page_merge(["img1.jpg", "img2.jpg"], first_doc)
        calls = service._pipeline.process.call_args_list
        assert len(calls) >= 2
        second_doc = calls[1].kwargs["doc_info"]
        # 继承后应为细分类型 HOUSEHOLD_REGISTER_CONTENT（与首页相同）
        assert second_doc.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT
        assert second_doc.metadata.get("inherited_from_first_page") is True
        # 置信度应为首页 * 0.9
        assert abs(second_doc.confidence - 0.95 * 0.9) < 0.01

    def test_unknown_page_no_inherit_low_confidence(self, service):
        """首页置信度 < 0.85 -> 不继承，保持UNKNOWN"""
        first_doc = DocumentInfo(
            image_path="img1.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.7,
        )
        service._classifier.classify.return_value = DocumentInfo(
            image_path="img2.jpg",
            doc_type=DocumentType.UNKNOWN,
            confidence=0.0,
        )
        service._pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.UNKNOWN,
            layer=ProcessingLayer.VLM,
            fields={},
            success=True,
        )
        service._extract_multi_page_merge(["img1.jpg", "img2.jpg"], first_doc)
        calls = service._pipeline.process.call_args_list
        assert len(calls) >= 2
        second_doc = calls[1].kwargs["doc_info"]
        # 不继承，仍是 UNKNOWN
        assert second_doc.doc_type == DocumentType.UNKNOWN
        assert not second_doc.metadata.get("inherited_from_first_page")

    def test_unknown_page_no_inherit_first_page_unknown(self, service):
        """首页本身是UNKNOWN -> 不继承（首页基础类型也是UNKNOWN）"""
        first_doc = DocumentInfo(
            image_path="img1.jpg",
            doc_type=DocumentType.UNKNOWN,
            confidence=0.95,
        )
        service._classifier.classify.return_value = DocumentInfo(
            image_path="img2.jpg",
            doc_type=DocumentType.UNKNOWN,
            confidence=0.0,
        )
        service._pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.UNKNOWN,
            layer=ProcessingLayer.VLM,
            fields={},
            success=True,
        )
        service._extract_multi_page_merge(["img1.jpg", "img2.jpg"], first_doc)
        calls = service._pipeline.process.call_args_list
        assert len(calls) >= 2
        second_doc = calls[1].kwargs["doc_info"]
        # 首页UNKNOWN -> _get_base_doc_type返回UNKNOWN -> 不继承
        assert second_doc.doc_type == DocumentType.UNKNOWN
        assert not second_doc.metadata.get("inherited_from_first_page")

    def test_non_unknown_page_no_inheritance(self, service):
        """后续页不是UNKNOWN -> 不触发继承，保持原分类"""
        first_doc = DocumentInfo(
            image_path="img1.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.95,
        )
        # 后续页正常分类为户口本内容页（不是UNKNOWN）
        service._classifier.classify.return_value = DocumentInfo(
            image_path="img2.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.9,
        )
        service._pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )
        service._extract_multi_page_merge(["img1.jpg", "img2.jpg"], first_doc)
        calls = service._pipeline.process.call_args_list
        assert len(calls) >= 2
        second_doc = calls[1].kwargs["doc_info"]
        # 保持原分类 HOUSEHOLD_REGISTER_CONTENT，不继承
        assert second_doc.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT
        assert not second_doc.metadata.get("inherited_from_first_page")

    def test_ocr_called_once_per_page(self, service):
        """H1: 多页处理每页只 OCR 一次（修复前 3 次/2页，修复后 2 次/2页）"""
        first_doc = DocumentInfo(
            image_path="img1.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.95,
        )
        service._classifier.classify.return_value = DocumentInfo(
            image_path="img2.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            confidence=0.9,
        )
        service._pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )
        service._extract_multi_page_merge(["img1.jpg", "img2.jpg"], first_doc)
        # 2 页 -> run_ocr 调用 2 次（每页一次）；修复前为 3 次（首页1 + 后续页2）
        assert service.run_ocr.call_count == 2


class TestBuildClassificationDict:
    """测试 _build_classification_dict 静态方法"""

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

    def test_basic_classification(self, service):
        """基础分类信息构建"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            confidence=0.95,
        )
        doc_info.metadata["route"] = "standard_certificate"
        doc_info.metadata["signal"] = "户口簿+户主"

        result = service._build_classification_dict(doc_info)
        assert result["doc_type"] == DocumentType.HOUSEHOLD_REGISTER.value
        assert result["confidence"] == 0.95
        assert result["route"] == "standard_certificate"
        assert result["route_name"] == "阶段1: 标准证件强信号"
        assert result["signal"] == "户口簿+户主"

    def test_unknown_route(self, service):
        """未知 route 返回自身"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.UNKNOWN,
            confidence=0.5,
        )
        doc_info.metadata["route"] = "unknown_route"

        result = service._build_classification_dict(doc_info)
        assert result["route"] == "unknown_route"
        assert result["route_name"] == "unknown_route"  # 找不到映射则返回原值

    def test_attachment_metadata(self, service):
        """附件标记"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            confidence=0.8,
        )
        doc_info.metadata["route"] = "standard_certificate"
        doc_info.metadata["is_attachment"] = True

        result = service._build_classification_dict(doc_info)
        assert result["is_attachment"] is True


class TestBuildPipelineFlow:
    """测试 _build_pipeline_flow 静态方法"""

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

    def test_standard_certificate_route(self, service):
        """标准证件路由"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.ID_CARD,
        )
        doc_info.metadata["route"] = "standard_certificate"
        doc_info.metadata["signal"] = "公民身份号码"

        result = ExtractionResult(
            doc_type=DocumentType.ID_CARD,
            layer=ProcessingLayer.RULE,
            fields={"姓名": "张三"},
            success=True,
        )

        flow = service._build_pipeline_flow(doc_info, result)
        assert flow["active_stage"] == "stage1"
        assert flow["stage_match_info"] == "公民身份号码"
        assert flow["extraction_layer"] == ProcessingLayer.RULE.value
        assert flow["doc_type"] == DocumentType.ID_CARD.value
        assert "stages" in flow
        assert "layer_color" in flow

    def test_vlm_fallback_route(self, service):
        """VLM兜底路由"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.UNKNOWN,
        )
        doc_info.metadata["route"] = "vlm_fallback_required"
        doc_info.metadata["vlm_result"] = "提取完成"

        result = ExtractionResult(
            doc_type=DocumentType.UNKNOWN,
            layer=ProcessingLayer.VLM,
            fields={},
            success=True,
        )

        flow = service._build_pipeline_flow(doc_info, result)
        assert flow["active_stage"] == "stage4"
        assert flow["stage_match_info"] == "提取完成"
        assert flow["extraction_layer"] == ProcessingLayer.VLM.value
        assert flow["doc_type"] == DocumentType.UNKNOWN.value

    def test_no_layer(self, service):
        """无提取层"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.UNKNOWN,
        )
        doc_info.metadata["route"] = ""

        result = ExtractionResult(
            doc_type=DocumentType.UNKNOWN,
            layer=None,
            fields={},
            success=False,
        )

        flow = service._build_pipeline_flow(doc_info, result)
        assert flow["extraction_layer"] == "none"
        assert flow["active_stage"] is None

    def test_contract_route(self, service):
        """合同字段组合路由"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.PURCHASE_CONTRACT,
        )
        doc_info.metadata["route"] = "contract_field_combination"

        result = ExtractionResult(
            doc_type=DocumentType.PURCHASE_CONTRACT,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )

        flow = service._build_pipeline_flow(doc_info, result)
        assert flow["active_stage"] == "stage3"
        assert flow["stage_match_info"] == "合同字段匹配"

    def test_backup_certificate_route(self, service):
        """备选强信号路由"""
        doc_info = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
        )
        doc_info.metadata["route"] = "backup_certificate"
        doc_info.metadata["primary"] = ["户口簿"]
        doc_info.metadata["required"] = ["户主"]

        result = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )

        flow = service._build_pipeline_flow(doc_info, result)
        assert flow["active_stage"] == "stage1_5"
        assert "户口簿" in flow["stage_match_info"]
        assert "户主" in flow["stage_match_info"]


class TestSetupLogging:
    """测试 setup_logging 函数"""

    def test_setup_logging_basic(self):
        """基础日志配置不报错"""
        from ocr_three_layer_hybrid.service import setup_logging
        setup_logging(level="DEBUG")

    def test_setup_logging_with_file(self):
        """文件日志配置"""
        import tempfile
        from ocr_three_layer_hybrid.service import setup_logging

        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = f.name

        try:
            setup_logging(level="INFO", log_file=log_path)
            # 日志文件应该存在
            assert os.path.exists(log_path)
        finally:
            if os.path.exists(log_path):
                os.unlink(log_path)
