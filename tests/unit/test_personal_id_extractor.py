#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试个人证件提取器
"""

import pytest
from ocr_three_layer_hybrid.extractors import PersonalIdExtractor


class TestPersonalIdExtractor:
    @pytest.fixture
    def extractor(self):
        return PersonalIdExtractor()

    def test_extract_id_card_with_labels(self, extractor):
        """测试有标签的身份证提取"""
        full_text = "姓名 张三 性别 男 民族 汉 出生 1990年1月1日 住址 北京市朝阳区 公民身份号码 110101199001011234"
        key_list = ["姓名", "性别", "民族", "出生", "住址", "公民身份号码"]

        fields = extractor.extract_id_card(full_text, key_list)

        assert fields["姓名"] == "张三"
        assert fields["性别"] == "男"
        assert fields["民族"] == "汉"
        assert fields["出生"] == "1990年1月1日"
        assert "朝阳区" in fields["住址"]
        assert fields["公民身份号码"] == "110101199001011234"

    def test_extract_id_card_without_labels(self, extractor):
        """测试无标签的身份证提取"""
        full_text = "张三 男 汉 1990年1月1日 北京市朝阳区 110101199001011234"
        key_list = ["姓名", "性别", "民族", "出生", "住址", "公民身份号码"]

        fields = extractor.extract_id_card(full_text, key_list)

        # 无标签格式应该也能提取到部分字段
        assert fields.get("公民身份号码") == "110101199001011234"

    def test_extract_id_card_back(self, extractor):
        """测试身份证背面提取"""
        full_text = "签发机关 北京市公安局朝阳分局 有效期限 2020.01.01-2040.01.01"
        key_list = ["签发机关", "有效期限"]

        # 身份证背面通过extract_id_card方法处理
        fields = extractor.extract_id_card(full_text, key_list)

        assert "北京市公安局" in fields["签发机关"]
        assert fields["有效期限"] == "2020.01.01-2040.01.01"

    def test_extract_marriage_certificate(self, extractor):
        """测试结婚证提取"""
        # 使用更清晰的格式，每个字段单独一行
        full_text = """结婚证字号 J12345
持证人 张三
登记日期 2020年1月1日
男方姓名 张三
女方姓名 李四"""
        key_list = ["结婚证字号", "持证人", "登记日期", "男方姓名", "女方姓名"]

        fields = extractor.extract_marriage_certificate(full_text, key_list)

        assert fields["结婚证字号"] == "J12345"
        assert fields["持证人"] == "张三"
        assert fields["登记日期"] == "2020年1月1日"
        assert fields["男方姓名"] == "张三"
        assert fields["女方姓名"] == "李四"

    def test_extract_divorce_certificate(self, extractor):
        """测试离婚证提取"""
        full_text = """离婚证字号 D12345
登记日期 2020年5月20日"""
        key_list = ["离婚证字号", "登记日期"]

        fields = extractor.extract_divorce_certificate(full_text, key_list)

        assert fields["离婚证字号"] == "D12345"
        assert fields["登记日期"] == "2020年5月20日"
