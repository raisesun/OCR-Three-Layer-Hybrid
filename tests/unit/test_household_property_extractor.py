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


class TestPropertyCertificateFirstPage:
    """测试不动产权证书首页提取（编号 + 登记日期）"""

    @pytest.fixture
    def extractor(self):
        return HouseholdPropertyExtractor()

    def test_extract_bianhao_format1(self, extractor):
        """测试编号提取：格式1 — 编号 № XXXXX"""
        text = "编号 № 34026135082\n登记日期 2025年03月20日"
        fields = extractor.extract_property_certificate_first_page(text, ["编号", "登记日期"])
        assert fields["编号"] == "34026135082"

    def test_extract_bianhao_format2(self, extractor):
        """测试编号提取：格式2 — 编号: XXXXX"""
        text = "编号: A12345678"
        fields = extractor.extract_property_certificate_first_page(text, ["编号"])
        assert fields["编号"] == "A12345678"

    def test_extract_bianhao_format3(self, extractor):
        """测试编号提取：格式3 — 皖(2025)蚌埠市不动产权第XXXXX号"""
        text = "皖（2025）蚌埠市不动产权第0058326号"
        fields = extractor.extract_property_certificate_first_page(text, ["编号"])
        assert fields["编号"] == "0058326"

    def test_extract_bianhao_not_found(self, extractor):
        """测试编号不存在时返回空字符串"""
        text = "这是一段无关的文本"
        fields = extractor.extract_property_certificate_first_page(text, ["编号"])
        assert fields["编号"] == ""

    def test_extract_dengji_riqi_format1(self, extractor):
        """测试登记日期提取：格式1 — 2025年03月20日"""
        text = "登记日期 2025年03月20日"
        fields = extractor.extract_property_certificate_first_page(text, ["登记日期"])
        assert "2025" in fields["登记日期"]
        assert "03" in fields["登记日期"]
        assert "20" in fields["登记日期"]

    def test_extract_dengji_riqi_format2(self, extractor):
        """测试登记日期提取：格式2 — 2025-03-20"""
        text = "登记日期：2025-03-20"
        fields = extractor.extract_property_certificate_first_page(text, ["登记日期"])
        assert "2025" in fields["登记日期"]

    def test_extract_dengji_riqi_not_found(self, extractor):
        """测试登记日期不存在时返回空字符串"""
        text = "这是无关文本"
        fields = extractor.extract_property_certificate_first_page(text, ["登记日期"])
        assert fields["登记日期"] == ""

    def test_extract_both_fields(self, extractor):
        """测试同时提取编号和登记日期"""
        text = "编号 № 34026135082 登记日期 2025年03月20日"
        fields = extractor.extract_property_certificate_first_page(text, ["编号", "登记日期"])
        assert fields["编号"] == "34026135082"
        assert "2025" in fields["登记日期"]

    def test_only_requested_fields_returned(self, extractor):
        """测试只返回 key_list 中请求的字段"""
        text = "编号 № 34026135082 登记日期 2025年03月20日"
        fields = extractor.extract_property_certificate_first_page(text, ["编号"])
        assert "编号" in fields
        assert "登记日期" not in fields


class TestHouseholdRegisterNewFields:
    """测试户口本提取器新增字段：出生日期 + 民族"""

    @pytest.fixture
    def extractor(self):
        return HouseholdPropertyExtractor()

    def test_extract_birth_date(self, extractor):
        """测试出生日期提取"""
        text = "姓名 张三\n出生日期 1990年1月15日\n公民身份号码 340123199001011234"
        fields = extractor.extract_household_register(text, ["出生日期"])
        assert "1990" in fields["出生日期"]
        assert "1" in fields["出生日期"]
        assert "15" in fields["出生日期"]

    def test_extract_birth_date_dot_format(self, extractor):
        """测试出生日期提取：点号格式"""
        text = "出生日期：1990.01.15"
        fields = extractor.extract_household_register(text, ["出生日期"])
        assert "1990" in fields["出生日期"]

    def test_extract_birth_date_not_found(self, extractor):
        """测试出生日期不存在时返回空"""
        text = "姓名 张三\n公民身份号码 340123199001011234"
        fields = extractor.extract_household_register(text, ["出生日期"])
        assert fields["出生日期"] == ""

    def test_extract_minzu(self, extractor):
        """测试民族提取"""
        text = "姓名 张三\n民族 汉\n公民身份号码 340123199001011234"
        fields = extractor.extract_household_register(text, ["民族"])
        assert fields["民族"] == "汉"

    def test_extract_minzu_with_spaces(self, extractor):
        """测试民族提取：OCR 输出带空格"""
        text = "民 族 回族"
        fields = extractor.extract_household_register(text, ["民族"])
        assert fields["民族"] == "回族"

    def test_extract_minzu_not_found(self, extractor):
        """测试民族不存在时返回空"""
        text = "姓名 张三\n公民身份号码 340123199001011234"
        fields = extractor.extract_household_register(text, ["民族"])
        assert fields["民族"] == ""

    def test_combined_personal_page_fields(self, extractor):
        """测试个人页完整字段提取（含新增字段）"""
        text = """常住人口登记卡
姓名 李四
与户主关系 之子
性别 男
民族 汉
出生日期 2000年6月15日
公民身份号码 340123200006151234"""
        key_list = ["姓名", "与户主关系", "性别", "出生日期", "民族", "公民身份号码"]
        fields = extractor.extract_household_register(text, key_list)
        assert fields["姓名"] == "李四"
        assert fields["与户主关系"] == "之子"
        assert fields["性别"] == "男"
        assert fields["民族"] == "汉"
        assert "2000" in fields["出生日期"]
        assert fields["公民身份号码"] == "340123200006151234"
