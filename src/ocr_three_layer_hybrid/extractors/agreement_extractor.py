# -*- coding: utf-8 -*-
"""协议书提取器

离婚协议书等字段提取。
"""

import re
from typing import Dict, List
from ocr_three_layer_hybrid.extractors.base_extractor import BaseExtractor
from ocr_three_layer_hybrid.interfaces import DocumentType


class AgreementExtractor(BaseExtractor):
    """协议书字段提取器"""

    def extract_divorce_agreement(
    self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
    """从离婚协议文本中提取字段"""
    fields = {}

    # ===== 男方姓名 =====
    if "男方姓名" in key_list:
        match = re.search(r"男方姓名\s*[:：]\s*(\S+)", full_text)
        if not match:
            match = re.search(r"男\s*方\s*[:：]\s*(\S+)", full_text)
        fields["男方姓名"] = match.group(1).strip() if match else ""

    # ===== 女方姓名 =====
    if "女方姓名" in key_list:
        match = re.search(r"女方姓名\s*[:：]\s*(\S+)", full_text)
        if not match:
            match = re.search(r"女\s*方\s*[:：]\s*(\S+)", full_text)
        fields["女方姓名"] = match.group(1).strip() if match else ""

    # ===== 离婚日期 =====
    if "离婚日期" in key_list:
        # 模式1: "离婚日期：2018年7月30日"
        match = re.search(
            r"离婚日期\s*[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)", full_text
        )
        if match:
            fields["离婚日期"] = match.group(1)
        else:
            # 策略：取最后一个非结婚登记日期
            all_dates = re.findall(r"(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            marriage_date = None
            m = re.search(
                r"(\d{4}年\d{1,2}月\d{1,2}日)[^\n]{0,30}结婚登记", full_text
            )
            if m:
                marriage_date = m.group(1)
            # 取最后一个不是结婚日期的日期（即签署日期）
            non_marriage_dates = [d for d in all_dates if d != marriage_date]
            if non_marriage_dates:
                fields["离婚日期"] = non_marriage_dates[-1]

    # ===== 子女抚养 =====
    if "子女抚养" in key_list:
        # "一、子女抚养问题：婚后子女已成年。"
        match = re.search(r"子女抚养[^\n]*?[:：]\s*([^\n]+)", full_text)
        if not match:
            match = re.search(r"子女抚养\s*([^\n]+)", full_text)
        value = match.group(1).strip() if match else ""
        # 清理：截取到下一个编号条目之前
        value = re.split(r"[一二三四五六七八九十]+[、.]", value)[0].strip()
        fields["子女抚养"] = value

    # ===== 财产分割约定 =====
    if "财产分割约定" in key_list:
        # "二、财产分割及债务、债权处理问题：\n 1、婚后男女双方无共同财产分割\n 2、婚后男女双方无共同债务..."
        # 先找到该条款区域
        section_match = re.search(
            r"财产分割[^\n]*?[:：]([\s\S]+?)(?:三[、.]|其他协议|$)", full_text
        )
        if section_match:
            section_text = section_match.group(1)
            # 提取各子条款内容
            sub_items = re.findall(r"\d+[、.]\s*([^\n]+)", section_text)
            if sub_items:
                # 合并所有子条款，去除尾部日期等噪声
                parts = []
                for item in sub_items:
                    # 去除尾部的数字日期格式 "2018.7.30"
                    item = re.sub(r"\s*\d{4}\.\d{1,2}\.\d{1,2}\s*", "", item)
                    # 去除尾部句号
                    item = item.rstrip("。")
                    if item.strip():
                        parts.append(item.strip())
                # 去除后续子条款中与第一项重复的主语前缀
                if len(parts) > 1:
                    first = parts[0]
                    # 尝试提取主语（取第一个谓语之前的部分）
                    # "婚后男女双方无共同财产分割" → 主语 "婚后男女双方"
                    prefix_match = re.match(r"^(.+?)(无|有|应|须|由|已|不)", first)
                    if prefix_match:
                        subject = prefix_match.group(1)
                        for i in range(1, len(parts)):
                            if parts[i].startswith(subject):
                                parts[i] = parts[i][len(subject) :]
                value = "，".join(parts)
            else:
                value = section_text.strip()
        else:
            # 简单模式: "财产分割：xxx"
            match = re.search(r"财产分割[^\n]*?[:：]?\s*([^\n]+)", full_text)
            value = match.group(1).strip() if match else ""
        fields["财产分割约定"] = value

    return fields
