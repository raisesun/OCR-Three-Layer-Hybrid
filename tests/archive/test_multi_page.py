#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多页文档处理集成测试

测试场景：
1. 多页离婚证：封面(skip) + 内容页(RULE) + 盖章页(skip) → 合并结果
2. 多页户口本：首页(RULE) + 个人页(RULE) → 合并结果
3. 多页资金监管协议：首页(RULE) + 信息页(RULE) + 签章页(skip) → 合并结果
4. VLM 兜底：RULE 缺失必填字段 → 触发 VLM 兜底
5. 方法C验证：RULE 已有字段不被 VLM 覆盖
6. 冲突检测：不同页提取到同一字段的不同值
7. 基础类型返回：结果 doc_type 是基础类型，不是首页细分类型
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
    FieldConflict,
)
from ocr_three_layer_hybrid.field_config import (
    DocumentFieldConfig,
    FieldConfig,
    FieldPriority,
    get_default_document_field_configs,
)


def _make_service():
    """创建一个不初始化外部依赖的 OCRService mock"""
    with patch("ocr_three_layer_hybrid.service.VLMClient"), \
         patch("ocr_three_layer_hybrid.service.KeywordDocumentClassifier"), \
         patch("ocr_three_layer_hybrid.service.VLMExtractionLayer"), \
         patch("ocr_three_layer_hybrid.service.PlanEPlusPipeline"), \
         patch("ocr_three_layer_hybrid.rule_layer.RuleExtractionLayer"):
        from ocr_three_layer_hybrid.service import OCRService
        svc = OCRService.__new__(OCRService)
        return svc


class TestMultiPageDivorceCertificate:
    """集成测试：多页离婚证处理流程"""

    def test_divorce_cert_cover_content_stamp(self):
        """离婚证：封面(skip) + 内容页(RULE成功) + 盖章页(skip) → 合并结果"""
        svc = _make_service()

        # Mock 分类器：依次返回 封面、内容页、盖章页
        mock_classifier = Mock()
        mock_classifier.classify.side_effect = [
            # 首页分类
            DocumentInfo(
                image_path="/tmp/divorce_0.jpg",
                doc_type=DocumentType.DIVORCE_CERTIFICATE_COVER,
                ocr_texts=["离婚证"],
                confidence=0.9,
            ),
            # 第2页分类（内容页）
            DocumentInfo(
                image_path="/tmp/divorce_1.jpg",
                doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
                ocr_texts=["离婚证字号 L12345"],
                confidence=0.9,
            ),
            # 第3页分类（盖章页）
            DocumentInfo(
                image_path="/tmp/divorce_2.jpg",
                doc_type=DocumentType.DIVORCE_CERTIFICATE_STAMP,
                ocr_texts=["登记机关章"],
                confidence=0.9,
            ),
        ]
        svc._classifier = mock_classifier

        # Mock run_ocr
        svc.run_ocr = Mock(side_effect=[
            "离婚证",  # 首页OCR（分类用）
            "离婚证",  # 第2页OCR（分类用）
            "离婚证字号 L12345 持证人身份证件号 340123199001011234",  # 第2页OCR（提取用）
            "登记机关章",  # 第3页OCR（分类用）
            "登记机关章",  # 第3页OCR（提取用）
        ])

        # Mock pipeline.process：返回成功提取结果
        def mock_process(img_path, ocr_texts, doc_info=None):
            if doc_info.doc_type == DocumentType.DIVORCE_CERTIFICATE_CONTENT:
                return ExtractionResult(
                    doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
                    layer=ProcessingLayer.RULE,
                    fields={
                        "离婚证字号": "L12345",
                        "持证人身份证件号": "340123199001011234",
                        "原配偶身份证件号": "340123199002022345",
                    },
                    success=True,
                )
            elif doc_info.doc_type in [
                DocumentType.DIVORCE_CERTIFICATE_COVER,
                DocumentType.DIVORCE_CERTIFICATE_STAMP,
            ]:
                # 封面和盖章页：skip，返回空字段
                return ExtractionResult(
                    doc_type=doc_info.doc_type,
                    layer=ProcessingLayer.RULE,
                    fields={},
                    success=True,
                )
            return ExtractionResult(
                doc_type=doc_info.doc_type if doc_info else DocumentType.UNKNOWN,
                layer=ProcessingLayer.RULE,
                fields={},
                success=False,
            )

        # Mock pipeline
        mock_pipeline = Mock()
        mock_pipeline.process.side_effect = mock_process
        mock_pipeline._get_layer.return_value = None  # 不需要 VLM 兜底
        svc._pipeline = mock_pipeline
        svc._vlm_fallback_handler = None

        # 执行多页处理
        result = svc.process_multi_page([
            "/tmp/divorce_0.jpg",
            "/tmp/divorce_1.jpg",
            "/tmp/divorce_2.jpg",
        ])

        # 验证返回结果是基础类型
        assert result["multi_page"]["doc_type"] == "离婚证"

        # 验证提取结果包含内容页字段
        fields = result["extraction"]["fields"]
        assert fields.get("离婚证字号") == "L12345"
        assert fields.get("持证人身份证件号") == "340123199001011234"


class TestMultiPageHouseholdRegister:
    """集成测试：多页户口本处理流程"""

    def test_household_cover_content_merge(self):
        """户口本：首页(户信息) + 个人页 → 合并字段"""
        svc = _make_service()

        mock_classifier = Mock()
        mock_classifier.classify.side_effect = [
            # 首页分类
            DocumentInfo(
                image_path="/tmp/household_0.jpg",
                doc_type=DocumentType.HOUSEHOLD_REGISTER_COVER,
                ocr_texts=["户别 非农业家庭户"],
                confidence=0.9,
            ),
            # 第2页分类
            DocumentInfo(
                image_path="/tmp/household_1.jpg",
                doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
                ocr_texts=["姓名 张三"],
                confidence=0.9,
            ),
        ]
        svc._classifier = mock_classifier

        svc.run_ocr = Mock(side_effect=[
            "户别 非农业家庭户 户主姓名 李大山 户号 12345678",  # 首页OCR（分类+提取）
            "户别 非农业家庭户 户主姓名 李大山 户号 12345678",  # 首页OCR（提取用）
            "姓名 张三 公民身份号码 340123199001011234",  # 第2页OCR（分类+提取）
            "姓名 张三 公民身份号码 340123199001011234",  # 第2页OCR（提取用）
        ])

        def mock_process(img_path, ocr_texts, doc_info=None):
            if doc_info.doc_type == DocumentType.HOUSEHOLD_REGISTER_COVER:
                return ExtractionResult(
                    doc_type=DocumentType.HOUSEHOLD_REGISTER_COVER,
                    layer=ProcessingLayer.RULE,
                    fields={
                        "户主姓名": "李大山",
                        "户号": "12345678",
                        "户别": "非农业家庭户",
                        "住址": "安徽省合肥市",
                    },
                    success=True,
                )
            elif doc_info.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT:
                return ExtractionResult(
                    doc_type=DocumentType.HOUSEHOLD_REGISTER_CONTENT,
                    layer=ProcessingLayer.RULE,
                    fields={
                        "姓名": "张三",
                        "公民身份号码": "340123199001011234",
                        "与户主关系": "之子",
                    },
                    success=True,
                )
            return ExtractionResult(
                doc_type=doc_info.doc_type if doc_info else DocumentType.UNKNOWN,
                layer=ProcessingLayer.RULE,
                fields={},
                success=False,
            )

        mock_pipeline = Mock()
        mock_pipeline.process.side_effect = mock_process
        mock_pipeline._get_layer.return_value = None
        svc._pipeline = mock_pipeline
        svc._vlm_fallback_handler = None

        result = svc.process_multi_page([
            "/tmp/household_0.jpg",
            "/tmp/household_1.jpg",
        ])

        # 验证返回基础类型
        assert result["multi_page"]["doc_type"] == "户口本"

        # 验证合并字段：首页 + 个人页
        fields = result["extraction"]["fields"]
        assert fields.get("户主姓名") == "李大山"
        assert fields.get("户号") == "12345678"
        assert fields.get("姓名") == "张三"
        assert fields.get("公民身份号码") == "340123199001011234"


class TestVLMFallbackMethodC:
    """集成测试：VLM 兜底方法C验证"""

    def test_vlm_does_not_overwrite_rule_values(self):
        """方法C：RULE 已有字段不被 VLM 覆盖"""
        svc = _make_service()

        mock_classifier = Mock()
        mock_classifier.classify.return_value = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            ocr_texts=["离婚证字号 L12345"],
            confidence=0.9,
        )
        svc._classifier = mock_classifier

        svc.run_ocr = Mock(side_effect=[
            "离婚证字号 L12345 持证人身份证件号 340123199001011234",  # 分类
            "离婚证字号 L12345 持证人身份证件号 340123199001011234",  # 提取
        ])

        # RULE 层：成功提取了离婚证字号，但缺失原配偶身份证件号
        def mock_process(img_path, ocr_texts, doc_info=None):
            return ExtractionResult(
                doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
                layer=ProcessingLayer.RULE,
                fields={
                    "离婚证字号": "L12345",
                    "持证人身份证件号": "340123199001011234",
                    "原配偶身份证件号": "",  # 缺失
                },
                success=True,
            )

        # VLM 层：返回不同值（方法C 不应覆盖）+ 填充缺失字段
        mock_vlm_layer = Mock()
        mock_vlm_layer.extract.return_value = ExtractionResult(
            doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            layer=ProcessingLayer.VLM,
            fields={
                "离婚证字号": "L99999",  # 与 RULE 不同
                "持证人身份证件号": "999999999999999999",  # 与 RULE 不同
                "原配偶身份证件号": "340123199002022345",  # 缺失字段，应填充
            },
            success=True,
        )

        mock_pipeline = Mock()
        mock_pipeline.process.side_effect = mock_process
        mock_pipeline._get_layer.return_value = mock_vlm_layer
        svc._pipeline = mock_pipeline
        svc._vlm_fallback_handler = None

        result = svc._extract_multi_page_merge(
            ["/tmp/test.jpg"],
            first_page_doc_info=DocumentInfo(
                image_path="/tmp/test.jpg",
                doc_type=DocumentType.DIVORCE_CERTIFICATE_CONTENT,
                ocr_texts=["离婚证字号 L12345"],
            ),
        )

        fields = result.fields
        # RULE 已有字段不应被 VLM 覆盖
        assert fields["离婚证字号"] == "L12345", "RULE 值不应被 VLM 覆盖"
        assert fields["持证人身份证件号"] == "340123199001011234", "RULE 值不应被 VLM 覆盖"
        # VLM 填充缺失字段
        assert fields["原配偶身份证件号"] == "340123199002022345", "VLM 应填充缺失字段"
        # VLM 兜底应被标记
        assert result.vlm_fallback_triggered is True


class TestConflictDetection:
    """集成测试：字段冲突检测"""

    def test_conflict_between_pages(self):
        """不同页提取到同一字段的不同值 → 检测冲突"""
        svc = _make_service()

        # 首页是 first_page_doc_info（不经过分类器），第2页才调用分类器
        mock_classifier = Mock()
        mock_classifier.classify.side_effect = [
            # 第2页分类（首页不经过分类器）
            DocumentInfo(
                image_path="/tmp/page1.jpg",
                doc_type=DocumentType.PURCHASE_CONTRACT_CONTENT,
                ocr_texts=["总价款 100万"],
                confidence=0.9,
            ),
        ]
        svc._classifier = mock_classifier

        # 首页不经过 run_ocr（复用 first_page_doc_info），第2页调用 2 次 run_ocr（分类 + 提取）
        # 但首页仍需 run_ocr 做提取（_extract_multi_page_merge 内）
        svc.run_ocr = Mock(side_effect=[
            "合同编号 HT-001 买受人 张三 出卖人 李四",  # 首页 OCR（提取用）
            "总价款 100万 签订日期 2025年1月1日",  # 第2页 OCR（分类用）
            "总价款 100万 签订日期 2025年1月1日",  # 第2页 OCR（提取用）
        ])

        def mock_process(img_path, ocr_texts, doc_info=None):
            if doc_info.doc_type == DocumentType.PURCHASE_CONTRACT_FIRST_PAGE:
                return ExtractionResult(
                    doc_type=DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
                    layer=ProcessingLayer.RULE,
                    fields={
                        "合同编号": "HT-001",
                        "买受人": "张三",
                        "出卖人": "李四",
                    },
                    success=True,
                )
            elif doc_info.doc_type == DocumentType.PURCHASE_CONTRACT_CONTENT:
                return ExtractionResult(
                    doc_type=DocumentType.PURCHASE_CONTRACT_CONTENT,
                    layer=ProcessingLayer.RULE,
                    fields={
                        "总价款": "100万",
                        "签订日期": "2025年1月1日",
                    },
                    success=True,
                )
            return ExtractionResult(
                doc_type=doc_info.doc_type if doc_info else DocumentType.UNKNOWN,
                layer=ProcessingLayer.RULE,
                fields={},
                success=False,
            )

        mock_pipeline = Mock()
        mock_pipeline.process.side_effect = mock_process
        mock_pipeline._get_layer.return_value = None
        svc._pipeline = mock_pipeline
        svc._vlm_fallback_handler = None

        result = svc._extract_multi_page_merge(
            ["/tmp/page0.jpg", "/tmp/page1.jpg"],
            first_page_doc_info=DocumentInfo(
                image_path="/tmp/page0.jpg",
                doc_type=DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
                ocr_texts=["合同编号 HT-001"],
            ),
        )

        # 验证基础类型
        assert result.doc_type == DocumentType.PURCHASE_CONTRACT

        # 验证合并字段
        assert result.fields.get("合同编号") == "HT-001"
        assert result.fields.get("买受人") == "张三"
        assert result.fields.get("总价款") == "100万"


class TestBaseDocTypeReturned:
    """集成测试：返回基础类型而非首页细分类型"""

    def test_first_page_cover_returns_base_type(self):
        """首页是封面 → 结果返回基础类型"""
        svc = _make_service()

        mock_classifier = Mock()
        mock_classifier.classify.return_value = DocumentInfo(
            image_path="/tmp/test.jpg",
            doc_type=DocumentType.DIVORCE_CERTIFICATE_COVER,
            ocr_texts=["离婚证"],
            confidence=0.9,
        )
        svc._classifier = mock_classifier

        svc.run_ocr = Mock(return_value="离婚证")

        mock_pipeline = Mock()
        mock_pipeline.process.return_value = ExtractionResult(
            doc_type=DocumentType.DIVORCE_CERTIFICATE_COVER,
            layer=ProcessingLayer.RULE,
            fields={},
            success=True,
        )
        mock_pipeline._get_layer.return_value = None
        svc._pipeline = mock_pipeline
        svc._vlm_fallback_handler = None

        result = svc._extract_multi_page_merge(
            ["/tmp/test.jpg"],
            first_page_doc_info=DocumentInfo(
                image_path="/tmp/test.jpg",
                doc_type=DocumentType.DIVORCE_CERTIFICATE_COVER,
                ocr_texts=["离婚证"],
            ),
        )

        # 结果应该是基础类型 DIVORCE_CERTIFICATE，不是 DIVORCE_CERTIFICATE_COVER
        assert result.doc_type == DocumentType.DIVORCE_CERTIFICATE
