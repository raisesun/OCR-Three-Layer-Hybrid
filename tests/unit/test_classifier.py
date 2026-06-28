#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文档分类器（重构版）
"""

import pytest
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.interfaces import DocumentType


class TestKeywordDocumentClassifier:
    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    # === 阶段1: 标准证件测试 ===

    def test_classify_id_card(self, classifier):
        """身份证：公民身份号码"""
        ocr_texts = ["姓名 张三", "性别 男", "公民身份号码 110101199001011234"]
        info = classifier.classify("/tmp/id_card.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD
        assert info.confidence == 0.95
        assert info.metadata["route"] == "standard_certificate"

    def test_classify_id_card_back(self, classifier):
        """身份证反面：签发机关"""
        ocr_texts = ["签发机关 北京市公安局", "有效期限 2020.01.01-2040.01.01"]
        info = classifier.classify("/tmp/id_card_back.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD
        assert info.confidence == 0.95

    def test_classify_marriage_certificate(self, classifier):
        """结婚证：结婚证字号"""
        ocr_texts = ["结婚证字号 J12345", "持证人 张三", "登记日期 2020年1月1日"]
        info = classifier.classify("/tmp/marriage.jpg", ocr_texts)
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE
        assert info.confidence == 0.95

    def test_classify_household_register(self, classifier):
        """户口本：常住人口登记卡"""
        ocr_texts = ["常住人口登记卡", "姓名 李四", "户主姓名 李大山"]
        info = classifier.classify("/tmp/hukou.jpg", ocr_texts)
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER
        assert info.confidence == 0.95

    def test_classify_property_certificate(self, classifier):
        """房产证：不动产权证书"""
        ocr_texts = ["不动产权证书", "权利人 王五", "共有情况 单独所有"]
        info = classifier.classify("/tmp/property.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PROPERTY_CERTIFICATE
        assert info.confidence == 0.95

    def test_classify_marriage_certificate_backup(self, classifier):
        """结婚证备选强信号：持证人 + 登记日期"""
        # 没有结婚证字号，但有持证人和登记日期
        ocr_texts = ["持证人 张三", "登记日期 2020年5月20日"]
        info = classifier.classify("/tmp/marriage_backup.jpg", ocr_texts)
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE
        assert info.confidence == 0.90
        assert info.metadata["route"] == "backup_certificate"

    def test_classify_marriage_certificate_backup_with_gender(self, classifier):
        """结婚证备选强信号：持证人 + 登记日期 + 其他字段"""
        # 模拟真实结婚证的OCR文本
        ocr_texts = [
            "持证人张梅梅",
            "登记日期2020年08月25日",
            "男方姓名 张三",
            "女方姓名 张梅梅",
        ]
        info = classifier.classify("/tmp/marriage_real.jpg", ocr_texts)
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE
        assert info.confidence == 0.90

    # === 阶段2: 标准单证测试 ===

    def test_classify_invoice(self, classifier):
        """发票：发票代码 + 发票号码"""
        ocr_texts = ["发票代码 11001234", "发票号码 56789012", "税额 10000", "不含税金额 100000"]
        info = classifier.classify("/tmp/invoice.jpg", ocr_texts)
        assert info.doc_type == DocumentType.INVOICE
        assert info.confidence == 0.95
        assert info.metadata["route"] == "standard_document"

    def test_classify_invoice_weak(self, classifier):
        """发票弱信号：税额 + 不含税金额"""
        ocr_texts = ["税额 10000", "不含税金额 100000", "价税合计 110000"]
        info = classifier.classify("/tmp/invoice_weak.jpg", ocr_texts)
        assert info.doc_type == DocumentType.INVOICE
        assert info.confidence == 0.7
        assert info.metadata["route"] == "standard_document_weak"

    # === 阶段3: 合同/协议测试 ===

    def test_classify_purchase_contract(self, classifier):
        """购房合同：买受人+出卖人+价款+商品房"""
        ocr_texts = ["商品房买卖合同", "买受人 王五", "出卖人 赵六", "总价款 1000000"]
        info = classifier.classify("/tmp/contract.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PURCHASE_CONTRACT
        assert info.confidence == 0.9

    def test_classify_stock_contract(self, classifier):
        """存量房合同：买受人+出卖人+价款+存量房"""
        ocr_texts = ["存量房买卖合同", "买受人 王五", "出卖人 赵六", "总价款 2000000"]
        info = classifier.classify("/tmp/stock_contract.jpg", ocr_texts)
        assert info.doc_type == DocumentType.STOCK_CONTRACT
        assert info.confidence == 0.9

    def test_classify_fund_supervision(self, classifier):
        """资金监管协议"""
        ocr_texts = ["资金监管协议", "监管金额 2000000", "买方 王五", "卖方 赵六"]
        info = classifier.classify("/tmp/supervision.jpg", ocr_texts)
        assert info.doc_type == DocumentType.FUND_SUPERVISION

    def test_classify_divorce_agreement(self, classifier):
        """离婚协议"""
        ocr_texts = ["离婚协议", "财产分割", "房产归男方所有"]
        info = classifier.classify("/tmp/divorce.jpg", ocr_texts)
        assert info.doc_type == DocumentType.DIVORCE_AGREEMENT

    # === 阶段4: UNKNOWN测试 ===

    def test_classify_unknown(self, classifier):
        """未知文档"""
        ocr_texts = ["这是一段无关文本", "没有任何关键词"]
        info = classifier.classify("/tmp/unknown.jpg", ocr_texts)
        assert info.doc_type == DocumentType.UNKNOWN
        assert info.confidence == 0.0
        assert info.metadata["route"] == "vlm_fallback_required"

    def test_classify_empty_text(self, classifier):
        """空文本"""
        info = classifier.classify("/tmp/empty.jpg", [])
        assert info.doc_type == DocumentType.UNKNOWN

    # === 优先级测试 ===

    def test_classify_priority_id_card_over_contract(self, classifier):
        """测试优先级：身份证强信号优先于合同字段组合"""
        ocr_texts = ["公民身份号码 110101199001011234", "买受人 王五", "出卖人 赵六"]
        info = classifier.classify("/tmp/mixed.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD

    def test_classify_priority_certificate_over_weak_signal(self, classifier):
        """测试优先级：标准证件强信号优先于发票弱信号"""
        ocr_texts = ["公民身份号码 110101199001011234", "税额 10000"]
        info = classifier.classify("/tmp/mixed2.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD

    # === 便捷方法测试 ===

    def test_classify_from_text(self, classifier):
        """从文本分类"""
        text = "常住人口登记卡 姓名 李四"
        info = classifier.classify_from_text("/tmp/hukou.jpg", text)
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER
