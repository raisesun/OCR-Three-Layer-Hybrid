#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段校验器
检查提取字段的合理性，判断是否需要VLM兜底重新提取

校验维度：
- 格式校验（正则匹配）
- 长度校验（最短/最长）
- 内容校验（包含关键词、字符类型等）
- 逻辑校验（字段间关系）
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ValidationStatus(str, Enum):
    """校验结果状态"""

    VALID = "valid"  # 通过校验
    EMPTY = "empty"  # 字段为空（不一定是错误）
    INVALID = "invalid"  # 校验失败
    UNCERTAIN = "uncertain"  # 无法判断（无规则）


@dataclass
class ValidationResult:
    """单字段校验结果"""

    field_name: str
    value: str
    status: ValidationStatus
    reason: str = ""

    @property
    def is_valid(self) -> bool:
        return self.status in (
            ValidationStatus.VALID,
            ValidationStatus.UNCERTAIN,
            ValidationStatus.EMPTY,
        )

    @property
    def needs_fallback(self) -> bool:
        return self.status == ValidationStatus.INVALID


class FieldValidator:
    """字段校验器

    根据预定义规则检查字段值的合理性。
    校验失败的字段将触发VLM兜底重新提取。

    Usage:
        validator = FieldValidator()
        result = validator.validate("户号", "005300251")
        if result.needs_fallback:
            # 触发VLM重新提取
            ...
    """

    # 字段校验规则
    # 每个字段可包含: pattern, min_len, max_len, contains, char_type, custom
    VALIDATION_RULES: Dict[str, Dict] = {
        # === 户口本 ===
        "户主姓名": {
            "min_len": 2,
            "max_len": 5,
            "char_type": "chinese_name",  # 中文姓名
        },
        "户号": {
            "pattern": r"^\d{5,12}$",
            "description": "5-12位数字",
        },
        "住址": {
            "min_len": 6,
            "description": "至少6个字符的详细地址",
        },
        "户别": {
            "pattern": r"^(农业|非农业).*(户|口)$",
            "description": "农业/非农业家庭户",
        },
        "公民身份号码": {
            "pattern": r"^\d{17}[\dXx]$",
            "description": "18位身份证号",
        },
        "姓名": {
            "min_len": 2,
            "max_len": 5,
            "char_type": "chinese_name",
        },
        "与户主关系": {
            "max_len": 5,
            "pattern": r"^(户主|妻|夫|子|女|长子|长女|次子|二女|孙子|孙女|父|母|兄弟|姐妹|祖父|祖母|外祖父|外祖母|其他)$",
            "description": "标准亲属关系",
        },
        "性别": {
            "pattern": r"^(男|女)$",
        },
        # === 身份证 ===
        # （公民身份号码已定义）
        # === 结婚证 ===
        "结婚证字号": {
            "pattern": r"^[一-鿿]\d{5,6}-\d{4}-\d{5,6}$",
            "description": "如：鄂340321-2022-000122",
        },
        "登记日期": {
            "pattern": r"^\d{4}[.\-/年]\d{1,2}[.\-/月]\d{1,2}[日]?$",
            "description": "日期格式",
        },
        "持证人": {
            "min_len": 2,
            "max_len": 5,
            "char_type": "chinese_name",
        },
        "男方姓名": {
            "min_len": 2,
            "max_len": 5,
            "char_type": "chinese_name",
        },
        "女方姓名": {
            "min_len": 2,
            "max_len": 5,
            "char_type": "chinese_name",
        },
        "男方身份证号": {
            "pattern": r"^\d{17}[\dXx]$",
        },
        "女方身份证号": {
            "pattern": r"^\d{17}[\dXx]$",
        },
        # === 发票 ===
        "发票代码": {
            "pattern": r"^\d{10,12}$",
            "description": "10-12位数字",
        },
        "发票号码": {
            "pattern": r"^\d{8}$",
            "description": "8位数字",
        },
        "价税合计": {
            "pattern": r"^[\d,.]+$",
            "description": "金额数字",
        },
        # === 合同/协议 ===
        "监管金额": {
            "pattern": r"^[\d,.]+.*元?$",
            "description": "金额",
        },
        "总价款": {
            "pattern": r"^[\d,.]+.*元?$",
            "description": "金额",
        },
        "建筑面积": {
            "pattern": r"^[\d,.]+.*平方米?$",
            "description": "面积",
        },
        # === 不动产权证书 ===
        "不动产单元号": {
            "pattern": r"^\d{20,}$",
            "description": "至少20位数字",
        },
    }

    # 中文地址关键词（至少包含一个）
    ADDRESS_KEYWORDS = [
        "省",
        "市",
        "区",
        "县",
        "镇",
        "乡",
        "路",
        "号",
        "街",
        "村",
        "弄",
        "栋",
        "幢",
        "室",
    ]

    def validate(self, field_name: str, value: str) -> ValidationResult:
        """
        校验单个字段

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            ValidationResult 对象
        """
        # 空值处理
        if not value or not value.strip():
            return ValidationResult(
                field_name=field_name,
                value=value or "",
                status=ValidationStatus.EMPTY,
                reason="字段为空",
            )

        value = value.strip()
        rules = self.VALIDATION_RULES.get(field_name)

        # 无规则 → 无法判断
        if rules is None:
            return ValidationResult(
                field_name=field_name,
                value=value,
                status=ValidationStatus.UNCERTAIN,
                reason="无校验规则",
            )

        # 长度校验
        min_len = rules.get("min_len")
        max_len = rules.get("max_len")
        if min_len and len(value) < min_len:
            return ValidationResult(
                field_name=field_name,
                value=value,
                status=ValidationStatus.INVALID,
                reason=f"长度{len(value)} < 最小{min_len}",
            )
        if max_len and len(value) > max_len:
            return ValidationResult(
                field_name=field_name,
                value=value,
                status=ValidationStatus.INVALID,
                reason=f"长度{len(value)} > 最大{max_len}",
            )

        # 正则格式校验
        pattern = rules.get("pattern")
        if pattern and not re.search(pattern, value):
            return ValidationResult(
                field_name=field_name,
                value=value,
                status=ValidationStatus.INVALID,
                reason=f"格式不匹配: {rules.get('description', pattern)}",
            )

        # 字符类型校验
        char_type = rules.get("char_type")
        if char_type == "chinese_name":
            if not re.match(r"^[一-鿿]{2,}$", value):
                # 允许少量非中文字符（如少数民族名字的·）
                chinese_ratio = len(re.findall(r"[一-鿿]", value)) / len(value)
                if chinese_ratio < 0.5:
                    return ValidationResult(
                        field_name=field_name,
                        value=value,
                        status=ValidationStatus.INVALID,
                        reason="姓名应主要为中文字符",
                    )

        # 地址校验（至少包含一个地址关键词）
        if field_name == "住址":
            if not any(kw in value for kw in self.ADDRESS_KEYWORDS):
                return ValidationResult(
                    field_name=field_name,
                    value=value,
                    status=ValidationStatus.INVALID,
                    reason="地址缺少地理关键词",
                )

        return ValidationResult(
            field_name=field_name,
            value=value,
            status=ValidationStatus.VALID,
            reason="校验通过",
        )

    def validate_fields(self, fields: Dict[str, str]) -> Dict[str, ValidationResult]:
        """
        批量校验所有字段

        Args:
            fields: 字段字典

        Returns:
            {字段名: ValidationResult} 字典
        """
        results = {}
        for field_name, value in fields.items():
            results[field_name] = self.validate(field_name, value)
        return results

    def get_failed_fields(self, fields: Dict[str, str]) -> List[str]:
        """
        获取需要VLM兜底的字段列表

        Args:
            fields: 字段字典

        Returns:
            校验失败的字段名列表
        """
        results = self.validate_fields(fields)
        failed = [name for name, result in results.items() if result.needs_fallback]
        if failed:
            logger.info(f"校验失败字段: {failed}")
            for name in failed:
                logger.info(f"  {name}: '{fields[name]}' - {results[name].reason}")
        return failed
