#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用正则表达式模式和提取函数

提取各extractor中重复的正则表达式模式，提供统一的提取接口。
"""

import re
from typing import Optional, List


# ============================================================================
# 通用常量模式
# ============================================================================

# 身份证号：18位，最后一位可以是数字或X/x
ID_CARD_NUMBER_PATTERN = r"(\d{17}[\dXx])"

# 性别：男/女
GENDER_PATTERN = r"性\s*别\s*[:：]?\s*(男|女)"

# 签发机关：包含"公安局"、"分局"等关键词
ISSUING_AUTHORITY_PATTERN = r"签发机关\s*([一-龥()（）]+(?:公安局|分局|派出所))"

# 户主姓名
HOUSEHOLDER_NAME_PATTERN = r"户\s*主\s*姓\s*名\s*([^\s]+)"

# 姓名（通用）
NAME_PATTERN = r"姓\s*名\s*[:：]?\s*([^\s]+)"

# 民族
ETHNICITY_PATTERN = r"(?:民)?族\s*([一-鿿]{1,2})"

# 出生日期：YYYY年MM月DD日
BIRTH_DATE_PATTERN = r"出\s*生\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"

# 有效期限：日期范围或长期
VALIDITY_PERIOD_RANGE_PATTERN = r"有效期限\s*(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})"
VALIDITY_PERIOD_LONG_TERM_PATTERN = r"有效期限\s*(\d{4}\.\d{2}\.\d{2}-长期)"

# 住址/地址（排除"变动"等干扰词）
ADDRESS_PATTERN = r"(?<![一-鿿])(?:住\s*址|地\s*址)\s*(?!变动)([^\n]+)"


# ============================================================================
# 通用提取函数
# ============================================================================

def extract_id_card_number(full_text: str) -> Optional[str]:
    """提取身份证号码

    Args:
        full_text: OCR识别的完整文本

    Returns:
        18位身份证号码，如果未找到则返回None
    """
    match = re.search(ID_CARD_NUMBER_PATTERN, full_text)
    return match.group(1) if match else None


def extract_gender(full_text: str) -> Optional[str]:
    """提取性别

    Args:
        full_text: OCR识别的完整文本

    Returns:
        "男"或"女"，如果未找到则返回None
    """
    match = re.search(GENDER_PATTERN, full_text)
    return match.group(1) if match else None


def extract_name(full_text: str, exclude_prefixes: Optional[List[str]] = None) -> Optional[str]:
    """提取姓名

    Args:
        full_text: OCR识别的完整文本
        exclude_prefixes: 需要排除的前缀列表（如["户主"]避免匹配"户主姓名"）

    Returns:
        姓名（2-4个汉字），如果未找到则返回None
    """
    # 构建负向后瞻，排除特定前缀
    pattern = NAME_PATTERN
    if exclude_prefixes:
        # 例如：(?<!户主)姓\s*名\s*[:：]?\s*([^\s]+)
        negative_lookbehind = "".join([f"(?<!{prefix})" for prefix in exclude_prefixes])
        pattern = negative_lookbehind + NAME_PATTERN

    match = re.search(pattern, full_text)
    if match:
        name = match.group(1).strip()
        # 验证是否为有效的姓名（2-4个汉字）
        if re.match(r"^[一-鿿]{2,4}$", name):
            return name

    # 回退：尝试多行匹配
    # 例如：
    # 姓
    # 张三
    match = re.search(r"姓\s*\n\s*([一-鿿]{2,4})\s*\n", full_text)
    if match:
        return match.group(1)

    return None


def extract_ethnicity(full_text: str) -> Optional[str]:
    """提取民族

    Args:
        full_text: OCR识别的完整文本

    Returns:
        民族名称（如"汉"、"满"），如果未找到则返回None
    """
    match = re.search(ETHNICITY_PATTERN, full_text)
    return match.group(1) if match else None


def extract_issuing_authority(full_text: str) -> Optional[str]:
    """提取签发机关

    Args:
        full_text: OCR识别的完整文本

    Returns:
        签发机关名称（如"北京市公安局朝阳分局"），如果未找到则返回None
    """
    match = re.search(ISSUING_AUTHORITY_PATTERN, full_text)
    return match.group(1) if match else None


def extract_validity_period(full_text: str) -> Optional[str]:
    """提取有效期限

    Args:
        full_text: OCR识别的完整文本

    Returns:
        有效期限（如"2020.01.01-2040.01.01"或"2020.01.01-长期"），如果未找到则返回None
    """
    # 优先匹配日期范围
    match = re.search(VALIDITY_PERIOD_RANGE_PATTERN, full_text)
    if match:
        return match.group(1)

    # 尝试匹配长期
    match = re.search(VALIDITY_PERIOD_LONG_TERM_PATTERN, full_text)
    if match:
        return match.group(1)

    return None


def extract_householder_name(full_text: str) -> Optional[str]:
    """提取户主姓名

    Args:
        full_text: OCR识别的完整文本

    Returns:
        户主姓名，如果未找到则返回None
    """
    # 优先匹配标准格式
    match = re.search(HOUSEHOLDER_NAME_PATTERN, full_text)
    if match:
        return match.group(1)

    # 回退：尝试宽松格式
    match = re.search(r"户主\s+姓名\s*([^\s]+)", full_text)
    return match.group(1) if match else None


def extract_address(full_text: str, keywords: Optional[List[str]] = None) -> Optional[str]:
    """提取地址（住址/地址）

    Args:
        full_text: OCR识别的完整文本
        keywords: 地址关键词列表，默认为["住址", "地址"]

    Returns:
        地址文本，如果未找到则返回None
    """
    if keywords is None:
        keywords = ["住址", "地址"]

    for keyword in keywords:
        # 构建模式：排除前面是汉字，排除后面是"变动"
        pattern = rf"(?<![一-鿿]){keyword}\s*(?!变动)([^\n]+)"
        match = re.search(pattern, full_text)
        if match:
            address = match.group(1).strip()
            # 验证是否包含地址特征词
            if re.search(r"(省|市|区|县|镇|乡|村|路|号|室)", address):
                return address

    return None


def extract_birth_date(full_text: str) -> Optional[str]:
    """提取出生日期

    Args:
        full_text: OCR识别的完整文本

    Returns:
        出生日期（格式：YYYY年MM月DD日），如果未找到则返回None
    """
    match = re.search(BIRTH_DATE_PATTERN, full_text)
    if match:
        year, month, day = match.groups()
        return f"{year}年{month}月{day}日"

    # 回退：分别提取年月日（更宽松的模式）
    # 匹配"1990年"或"1990 年"
    year_match = re.search(r"((?:19|20)\d{2})\s*年", full_text)
    month_match = re.search(r"(\d{1,2})\s*月", full_text)
    day_match = re.search(r"(\d{1,2})\s*日", full_text)

    if year_match and month_match and day_match:
        year = year_match.group(1)
        month = month_match.group(1)
        day = day_match.group(1)
        return f"{year}年{month}月{day}日"

    return None


def extract_household_type(full_text: str) -> Optional[str]:
    """提取户别（如"非农业家庭户"、"农业家庭户"）

    Args:
        full_text: OCR识别的完整文本

    Returns:
        户别类型，如果未找到则返回None
    """
    # 匹配"户别 XXX"或"户 别 XXX"，到下一个字段标签或换行符
    match = re.search(r"户\s*别\s+(.+?)(?=\n|户\s*主|户\s*号|住\s*址|$)", full_text, re.MULTILINE)
    if match:
        value = match.group(1).strip()
        # 排除无效值
        if value and value not in ("户别", "户 别"):
            return value
    return None


def extract_household_number(full_text: str) -> Optional[str]:
    """提取户号

    Args:
        full_text: OCR识别的完整文本

    Returns:
        户号（字母数字组合），如果未找到则返回None
    """
    # 优先匹配"户号 XXX"格式
    match = re.search(r"户\s*号\s*([A-Z0-9]+)", full_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # 回退：尝试匹配纯数字户号
    match = re.search(r"户\s*号\s*(\d+)", full_text)
    if match:
        return match.group(1)

    # 最终回退：尝试匹配行首的6-12位数字
    match = re.search(r"^([0-9]{6,12})\s*\n", full_text, re.MULTILINE)
    return match.group(1) if match else None
