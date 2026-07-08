#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试方案E+编排管道
"""

import pytest
from unittest.mock import Mock
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    ProcessingLayer,
    DocumentInfo,
    ExtractionResult,
)


class TestPlanEPlusPipeline:
    @pytest.fixture
    def pipeline(self):
        return PlanEPlusPipeline()

    def test_default_layer_routing(self, pipeline):
        assert pipeline.get_layer_for_doc_type(DocumentType.ID_CARD) == ProcessingLayer.RULE
        assert pipeline.get_layer_for_doc_type(DocumentType.MARRIAGE_CERTIFICATE) == ProcessingLayer.RULE
        assert pipeline.get_layer_for_doc_type(DocumentType.HOUSEHOLD_REGISTER) == ProcessingLayer.RULE  # 已改为规则层
        assert pipeline.get_layer_for_doc_type(DocumentType.PROPERTY_CERTIFICATE) == ProcessingLayer.RULE  # 已改为规则层
        assert pipeline.get_layer_for_doc_type(DocumentType.INVOICE) == ProcessingLayer.RULE  # 新增
        assert pipeline.get_layer_for_doc_type(DocumentType.PURCHASE_CONTRACT) == ProcessingLayer.RULE  # 已改为规则层
        assert pipeline.get_layer_for_doc_type(DocumentType.STOCK_CONTRACT) == ProcessingLayer.RULE  # 已改为规则层
        assert pipeline.get_layer_for_doc_type(DocumentType.FUND_SUPERVISION) == ProcessingLayer.RULE  # 新增
        assert pipeline.get_layer_for_doc_type(DocumentType.UNKNOWN) == ProcessingLayer.VLM  # VLM兜底

    def test_process_id_card_routes_to_rule_layer(self, pipeline):
        ocr_texts = ["姓名 张三", "公民身份号码 110101199001011234"]
        result = pipeline.process("/tmp/id.jpg", ocr_texts)

        assert result.success is True
        # 现在会识别为身份证正面
        assert result.doc_type == DocumentType.ID_CARD_FRONT
        assert result.layer == ProcessingLayer.RULE
        assert result.fields["姓名"] == "张三"
        assert result.fields["公民身份号码"] == "110101199001011234"

    def test_process_marriage_certificate_routes_to_rule_layer(self, pipeline):
        ocr_texts = ["结婚证", "持证人 张三", "结婚证字号 J12345"]
        result = pipeline.process("/tmp/marriage.jpg", ocr_texts)

        assert result.success is True
        # 现在会识别为结婚证内容页
        assert result.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT
        assert result.layer == ProcessingLayer.RULE
        assert result.fields["持证人"] == "张三"
        assert result.fields["结婚证字号"] == "J12345"

    def test_process_unknown_document_no_layer(self, pipeline):
        ocr_texts = ["不相关文本"]
        result = pipeline.process("/tmp/unknown.jpg", ocr_texts)

        assert result.success is False
        assert result.doc_type == DocumentType.UNKNOWN
        assert "没有可用的" in result.error_message

    def test_process_purchase_contract_no_llm_layer(self, pipeline):
        """没有配置LLM层时，购房合同应该由规则层处理"""
        ocr_texts = ["商品房买卖合同", "买受人 张三", "出卖人 李四", "总价款 1000000"]
        result = pipeline.process("/tmp/contract.jpg", ocr_texts)

        # 购房合同现在由规则层处理（不需要LLM层）
        assert result.success is True
        assert result.doc_type == DocumentType.PURCHASE_CONTRACT
        assert result.layer == ProcessingLayer.RULE

    def test_process_with_mock_llm_layer(self):
        """使用mock LLM层测试购房合同流程（现在购房合同由规则层处理）"""
        # 由于购房合同现在由规则层处理，这个测试改为测试UNKNOWN文档的VLM兜底
        mock_vlm_layer = Mock()
        mock_vlm_layer.can_process.return_value = True
        mock_vlm_layer.extract.return_value = ExtractionResult(
            doc_type=DocumentType.UNKNOWN,
            layer=ProcessingLayer.VLM,
            fields={"文档类型": "合同", "金额": "1000000"},
            success=True,
            time_cost=2.0,
        )

        pipeline = PlanEPlusPipeline(vlm_layer=mock_vlm_layer)
        ocr_texts = ["不相关文本"]  # 无法分类的文档
        result = pipeline.process("/tmp/unknown.jpg", ocr_texts)

        assert result.success is True
        assert result.doc_type == DocumentType.UNKNOWN
        assert result.layer == ProcessingLayer.VLM
        assert result.fields["金额"] == "1000000"

        # 验证VLM层被正确调用
        mock_vlm_layer.can_process.assert_called_once()
        mock_vlm_layer.extract.assert_called_once()

    def test_process_with_custom_key_list(self, pipeline):
        ocr_texts = ["姓名 张三", "公民身份号码 110101199001011234", "性别 男"]
        result = pipeline.process(
            "/tmp/id.jpg",
            ocr_texts,
            key_list=["姓名"],
        )

        assert "姓名" in result.fields
        assert result.fields["姓名"] == "张三"
        assert "性别" not in result.fields

    def test_process_force_layer(self, pipeline):
        """测试强制指定处理层"""
        ocr_texts = ["姓名 张三", "公民身份号码 110101199001011234"]
        result = pipeline.process(
            "/tmp/id.jpg",
            ocr_texts,
            force_layer=ProcessingLayer.RULE,
        )

        assert result.success is True
        assert result.layer == ProcessingLayer.RULE

    def test_default_key_lists(self, pipeline):
        assert "姓名" in pipeline.key_lists[DocumentType.ID_CARD]
        assert "持证人" in pipeline.key_lists[DocumentType.MARRIAGE_CERTIFICATE]
        assert "买受人" in pipeline.key_lists[DocumentType.PURCHASE_CONTRACT]

    def test_custom_key_lists(self):
        custom_keys = {
            DocumentType.ID_CARD: ["姓名", "性别"],
        }
        pipeline = PlanEPlusPipeline(key_lists=custom_keys)
        assert pipeline.key_lists[DocumentType.ID_CARD] == ["姓名", "性别"]

    def test_process_household_register_with_mock_vlm_layer(self, tmp_path):
        """使用mock VLM层测试户口本流程（VLM作为兜底）"""
        from unittest.mock import Mock

        mock_vlm_layer = Mock()
        mock_vlm_layer.can_process.return_value = True
        mock_vlm_layer.extract.return_value = ExtractionResult(
            doc_type=DocumentType.HOUSEHOLD_REGISTER,
            layer=ProcessingLayer.VLM,
            fields={"姓名": "张三", "户主": "李四", "出生日期": "1990年1月1日", "民族": "汉族"},
            success=True,
            time_cost=2.0,
        )

        pipeline = PlanEPlusPipeline(vlm_layer=mock_vlm_layer)
        # 使用"常住人口登记卡"强信号，应该被规则层处理
        ocr_texts = ["常住人口登记卡", "姓名 张三", "户主姓名 李四"]
        result = pipeline.process("/tmp/hukou.jpg", ocr_texts)

        # 户口本现在由规则层处理，识别为个人页
        assert result.success is True
        assert result.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT
        assert result.layer == ProcessingLayer.RULE
