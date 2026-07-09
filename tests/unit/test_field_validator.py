#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""field_validator 单元测试"""

import pytest

from ocr_three_layer_hybrid.field_validator import (
    FieldValidator,
    ValidationStatus,
    ValidationResult,
)


class TestValidationResult:
    """ValidationResult 属性测试"""

    def test_valid_is_valid(self):
        r = ValidationResult("姓名", "张三", ValidationStatus.VALID)
        assert r.is_valid is True
        assert r.needs_fallback is False

    def test_empty_is_valid(self):
        r = ValidationResult("姓名", "", ValidationStatus.EMPTY)
        assert r.is_valid is True
        assert r.needs_fallback is False

    def test_uncertain_is_valid(self):
        r = ValidationResult("自定义", "值", ValidationStatus.UNCERTAIN)
        assert r.is_valid is True
        assert r.needs_fallback is False

    def test_invalid_needs_fallback(self):
        r = ValidationResult("户号", "abc", ValidationStatus.INVALID, "格式错误")
        assert r.is_valid is False
        assert r.needs_fallback is True


class TestFieldValidator:
    """FieldValidator 测试"""

    def setup_method(self):
        self.validator = FieldValidator()

    # ===== 空值处理 =====

    def test_empty_value(self):
        r = self.validator.validate("户号", "")
        assert r.status == ValidationStatus.EMPTY

    def test_whitespace_value(self):
        r = self.validator.validate("户号", "   ")
        assert r.status == ValidationStatus.EMPTY

    # ===== 无规则 =====

    def test_unknown_field(self):
        r = self.validator.validate("自定义字段", "任意值")
        assert r.status == ValidationStatus.UNCERTAIN

    # ===== 户号（正则校验）=====

    def test_valid_huhao(self):
        r = self.validator.validate("户号", "005300251")
        assert r.status == ValidationStatus.VALID

    def test_invalid_huhao_too_short(self):
        r = self.validator.validate("户号", "123")
        assert r.status == ValidationStatus.INVALID

    def test_invalid_huhao_non_digit(self):
        r = self.validator.validate("户号", "abc12345")
        assert r.status == ValidationStatus.INVALID

    # ===== 性别 =====

    def test_valid_gender_male(self):
        r = self.validator.validate("性别", "男")
        assert r.status == ValidationStatus.VALID

    def test_valid_gender_female(self):
        r = self.validator.validate("性别", "女")
        assert r.status == ValidationStatus.VALID

    def test_invalid_gender(self):
        r = self.validator.validate("性别", "未知")
        assert r.status == ValidationStatus.INVALID

    # ===== 公民身份号码 =====

    def test_valid_id_number(self):
        r = self.validator.validate("公民身份号码", "340321199001011234")
        assert r.status == ValidationStatus.VALID

    def test_valid_id_number_with_x(self):
        r = self.validator.validate("公民身份号码", "34032119900101123X")
        assert r.status == ValidationStatus.VALID

    def test_invalid_id_number_too_short(self):
        r = self.validator.validate("公民身份号码", "12345")
        assert r.status == ValidationStatus.INVALID

    # ===== 姓名（中文姓名校验）=====

    def test_valid_chinese_name(self):
        r = self.validator.validate("姓名", "张三")
        assert r.status == ValidationStatus.VALID

    def test_invalid_name_too_short(self):
        r = self.validator.validate("姓名", "张")
        assert r.status == ValidationStatus.INVALID

    def test_invalid_name_english(self):
        r = self.validator.validate("姓名", "John Smith")
        assert r.status == ValidationStatus.INVALID

    # ===== 住址（地址关键词校验）=====

    def test_valid_address(self):
        r = self.validator.validate("住址", "安徽省蚌埠市蚌山区燕山乡定安村张庄219号")
        assert r.status == ValidationStatus.VALID

    def test_invalid_address_no_keyword(self):
        r = self.validator.validate("住址", "某个奇怪的地方")
        assert r.status == ValidationStatus.INVALID

    def test_invalid_address_too_short(self):
        r = self.validator.validate("住址", "北京市")
        assert r.status == ValidationStatus.INVALID  # 长度 < 6

    # ===== 批量校验 =====

    def test_validate_fields(self):
        fields = {
            "户号": "005300251",
            "性别": "男",
            "公民身份号码": "abc",  # 无效
        }
        results = self.validator.validate_fields(fields)
        assert len(results) == 3
        assert results["户号"].status == ValidationStatus.VALID
        assert results["性别"].status == ValidationStatus.VALID
        assert results["公民身份号码"].status == ValidationStatus.INVALID

    def test_get_failed_fields(self):
        fields = {
            "户号": "005300251",  # 有效
            "性别": "未知",       # 无效
            "公民身份号码": "abc",  # 无效
        }
        failed = self.validator.get_failed_fields(fields)
        assert "性别" in failed
        assert "公民身份号码" in failed
        assert "户号" not in failed

    def test_get_failed_fields_empty(self):
        fields = {"户号": "005300251", "性别": "男"}
        failed = self.validator.get_failed_fields(fields)
        assert failed == []

    # ===== 户别 =====

    def test_valid_hubie(self):
        r = self.validator.validate("户别", "非农业家庭户")
        assert r.status == ValidationStatus.VALID

    def test_invalid_hubie(self):
        r = self.validator.validate("户别", "城市户口")
        assert r.status == ValidationStatus.INVALID

    # ===== 日期格式 =====

    def test_valid_registration_date(self):
        r = self.validator.validate("登记日期", "2024年01月15日")
        assert r.status == ValidationStatus.VALID

    def test_valid_registration_date_dash(self):
        r = self.validator.validate("登记日期", "2024-01-15")
        assert r.status == ValidationStatus.VALID
