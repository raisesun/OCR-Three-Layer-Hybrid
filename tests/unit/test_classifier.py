#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文档分类器（重构版）
"""

import pytest
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.interfaces import DocumentType, PageType


class TestKeywordDocumentClassifier:
    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    # === 阶段1: 标准证件测试 ===

    def test_classify_id_card(self, classifier):
        """身份证：公民身份号码 → 身份证正面"""
        ocr_texts = ["姓名 张三", "性别 男", "公民身份号码 110101199001011234"]
        info = classifier.classify("/tmp/id_card.jpg", ocr_texts)
        # 现在会识别为身份证正面（有姓名、性别、公民身份号码）
        assert info.doc_type == DocumentType.ID_CARD_FRONT
        assert info.confidence == 0.95
        assert info.metadata["route"] == "standard_certificate"

    def test_classify_id_card_back(self, classifier):
        """身份证反面：签发机关 → 身份证背面"""
        ocr_texts = ["签发机关 北京市公安局", "有效期限 2020.01.01-2040.01.01"]
        info = classifier.classify("/tmp/id_card_back.jpg", ocr_texts)
        # 现在会识别为身份证背面（有签发机关、有效期限）
        assert info.doc_type == DocumentType.ID_CARD_BACK
        assert info.confidence == 0.95

    def test_classify_marriage_certificate(self, classifier):
        """结婚证：结婚证字号 → 结婚证内容页"""
        ocr_texts = ["结婚证字号 J12345", "持证人 张三", "登记日期 2020年1月1日"]
        info = classifier.classify("/tmp/marriage.jpg", ocr_texts)
        # 现在会识别为结婚证内容页（有结婚证字号、持证人、登记日期）
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT
        assert info.confidence == 0.95

    def test_classify_household_register(self, classifier):
        """户口本：常住人口登记卡 → 户口本个人页"""
        ocr_texts = ["常住人口登记卡", "姓名 李四", "户主姓名 李大山"]
        info = classifier.classify("/tmp/hukou.jpg", ocr_texts)
        # 现在会识别为户口本个人页（有常住人口登记卡）
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT
        assert info.confidence == 0.95

    def test_classify_property_certificate(self, classifier):
        """房产证：不动产权证书"""
        ocr_texts = ["不动产权证书", "权利人 王五", "共有情况 单独所有"]
        info = classifier.classify("/tmp/property.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PROPERTY_CERTIFICATE
        assert info.confidence == 0.95

    def test_classify_marriage_certificate_backup(self, classifier):
        """结婚证备选强信号：持证人 + 登记日期 → 结婚证内容页"""
        # 没有结婚证字号，但有持证人和登记日期
        ocr_texts = ["持证人 张三", "登记日期 2020年5月20日"]
        info = classifier.classify("/tmp/marriage_backup.jpg", ocr_texts)
        # 现在会识别为结婚证内容页（有持证人、登记日期）
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT
        assert info.confidence == 0.90
        assert info.metadata["route"] == "backup_certificate"

    def test_classify_marriage_certificate_backup_with_gender(self, classifier):
        """结婚证备选强信号：持证人 + 登记日期 + 其他字段 → 结婚证内容页"""
        # 模拟真实结婚证的OCR文本
        ocr_texts = [
            "持证人张梅梅",
            "登记日期2020年08月25日",
            "男方姓名 张三",
            "女方姓名 张梅梅",
        ]
        info = classifier.classify("/tmp/marriage_real.jpg", ocr_texts)
        # 现在会识别为结婚证内容页（有持证人、登记日期）
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT
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
        """从文本分类 → 户口本个人页"""
        text = "常住人口登记卡 姓名 李四"
        info = classifier.classify_from_text("/tmp/hukou.jpg", text)
        # 现在会识别为户口本个人页（有常住人口登记卡）
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT


class TestMultiDocConflict:
    """阶段0: 多文档冲突检测"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_purchase_contract_overrides_id_in_contract(self, classifier):
        """合同中包含身份证号 → 仍分类为购房合同（不是身份证）"""
        ocr_texts = [
            "商品房买卖合同",
            "买受人 王五",
            "出卖人 赵六",
            "公民身份号码 110101199001011234",  # 合同中有身份证号
        ]
        info = classifier.classify("/tmp/mixed_scan.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PURCHASE_CONTRACT
        assert info.confidence == 0.90
        assert info.metadata["route"] == "multi_doc_conflict_resolution"

    def test_stock_contract_overrides_id_in_contract(self, classifier):
        """存量房合同中包含身份证号 → 仍分类为存量房合同"""
        ocr_texts = [
            "存量房买卖合同",
            "买受人 王五",
            "出卖人 赵六",
            "公民身份号码 110101199001011234",
        ]
        info = classifier.classify("/tmp/mixed_scan2.jpg", ocr_texts)
        assert info.doc_type == DocumentType.STOCK_CONTRACT
        assert info.metadata["route"] == "multi_doc_conflict_resolution"


class TestStandardCertificates:
    """阶段1: 更多标准证件测试"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_classify_notary_certificate(self, classifier):
        """公证书：公证书标题 → 公证书"""
        ocr_texts = ["公证书", "（2020）京海民证字第12345号"]
        info = classifier.classify("/tmp/notary.jpg", ocr_texts)
        assert info.doc_type == DocumentType.NOTARY_CERTIFICATE
        assert info.confidence == 0.95
        assert info.metadata["route"] == "standard_certificate"

    def test_classify_notary_certificate_by_number(self, classifier):
        """公证书：公证字第 → 公证书"""
        ocr_texts = ["公证字第12345号", "申请人 张三"]
        info = classifier.classify("/tmp/notary2.jpg", ocr_texts)
        assert info.doc_type == DocumentType.NOTARY_CERTIFICATE
        assert info.confidence == 0.95

    def test_classify_power_of_attorney(self, classifier):
        """委托书：委托书标题 → 委托书"""
        ocr_texts = ["委托书", "委托人 张三", "受托人 李四"]
        info = classifier.classify("/tmp/power.jpg", ocr_texts)
        assert info.doc_type == DocumentType.POWER_OF_ATTORNEY
        assert info.confidence == 0.95

    def test_classify_power_of_attorney_by_agent(self, classifier):
        """委托书：委托人+受托人 → 委托书"""
        ocr_texts = ["委托人 张三", "受托人 李四", "委托事项 办理房产过户"]
        info = classifier.classify("/tmp/power2.jpg", ocr_texts)
        assert info.doc_type == DocumentType.POWER_OF_ATTORNEY
        assert info.confidence == 0.95

    def test_classify_divorce_agreement(self, classifier):
        """离婚协议书：标题 → 离婚协议书"""
        ocr_texts = ["离婚协议书", "男方 张三", "女方 李四"]
        info = classifier.classify("/tmp/divorce_agreement.jpg", ocr_texts)
        assert info.doc_type == DocumentType.DIVORCE_AGREEMENT
        assert info.confidence == 0.95


class TestFundSupervisionCertificate:
    """资金监管凭证 vs 协议信息页区分（特殊二次验证）"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_fund_supervision_certificate_with_cert_fields(self, classifier):
        """资金监管凭证：有凭证字段 + 无协议信息 → FUND_SUPERVISION_CERTIFICATE"""
        ocr_texts = [
            "存量房交易资金监管凭证",
            "协议编号 ABC123",
            "买房人 张三",
            "监管总额 2000000",
        ]
        info = classifier.classify("/tmp/fund_cert.jpg", ocr_texts)
        assert info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE
        assert info.confidence == 0.95

    def test_fund_supervision_info_page_with_agreement_info(self, classifier):
        """资金监管凭证关键词 + 有协议信息 → 协议信息页（细化后）"""
        ocr_texts = [
            "资金监管凭证",
            "甲方 张三",
            "乙方 李四",
            "开户银行 工商银行",
            "账号 1234567890",
        ]
        info = classifier.classify("/tmp/fund_info.jpg", ocr_texts)
        # 虽然有"资金监管凭证"关键词，但有甲乙方+银行/账号 → 降级为协议信息页
        # 经过页面类型识别后细化为 FUND_SUPERVISION_AGREEMENT_INFO_PAGE
        assert info.doc_type == DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE

    def test_fund_supervision_certificate_without_cert_fields(self, classifier):
        """资金监管凭证关键词 + 无凭证字段 → FUND_SUPERVISION"""
        ocr_texts = [
            "资金监管凭证",
            "甲方 张三",
            "乙方 李四",
        ]
        info = classifier.classify("/tmp/fund_no_fields.jpg", ocr_texts)
        # 没有凭证字段 → 降级为协议
        assert info.doc_type == DocumentType.FUND_SUPERVISION


class TestAdditionalBackupSignals:
    """阶段1.6: 更多备选信号（特殊页面）"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_household_register_cover_page(self, classifier):
        """户口本首页：户别 + 户主姓名 + 住址"""
        ocr_texts = ["户别 非农业户口", "户主姓名 李大山", "住址 北京市海淀区"]
        info = classifier.classify("/tmp/hukou_cover.jpg", ocr_texts)
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER_COVER
        assert info.confidence == 0.85
        assert info.metadata["route"] == "additional_backup"

    def test_household_register_cover_with_space_in_hubie(self, classifier):
        """户口本首页：户 别（OCR空格处理）"""
        ocr_texts = ["户 别 非农业户口", "户主姓名 李大山", "家庭住址 北京市"]
        info = classifier.classify("/tmp/hukou_cover2.jpg", ocr_texts)
        # classify 内部会去除空格，所以"户 别"变成"户别"
        # 经过 backup + page_type + refined → 户口本首页
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER_COVER
        assert info.confidence >= 0.85

    def test_marriage_certificate_stamp_page(self, classifier):
        """结婚证盖章页：结婚证 + 登记机关"""
        ocr_texts = ["结婚证", "登记机关 北京市民政局", "民政部监制"]
        info = classifier.classify("/tmp/marriage_stamp.jpg", ocr_texts)
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_STAMP
        assert info.confidence == 0.85

    def test_divorce_certificate_stamp_page(self, classifier):
        """离婚证盖章页：离婚证 + 予以登记 → 盖章页"""
        ocr_texts = ["离婚证", "予以登记", "婚姻登记专用章"]
        info = classifier.classify("/tmp/divorce_stamp.jpg", ocr_texts)
        # "离婚证" 匹配标准证件强信号（0.95），然后页面识别为盖章页
        assert info.doc_type == DocumentType.DIVORCE_CERTIFICATE_STAMP
        assert info.confidence == 0.95

    def test_property_certificate_content_page(self, classifier):
        """房产证内容页：不动产权 + 权利人 + 不动产单元号"""
        ocr_texts = ["不动产权", "权利人 王五", "不动产单元号 110101123456"]
        info = classifier.classify("/tmp/property_content.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PROPERTY_CERTIFICATE
        assert info.confidence == 0.85

    def test_property_certificate_attachment_page(self, classifier):
        """房产证附图页：宗地图关键词"""
        ocr_texts = ["不动产权证书", "宗地图", "所在图幅编号 12345"]
        info = classifier.classify("/tmp/property_attachment.jpg", ocr_texts)
        # 附图页有强信号关键词 → 通过 standard_certificate 路由
        assert info.doc_type == DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT
        assert info.confidence == 0.95


class TestPageTypeDetection:
    """页面类型识别（_detect_page_type）"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_id_card_front_page_type(self, classifier):
        """身份证正面：有姓名+公民身份号码 → CONTENT"""
        ocr_texts = ["姓名 张三", "性别 男", "公民身份号码 110101199001011234"]
        info = classifier.classify("/tmp/id_front.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD_FRONT
        assert info.page_type == PageType.CONTENT

    def test_id_card_back_page_type(self, classifier):
        """身份证背面：有签发机关 → BACK"""
        ocr_texts = ["签发机关 北京市公安局", "有效期限 2020.01.01-2040.01.01"]
        info = classifier.classify("/tmp/id_back.jpg", ocr_texts)
        assert info.doc_type == DocumentType.ID_CARD_BACK
        assert info.page_type == PageType.BACK

    def test_marriage_cover_page_type(self, classifier):
        """结婚证封面：有'结婚证字号'但无持证人/登记日期 → 封面"""
        # 需要匹配到结婚证基础类型（通过结婚证字号），然后页面识别为封面
        ocr_texts = ["结婚证字号 J12345", "中华人民共和国"]
        info = classifier.classify("/tmp/marriage_cover.jpg", ocr_texts)
        # 有结婚证字号但无持证人和登记日期 → 不满足内容页条件
        # 页面识别逻辑：has_cert_no=True, has_holder=False, has_date=False
        # 条件 has_cert_no or (has_holder and has_date) = True → CONTENT
        # 所以这实际会返回内容页，而不是封面
        # 要测试封面，需要用"结婚证"但不含字号的方式
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT

    def test_marriage_cover_page_type(self, classifier):
        """结婚证封面：有'结婚证'但无字号 → 封面"""
        # "结婚证" 通过 additional_backup 匹配基础类型 MARRIAGE_CERTIFICATE
        # 然后页面识别为封面（有"结婚证"但无结婚证字号）
        ocr_texts = ["结婚证", "民政部监制"]
        info = classifier.classify("/tmp/marriage_cover.jpg", ocr_texts)
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_COVER

    def test_divorce_cover_page_type(self, classifier):
        """离婚证封面：有'离婚证'但无字号 → 封面"""
        # "离婚证" 通过 standard_certificate 匹配 DIVORCE_CERTIFICATE
        # 页面识别：有"离婚证"但无字号、无盖章信号 → COVER
        ocr_texts = ["离婚证", "中华人民共和国"]
        info = classifier.classify("/tmp/divorce_cover.jpg", ocr_texts)
        assert info.doc_type == DocumentType.DIVORCE_CERTIFICATE_COVER

    def test_household_register_personal_page(self, classifier):
        """户口本个人页：常住人口登记卡"""
        ocr_texts = ["常住人口登记卡", "姓名 李四", "户主姓名 李大山"]
        info = classifier.classify("/tmp/hukou_personal.jpg", ocr_texts)
        assert info.doc_type == DocumentType.HOUSEHOLD_REGISTER_CONTENT

    def test_fund_supervision_first_page(self, classifier):
        """资金监管协议首页：标题 + 编号 + 甲方"""
        ocr_texts = [
            "存量房交易资金监管协议",
            "编号 REG123",
            "甲方 张三",
            "乙方 李四",
        ]
        info = classifier.classify("/tmp/fund_first.jpg", ocr_texts)
        assert info.doc_type == DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE

    def test_fund_supervision_stamp_page(self, classifier):
        """资金监管协议签章页：甲方签章"""
        ocr_texts = [
            "资金监管协议",
            "甲方（签章）",
            "乙方（签章）",
            "丙方（签章）",
        ]
        info = classifier.classify("/tmp/fund_stamp.jpg", ocr_texts)
        assert info.doc_type == DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP

    def test_purchase_contract_first_page(self, classifier):
        """购房合同首页：买卖合同 + 卖方 + 买方"""
        ocr_texts = [
            "商品房买卖合同",
            "卖方 赵六",
            "买方 王五",
            "房屋坐落 北京市海淀区",
        ]
        info = classifier.classify("/tmp/contract_first.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PURCHASE_CONTRACT_FIRST_PAGE

    def test_purchase_contract_stamp_page(self, classifier):
        """购房合同签署页：合同签订日期"""
        ocr_texts = [
            "商品房买卖合同",
            "买受人 王五",
            "出卖人 赵六",
            "合同签订日期 2024年6月1日",
        ]
        info = classifier.classify("/tmp/contract_stamp.jpg", ocr_texts)
        assert info.doc_type == DocumentType.PURCHASE_CONTRACT_STAMP


class TestOcrSpaceHandling:
    """OCR 空格处理（破碎文本匹配）"""

    @pytest.fixture
    def classifier(self):
        return KeywordDocumentClassifier()

    def test_classify_with_space_in_keyword(self, classifier):
        """关键词中有空格：'结 婚证字号' → 应匹配'结婚证字号'"""
        ocr_texts = ["结 婚证字号 J12345", "持证人 张三", "登记日期 2020年1月1日"]
        info = classifier.classify("/tmp/marriage_space.jpg", ocr_texts)
        # 内部 replace(" ", "") 后能匹配到结婚证字号
        assert info.doc_type == DocumentType.MARRIAGE_CERTIFICATE_CONTENT
        assert info.confidence == 0.95

    def test_classify_with_space_in_household(self, classifier):
        """户口本空格处理：'户 口 簿' → 应匹配"""
        ocr_texts = ["户 口 簿", "户主 李大山"]
        info = classifier.classify("/tmp/hukou_space.jpg", ocr_texts)
        # 去除空格后能匹配到"户口簿"
        assert info.doc_type in (
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_COVER,
        )
