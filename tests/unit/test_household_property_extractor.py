#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试户口本和房产证提取器
"""

import pytest
from ocr_three_layer_hybrid.extractors import HouseholdPropertyExtractor


class TestHouseholdPropertyExtractor:
    @pytest.fixture
    def extractor(self):
        # 初始化时传入None作为position_extractor
        return HouseholdPropertyExtractor(position_extractor=None)

    def test_extract_household_register_first_page(self, extractor):
        """测试户口本首页提取"""
        # 使用更真实的OCR输出格式
        full_text = """户别 非农业家庭户
户主姓名 李大山
住址 北京市朝阳区XX路XX号"""
        key_list = ["户别", "户主姓名", "住址"]

        fields = extractor.extract_household_register(full_text, key_list, "/tmp/hukou.jpg")

        assert fields["户别"] == "非农业家庭户"
        assert fields["户主姓名"] == "李大山"
        assert "朝阳区" in fields["住址"]

    def test_extract_household_register_personal_page(self, extractor):
        """测试户口本个人页提取"""
        full_text = "常住人口登记卡 姓名 李四 与户主关系 之子 公民身份号码 110101199001011234"
        key_list = ["姓名", "与户主关系", "公民身份号码"]

        fields = extractor.extract_household_register(full_text, key_list, "/tmp/hukou_personal.jpg")

        assert fields["姓名"] == "李四"
        assert fields["与户主关系"] == "之子"
        assert fields["公民身份号码"] == "110101199001011234"

    def test_extract_property_certificate(self, extractor):
        """测试房产证提取"""
        # 使用更清晰的格式
        full_text = """不动产权证书
权利人 王五
共有情况 单独所有
坐落 北京市朝阳区XX路XX号"""
        key_list = ["权利人", "共有情况", "坐落"]

        fields = extractor.extract_property_certificate(full_text, key_list)

        assert fields["权利人"] == "王五"
        assert fields["共有情况"] == "单独所有"
        assert "朝阳区" in fields["坐落"]
