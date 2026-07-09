#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试规则提取层
"""

import pytest
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.interfaces import DocumentType, DocumentInfo


class TestRuleExtractionLayer:
    @pytest.fixture
    def layer(self):
        return RuleExtractionLayer()

    def test_supported_doc_types(self, layer):
        assert DocumentType.ID_CARD in layer.supported_doc_types
        assert DocumentType.MARRIAGE_CERTIFICATE in layer.supported_doc_types
        assert DocumentType.HOUSEHOLD_REGISTER in layer.supported_doc_types  # 已添加到规则层
        assert DocumentType.PROPERTY_CERTIFICATE in layer.supported_doc_types
        assert DocumentType.INVOICE in layer.supported_doc_types
        assert DocumentType.PURCHASE_CONTRACT in layer.supported_doc_types
        assert DocumentType.STOCK_CONTRACT in layer.supported_doc_types
        assert DocumentType.FUND_SUPERVISION in layer.supported_doc_types

    def test_can_process_id_card(self, layer):
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD)
        assert layer.can_process(info) is True

    def test_can_process_unknown(self, layer):
        info = DocumentInfo(image_path="/tmp/unknown.jpg", doc_type=DocumentType.UNKNOWN)
        assert layer.can_process(info) is False

    def test_extract_id_card_fields(self, layer):
        ocr_texts = [
            "姓名 张三",
            "性别 男 民族 汉族",
            "出生 1990年1月1日",
            "住址 北京市朝阳区某某路1号",
            "公民身份号码 110101199001011234",
        ]
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD, ocr_texts=ocr_texts)
        key_list = ["姓名", "性别", "民族", "出生", "公民身份号码"]

        result = layer.extract(info, key_list)

        assert result.success is True
        assert result.doc_type == DocumentType.ID_CARD
        assert result.fields["姓名"] == "张三"
        assert result.fields["性别"] == "男"
        assert result.fields["民族"] == "汉族"
        assert result.fields["出生"] == "1990年1月1日"
        assert result.fields["公民身份号码"] == "110101199001011234"

    def test_extract_id_card_with_x(self, layer):
        ocr_texts = ["公民身份号码 11010119900101123X"]
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD, ocr_texts=ocr_texts)
        result = layer.extract(info, ["公民身份号码"])
        assert result.fields["公民身份号码"] == "11010119900101123X"

    def test_extract_marriage_certificate_fields(self, layer):
        ocr_texts = [
            "结婚证",
            "持证人 张三",
            "登记日期 2020年5月20日",
            "结婚证字号 J110101-2020-000123",
        ]
        info = DocumentInfo(
            image_path="/tmp/marriage.jpg",
            doc_type=DocumentType.MARRIAGE_CERTIFICATE,
            ocr_texts=ocr_texts,
        )
        key_list = ["持证人", "登记日期", "结婚证字号"]

        result = layer.extract(info, key_list)

        assert result.success is True
        assert result.fields["持证人"] == "张三"
        assert result.fields["登记日期"] == "2020年5月20日"
        assert result.fields["结婚证字号"] == "J110101-2020-000123"

    def test_extract_only_requested_fields(self, layer):
        ocr_texts = [
            "姓名 张三",
            "性别 男",
            "公民身份号码 110101199001011234",
        ]
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD, ocr_texts=ocr_texts)
        result = layer.extract(info, ["姓名"])

        assert "姓名" in result.fields
        assert result.fields["姓名"] == "张三"
        # 未请求的字段不应返回
        assert "性别" not in result.fields

    def test_extract_unknown_field_returns_empty(self, layer):
        ocr_texts = ["姓名 张三"]
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD, ocr_texts=ocr_texts)
        result = layer.extract(info, ["不存在的字段"])
        assert result.fields["不存在的字段"] == ""
        assert result.success is True

    def test_extract_empty_text(self, layer):
        info = DocumentInfo(image_path="/tmp/id.jpg", doc_type=DocumentType.ID_CARD, ocr_texts=[])
        result = layer.extract(info, ["姓名"])
        assert result.success is True
        assert result.fields["姓名"] == ""

    def test_extract_marriage_gender_pattern(self, layer):
        ocr_texts = [
            "姓名 张三 性别 男 国籍 中国",
            "姓名 李四 性别 女 国籍 中国",
            "男方姓名 张三 女方姓名 李四",
        ]
        info = DocumentInfo(
            image_path="/tmp/marriage.jpg",
            doc_type=DocumentType.MARRIAGE_CERTIFICATE,
            ocr_texts=ocr_texts,
        )
        result = layer.extract(info, ["男方姓名", "女方姓名"])
        assert result.fields["男方姓名"] == "张三"
        assert result.fields["女方姓名"] == "李四"

    def test_extract_id_card_back_issuing_authority(self, layer):
        """测试身份证背面签发机关提取"""
        ocr_texts = [
            "中华人民共和国",
            "居民身份证",
            "签发机关  蚌埠市公安局蚌山分局",
            "有效期限  2024.06.21-2044.06.21",
        ]
        info = DocumentInfo(
            image_path="/tmp/id_back.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=ocr_texts,
        )
        result = layer.extract(info, ["签发机关", "有效期限"])

        assert result.success is True
        assert result.fields["签发机关"] == "蚌埠市公安局蚌山分局"

    def test_extract_id_card_back_validity_period(self, layer):
        """测试身份证背面有效期限提取"""
        ocr_texts = [
            "中华人民共和国",
            "居民身份证",
            "签发机关 蚌埠市公安局龙子湖分局",
            "有效期限 2021.07.15-2041.07.15",
        ]
        info = DocumentInfo(
            image_path="/tmp/id_back.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=ocr_texts,
        )
        result = layer.extract(info, ["有效期限"])

        assert result.success is True
        assert result.fields["有效期限"] == "2021.07.15-2041.07.15"

    def test_extract_id_card_back_validity_long_term(self, layer):
        """测试身份证背面长期有效期限提取"""
        ocr_texts = [
            "中华人民共和国",
            "居民身份证",
            "签发机关  蚌埠市公安局蚌山分局",
            "有效期限  2016.10.11-长期",
        ]
        info = DocumentInfo(
            image_path="/tmp/id_back.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=ocr_texts,
        )
        result = layer.extract(info, ["有效期限"])

        assert result.success is True
        assert result.fields["有效期限"] == "2016.10.11-长期"

    def test_extract_id_card_front_and_back_combined(self, layer):
        """测试身份证正反面混合文本的字段提取"""
        ocr_texts = [
            "姓名 王琼",
            "性别 男 民族 汉",
            "出生 2003 年 6 月 16 日",
            "住址 安徽省固镇县王庄镇河东村北王组73号",
            "公民身份号码 34032320030616491X",
            "",
            "中华人民共和国",
            "居民身份证",
            "签发机关  固镇县公安局",
            "有效期限  2023.06.25-2033.06.25",
        ]
        info = DocumentInfo(
            image_path="/tmp/id_full.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=ocr_texts,
        )
        key_list = ["姓名", "性别", "公民身份号码", "签发机关", "有效期限"]
        result = layer.extract(info, key_list)

        assert result.success is True
        assert result.fields["姓名"] == "王琼"
        assert result.fields["性别"] == "男"
        assert result.fields["公民身份号码"] == "34032320030616491X"
        assert result.fields["签发机关"] == "固镇县公安局"
        assert result.fields["有效期限"] == "2023.06.25-2033.06.25"

    def test_extract_id_card_name_not_mixed_with_gender(self, layer):
        """测试姓名字段不会错误提取为包含性别的内容"""
        ocr_texts = [
            "姓名 张三",
            "性别 男 民族 汉族",
        ]
        info = DocumentInfo(
            image_path="/tmp/id.jpg",
            doc_type=DocumentType.ID_CARD,
            ocr_texts=ocr_texts,
        )
        result = layer.extract(info, ["姓名", "性别"])

        # 姓名不应包含"性别"字样
        assert result.fields["姓名"] == "张三"
        assert result.fields["性别"] == "男"
        assert "性别" not in result.fields["姓名"]


class TestRuleLayerSkipTypes:
    """测试规则层跳过列表（封面页、盖章页、附图页、签署页）"""

    @pytest.fixture
    def layer(self):
        return RuleExtractionLayer(position_extractor=None)

    def test_skip_property_certificate_attachment(self, layer):
        """测试不动产权证书附图页返回空字段"""
        doc_info = DocumentInfo(
            image_path="/tmp/attachment.jpg",
            doc_type=DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            ocr_texts=["附图页 房屋坐落"],
        )
        key_list = ["证书号", "权利人", "房屋地址"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert all(v == "" for v in result.fields.values())

    def test_skip_purchase_contract_stamp(self, layer):
        """测试购房合同签署页返回空字段"""
        doc_info = DocumentInfo(
            image_path="/tmp/stamp.jpg",
            doc_type=DocumentType.PURCHASE_CONTRACT_STAMP,
            ocr_texts=["签署页 签章"],
        )
        key_list = ["合同编号", "买受人", "总价款"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert all(v == "" for v in result.fields.values())

    def test_skip_stock_contract_stamp(self, layer):
        """测试存量房合同签署页返回空字段"""
        doc_info = DocumentInfo(
            image_path="/tmp/stamp.jpg",
            doc_type=DocumentType.STOCK_CONTRACT_STAMP,
            ocr_texts=["签署页 签章"],
        )
        key_list = ["合同编号", "买受人", "总价款"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert all(v == "" for v in result.fields.values())

    def test_skip_marriage_certificate_cover(self, layer):
        """测试结婚证封面页返回空字段"""
        doc_info = DocumentInfo(
            image_path="/tmp/cover.jpg",
            doc_type=DocumentType.MARRIAGE_CERTIFICATE_COVER,
            ocr_texts=["结婚证"],
        )
        key_list = ["结婚证字号", "持证人"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert all(v == "" for v in result.fields.values())

    def test_skip_fund_supervision_stamp(self, layer):
        """测试资金监管协议签章页返回空字段"""
        doc_info = DocumentInfo(
            image_path="/tmp/stamp.jpg",
            doc_type=DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
            ocr_texts=["资金监管协议 签章"],
        )
        key_list = ["编号", "甲方", "乙方"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert all(v == "" for v in result.fields.values())


class TestRuleLayerPropertyCertificateFirstPage:
    """测试房产证首页路由到新提取器"""

    @pytest.fixture
    def layer(self):
        return RuleExtractionLayer(position_extractor=None)

    def test_extract_property_first_page_bianhao(self, layer):
        """测试房产证首页提取编号"""
        doc_info = DocumentInfo(
            image_path="/tmp/property_first.jpg",
            doc_type=DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
            ocr_texts=["编号 № 34026135082 登记日期 2025年03月20日"],
        )
        key_list = ["编号", "登记日期"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert result.fields["编号"] == "34026135082"

    def test_extract_property_first_page_dengji_riqi(self, layer):
        """测试房产证首页提取登记日期"""
        doc_info = DocumentInfo(
            image_path="/tmp/property_first.jpg",
            doc_type=DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
            ocr_texts=["编号 № 34026135082 登记日期 2025年03月20日"],
        )
        key_list = ["编号", "登记日期"]
        result = layer.extract(doc_info, key_list)
        assert result.success is True
        assert "2025" in result.fields["登记日期"]
