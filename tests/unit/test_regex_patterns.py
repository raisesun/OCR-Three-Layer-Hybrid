#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试通用正则表达式模式和提取函数
"""

import pytest
from ocr_three_layer_hybrid.extractors.regex_patterns import (
    extract_id_card_number,
    extract_gender,
    extract_name,
    extract_ethnicity,
    extract_issuing_authority,
    extract_validity_period,
    extract_householder_name,
    extract_address,
    extract_birth_date,
    extract_household_type,
    extract_household_number,
)


class TestRegexPatterns:
    """测试通用正则表达式提取函数"""

    def test_extract_id_card_number(self):
        """测试身份证号提取"""
        # 标准格式
        text = "姓名 张三 公民身份号码 110101199001011234"
        assert extract_id_card_number(text) == "110101199001011234"

        # 最后一位是X
        text = "身份证号 11010119900101123X"
        assert extract_id_card_number(text) == "11010119900101123X"

        # 最后一位是小写x
        text = "身份证号 11010119900101123x"
        assert extract_id_card_number(text) == "11010119900101123x"

        # 未找到
        text = "姓名 张三"
        assert extract_id_card_number(text) is None

    def test_extract_gender(self):
        """测试性别提取"""
        # 标准格式
        text = "性别 男"
        assert extract_gender(text) == "男"

        # 有冒号
        text = "性别：女"
        assert extract_gender(text) == "女"

        # 有空格
        text = "性 别 男"
        assert extract_gender(text) == "男"

        # 未找到
        text = "姓名 张三"
        assert extract_gender(text) is None

    def test_extract_name(self):
        """测试姓名提取"""
        # 标准格式
        text = "姓名 张三"
        assert extract_name(text) == "张三"

        # 有冒号
        text = "姓名：李四"
        assert extract_name(text) == "李四"

        # 排除前缀（避免匹配"户主姓名"）
        text = "户主姓名 李大山"
        assert extract_name(text, exclude_prefixes=["户主"]) is None

        # 多行格式
        text = "姓\n张三\n"
        assert extract_name(text) == "张三"

        # 未找到
        text = "性别 男"
        assert extract_name(text) is None

    def test_extract_ethnicity(self):
        """测试民族提取"""
        # 标准格式
        text = "民族 汉"
        assert extract_ethnicity(text) == "汉"

        # 带"族"字（会匹配1-2个汉字）
        text = "民族 满族"
        # 注意：模式匹配1-2个汉字，所以会匹配"满族"
        result = extract_ethnicity(text)
        assert result in ["满", "满族"]

        # 未找到
        text = "姓名 张三"
        assert extract_ethnicity(text) is None

    def test_extract_issuing_authority(self):
        """测试签发机关提取"""
        # 标准格式
        text = "签发机关 北京市公安局朝阳分局"
        assert extract_issuing_authority(text) == "北京市公安局朝阳分局"

        # 包含"派出所"
        text = "签发机关 北京市公安局朝阳分局三里屯派出所"
        assert extract_issuing_authority(text) == "北京市公安局朝阳分局三里屯派出所"

        # 未找到
        text = "姓名 张三"
        assert extract_issuing_authority(text) is None

    def test_extract_validity_period(self):
        """测试有效期限提取"""
        # 日期范围
        text = "有效期限 2020.01.01-2040.01.01"
        assert extract_validity_period(text) == "2020.01.01-2040.01.01"

        # 长期
        text = "有效期限 2020.01.01-长期"
        assert extract_validity_period(text) == "2020.01.01-长期"

        # 未找到
        text = "签发机关 北京市公安局"
        assert extract_validity_period(text) is None

    def test_extract_householder_name(self):
        """测试户主姓名提取"""
        # 标准格式
        text = "户主姓名 李大山"
        assert extract_householder_name(text) == "李大山"

        # 有空格
        text = "户 主 姓 名 李大山"
        assert extract_householder_name(text) == "李大山"

        # 宽松格式
        text = "户主 姓名 李大山"
        assert extract_householder_name(text) == "李大山"

        # 未找到
        text = "姓名 张三"
        assert extract_householder_name(text) is None

    def test_extract_address(self):
        """测试地址提取"""
        # 标准住址
        text = "住址 北京市朝阳区XX路XX号"
        assert "朝阳区" in extract_address(text)

        # 地址
        text = "地址 北京市海淀区XX路XX号"
        assert "海淀区" in extract_address(text)

        # 排除"变动"
        text = "住址变动 北京市朝阳区"
        assert extract_address(text) is None

        # 未找到
        text = "姓名 张三"
        assert extract_address(text) is None

    def test_extract_birth_date(self):
        """测试出生日期提取"""
        # 标准格式
        text = "出生 1990年1月1日"
        assert extract_birth_date(text) == "1990年1月1日"

        # 有空格
        text = "出 生 1990年1月1日"
        assert extract_birth_date(text) == "1990年1月1日"

        # 分别提取年月日
        text = "1990年 1月 1日"
        assert extract_birth_date(text) == "1990年1月1日"

        # 未找到
        text = "姓名 张三"
        assert extract_birth_date(text) is None

    def test_extract_household_type(self):
        """测试户别提取"""
        # 标准格式
        text = "户别 非农业家庭户"
        assert extract_household_type(text) == "非农业家庭户"

        # 有空格
        text = "户 别 农业家庭户"
        assert extract_household_type(text) == "农业家庭户"

        # 到下一个字段结束
        text = "户别 非农业家庭户\n户主姓名 李大山"
        assert extract_household_type(text) == "非农业家庭户"

        # 排除无效值
        text = "户别 户别"
        assert extract_household_type(text) is None

        # 未找到
        text = "姓名 张三"
        assert extract_household_type(text) is None

    def test_extract_household_number(self):
        """测试户号提取"""
        # 标准格式
        text = "户号 A123456"
        assert extract_household_number(text) == "A123456"

        # 纯数字
        text = "户号 123456"
        assert extract_household_number(text) == "123456"

        # 有空格
        text = "户 号 A123456"
        assert extract_household_number(text) == "A123456"

        # 行首数字（回退）
        text = "123456\n"
        assert extract_household_number(text) == "123456"

        # 未找到
        text = "姓名 张三"
        assert extract_household_number(text) is None
