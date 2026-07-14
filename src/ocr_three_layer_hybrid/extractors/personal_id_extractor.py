# -*- coding: utf-8 -*-
"""个人证件提取器

身份证、结婚证、离婚证字段提取。
"""

import re
from typing import Dict, List

from ocr_three_layer_hybrid.extractors.base_extractor import BaseExtractor
from ocr_three_layer_hybrid.extractors.regex_patterns import (
    extract_id_card_number,
    extract_gender,
    extract_name,
    extract_ethnicity,
    extract_issuing_authority,
    extract_validity_period,
    extract_address,
    extract_birth_date,
)
from ocr_three_layer_hybrid.interfaces import DocumentType


class PersonalIdExtractor(BaseExtractor):
    """个人证件字段提取器

    支持：身份证（正反面）、结婚证、离婚证
    """

    def extract_id_card(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从身份证文本中提取字段（正面+背面）

        支持两种格式：
        1. 标准格式：有字段标签（姓名、性别、民族等）
        2. 无标签格式：OCR只输出值，没有字段标签
        """
        fields: Dict[str, str] = {}

        # 检测是否为无标签格式（通过检查是否有"姓名"、"性别"等标签）
        has_labels = any(
            keyword in full_text for keyword in ["姓名", "性别", "民族", "出生", "住址"]
        )

        if has_labels:
            # 标准格式：使用标签匹配
            self.extract_id_card_with_labels(full_text, key_list, fields)
        else:
            # 无标签格式：使用位置和模式匹配
            self.extract_id_card_without_labels(full_text, key_list, fields)

        return fields

    def extract_id_card_with_labels(
        self, full_text: str, key_list: List[str], fields: Dict[str, str]
    ):
        """标准格式：有字段标签的身份证提取"""
        # 正面字段
        if "姓名" in key_list:
            # 格式1（优先）：标签+同行值 "姓名XXX" 或 "姓名 XXX"（预处理后的常见格式）
            # 这种格式在身份证正面和预处理后都常见
            # 注意：预处理可能移除字间空格，所以名字后可能是任何非中文字符或行尾
            match = re.search(
                r"(?<!户主)姓\s*名\s*[:：]?\s*([一-鿿]{2,4})(?=[\s\d\-—:：;；,，.。、/／()（）\[\]【】]|$|[^一-鿿])", full_text
            )
            # 格式2：值+标签 "XXX\n姓名"（OCR输出值在标签之前）
            if not match:
                match = re.search(r"([一-鿿]{2,4})\s*\n\s*姓名", full_text)
                # 验证：排除字段标签和常见误匹配
                if match:
                    candidate = match.group(1)
                    if candidate in (
                        "签发机关",
                        "性别",
                        "民族",
                        "出生",
                        "住址",
                        "公民身份号码",
                        "有效期限",
                        "性别男",
                        "性别女",
                        "民族汉",  # 预处理后常见的误匹配
                    ):
                        match = None  # 重置匹配，继续查找
            if match:
                candidate = match.group(1)
                # 再次验证：排除字段标签
                if candidate not in (
                    "签发机关",
                    "性别",
                    "民族",
                    "出生",
                    "住址",
                    "公民身份号码",
                    "有效期限",
                    "性别男",
                    "性别女",
                    "民族汉",
                ):
                    fields["姓名"] = candidate
                else:
                    fields["姓名"] = ""
            else:
                fields["姓名"] = ""

        if "性别" in key_list:
            match = re.search(r"性别\s*(男|女)", full_text)
            if not match:
                match = re.search(r"\b(男|女)\b", full_text)
            fields["性别"] = match.group(1) if match else ""

        if "民族" in key_list:
            match = re.search(r"民族\s*([^\s]+)", full_text)
            fields["民族"] = match.group(1) if match else ""

        if "出生" in key_list or "出生日期" in key_list:
            # OCR 输出可能有空格：出生 2004 年 8 月 3 日
            match = re.search(
                r"出生\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", full_text
            )
            value = match.group(1) if match else ""
            # 标准化：去除日期内空格 "2004 年 8 月 3 日" → "2004年8月3日"
            if value:
                value = re.sub(r"\s+", "", value)
            if "出生" in key_list:
                fields["出生"] = value
            if "出生日期" in key_list:
                fields["出生日期"] = value

        if "住址" in key_list:
            candidate = ""
            # 格式1（优先）：标签+同行值 "住址XXX"（可能跨多行）
            # 匹配"住址"后的地址内容，允许中间有其他字段（OCR可能按位置识别）
            match = re.search(
                r"住址\s*([一-鿿]+(?:省|市|区|县|镇|乡|村|路|号|室)[^\n]*)", full_text
            )
            if match:
                candidate = match.group(1).strip()
                # 尝试查找后续行中是否有地址的剩余部分
                # 查找当前行之后的行，看是否有地址特征词
                lines_after = full_text[match.end() :].split("\n")
                for line in lines_after[:5]:  # 只检查后面5行
                    line = line.strip()
                    # 如果行包含地址特征词且不是其他字段标签
                    if any(
                        kw in line for kw in ["镇", "乡", "村", "路", "号", "室"]
                    ) and not any(
                        label in line
                        for label in ["出生", "性别", "民族", "公民身份", "签发"]
                    ):
                        candidate += line
                        break
            # 格式2：标签+换行+多行地址 "住址\n安徽省...\n乡..."
            if not candidate:
                match = re.search(
                    r"住址\s*\n\s*(.+?)(?:\n\s*公民身份号码|\n\s*姓名|\n\s*$)",
                    full_text,
                    re.DOTALL,
                )
                if match:
                    candidate = re.sub(r"\s*\n\s*", "", match.group(1)).strip()
            # 格式3：值+标签 "XXX\n住址"
            if not candidate:
                match = re.search(
                    r"(.+?(?:省|市|区|县|镇|乡|村|路|号|室)[^\n]*)\s*\n\s*住址",
                    full_text,
                )
                if match:
                    candidate = match.group(1).strip()
            # 排除政府机关名称（如"蚌埠市公安局蚌山分局"）
            if candidate and not re.search(r"(公安局|分局|派出所|人民政府)", candidate):
                fields["住址"] = candidate
            else:
                fields["住址"] = ""

        if "公民身份号码" in key_list:
            id_number = extract_id_card_number(full_text)
            fields["公民身份号码"] = id_number.upper() if id_number else ""

        # 背面字段：签发机关
        if "签发机关" in key_list:
            fields["签发机关"] = extract_issuing_authority(full_text) or ""

        # 背面字段：有效期限
        if "有效期限" in key_list:
            fields["有效期限"] = extract_validity_period(full_text) or ""

    def extract_id_card_without_labels(
        self, full_text: str, key_list: List[str], fields: Dict[str, str]
    ):
        """无标签格式：OCR只输出值，没有字段标签

        典型OCR输出：
        公民身份
        1994
        安徽省蚌埠市淮上区沫河
        口镇汪邢村朱刘101号
        男
        刘开顺
        3月
        族汉
        340322199403014698
        """
        lines = [line.strip() for line in full_text.split("\n") if line.strip()]

        # 提取18位身份证号（最可靠的标识）
        id_number = ""
        if "公民身份号码" in key_list:
            match = re.search(r"(\d{17}[\dXx])", full_text)
            if match:
                id_number = match.group(1).upper()
                fields["公民身份号码"] = id_number

        # 提取性别（男/女）
        gender = ""
        if "性别" in key_list:
            for line in lines:
                if line in ["男", "女"]:
                    gender = line
                    fields["性别"] = gender
                    break

        # 提取姓名（2-4个中文字符，排除常见非姓名词）
        name = ""
        if "姓名" in key_list:
            # 查找2-4个中文字符的行
            for line in lines:
                if re.match(r"^[一-鿿]{2,4}$", line):
                    # 排除常见非姓名词（包括身份证背面标签）
                    if line not in [
                        "男",
                        "女",
                        "汉族",
                        "民族",
                        "出生",
                        "住址",
                        "公民身份",
                        "签发机关",
                        "有效期限",
                        "中华人民共和国",
                        "居民身份证",
                    ]:
                        name = line
                        fields["姓名"] = name
                        break

        # 提取民族（处理"族汉"、"民族汉"等变体）
        ethnicity = ""
        if "民族" in key_list:
            # 匹配"族X"或"民族X"
            match = re.search(r"(?:民)?族\s*([一-鿿]{1,2})", full_text)
            if match:
                ethnicity = match.group(1)
                fields["民族"] = ethnicity

        # 提取出生日期（年份+月份）
        birth = ""
        if "出生" in key_list or "出生日期" in key_list:
            # 查找年份（4位数字）
            year_match = re.search(r"\b(19|20)\d{2}\b", full_text)
            year = year_match.group(0) if year_match else ""

            # 查找月份（1-12月）
            month_match = re.search(r"(\d{1,2})\s*月", full_text)
            month = month_match.group(1) if month_match else ""

            # 查找日期（1-31日）
            day_match = re.search(r"(\d{1,2})\s*日", full_text)
            day = day_match.group(1) if day_match else ""

            if year and month:
                birth = f"{year}年{month}月"
                if day:
                    birth += f"{day}日"
                if "出生" in key_list:
                    fields["出生"] = birth
                if "出生日期" in key_list:
                    fields["出生日期"] = birth

        # 提取住址（包含省/市/区/县/镇/乡/村/路/号的连续文本）
        address = ""
        if "住址" in key_list:
            # 查找包含地址关键词的行
            address_lines = []
            for i, line in enumerate(lines):
                if any(
                    keyword in line
                    for keyword in [
                        "省",
                        "市",
                        "区",
                        "县",
                        "镇",
                        "乡",
                        "村",
                        "路",
                        "号",
                    ]
                ):
                    # 排除政府机关名称（如"蚌埠市公安局蚌山分局"）
                    if re.search(r"(公安局|分局|派出所|人民政府)", line):
                        continue
                    # 收集连续的地址行
                    address_lines.append(line)
                    # 检查下一行是否也是地址的一部分
                    if i + 1 < len(lines) and any(
                        keyword in lines[i + 1]
                        for keyword in ["镇", "乡", "村", "路", "号", "室"]
                    ):
                        # 也要排除下一行是政府机关的情况
                        if not re.search(
                            r"(公安局|分局|派出所|人民政府)", lines[i + 1]
                        ):
                            address_lines.append(lines[i + 1])
                        break

            if address_lines:
                address = "".join(address_lines)
                fields["住址"] = address

        # 背面字段：签发机关（即使正面标签缺失，背面标签也可能存在）
        if "签发机关" in key_list and "签发机关" not in fields:
            authority = extract_issuing_authority(full_text)
            if authority:
                fields["签发机关"] = authority

        # 背面字段：有效期限
        if "有效期限" in key_list and "有效期限" not in fields:
            period = extract_validity_period(full_text)
            if period:
                fields["有效期限"] = period

    def extract_marriage_certificate(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """从结婚证文本中提取字段"""
        fields = {}

        if "持证人" in key_list:
            # OCR 可能输出 "持 证 人"（字间有空格）
            match = re.search(r"持\s*证\s*人\s*([^\s]+)", full_text)
            fields["持证人"] = match.group(1) if match else ""

        if "登记日期" in key_list:
            match = re.search(r"登记日期\s*(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            fields["登记日期"] = match.group(1) if match else ""

        if "结婚证字号" in key_list:
            # OCR 可能输出 "结 婚 证 字 号"，值可能包含中文字符如 "皖固镇结字第010800316号"
            match = re.search(r"结\s*婚\s*证\s*字\s*号\s*([^\n]+)", full_text)
            value = ""
            if match:
                raw = match.group(1).strip()
                # 去除值内空格："J 340322 - 2025 - 000779" → "J340322-2025-000779"
                value = re.sub(r"\s+", "", raw)
            fields["结婚证字号"] = value

        if "男方姓名" in key_list:
            match = re.search(r"男方姓名\s*([^\s]+)", full_text)
            if not match:
                # 允许姓名和性别之间有其他字段（国籍、证件号等）
                match = re.search(
                    r"姓名\s*([^\s]+)(?:(?!姓名).)*?性别\s*男",
                    full_text,
                    re.DOTALL,
                )
            fields["男方姓名"] = match.group(1) if match else ""

        if "女方姓名" in key_list:
            match = re.search(r"女方姓名\s*([^\s]+)", full_text)
            if not match:
                # 查找姓名+性别女的组合（允许中间有其他字段）
                persons = re.findall(
                    r"姓名\s*([^\s]+)(?:(?!姓名).)*?性别\s*(男|女)",
                    full_text,
                    re.DOTALL,
                )
                for name, gender in persons:
                    if gender == "女":
                        fields["女方姓名"] = name
                        break
            else:
                fields["女方姓名"] = match.group(1)

        if "男方身份证号" in key_list:
            # 模式1：同一person块内（姓名→身份证号→性别男），避免跨person匹配
            match = re.search(
                r"姓名\s*[^\s]+\s*(?:(?!姓名).)*?(\d{17}[\dXx])\s*(?:(?!姓名).)*?性\s*别\s*男",
                full_text,
                re.DOTALL,
            )
            if not match:
                # 模式2：身份证号在性别后
                match = re.search(
                    r"性\s*别\s*男(?:(?!姓名).)*?(\d{17}[\dXx])",
                    full_text,
                    re.DOTALL,
                )
            fields["男方身份证号"] = match.group(1).upper() if match else ""

        if "女方身份证号" in key_list:
            # 模式1：同一person块内
            match = re.search(
                r"姓名\s*[^\s]+\s*(?:(?!姓名).)*?(\d{17}[\dXx])\s*(?:(?!姓名).)*?性\s*别\s*女",
                full_text,
                re.DOTALL,
            )
            if not match:
                # 模式2：身份证号在性别后
                match = re.search(
                    r"性\s*别\s*女(?:(?!姓名).)*?(\d{17}[\dXx])",
                    full_text,
                    re.DOTALL,
                )
            fields["女方身份证号"] = match.group(1).upper() if match else ""

        return fields

    def extract_divorce_certificate(
        self, full_text: str, key_list: List[str]
    ) -> Dict[str, str]:
        """
        从离婚证文本中提取字段

        离婚证内容页包含两组人员信息：持证人和原配偶
        """
        fields = {}

        # === 基本信息 ===
        if "离婚证字号" in key_list:
            match = re.search(r"离婚证字号\s*([^\n]+)", full_text)
            value = ""
            if match:
                raw = match.group(1).strip()
                value = re.sub(r"\s+", "", raw)
            fields["离婚证字号"] = value

        if "登记日期" in key_list:
            match = re.search(r"登记日期\s*(\d{4}年\d{1,2}月\d{1,2}日)", full_text)
            fields["登记日期"] = match.group(1) if match else ""

        # === 持证人信息 ===
        if "持证人" in key_list:
            match = re.search(r"持\s*证\s*人\s*([^\s]+)", full_text)
            fields["持证人"] = match.group(1) if match else ""

        # 提取两组人员信息（持证人和原配偶）
        # 离婚证通常有两组：姓名、性别、民族、出生日期、身份证件号
        persons = self.extract_two_persons_info(full_text)

        # 持证人信息
        if "持证人性别" in key_list:
            fields["持证人性别"] = persons[0].get("性别", "")
        if "持证人民族" in key_list:
            fields["持证人民族"] = persons[0].get("民族", "")
        if "持证人出生日期" in key_list:
            fields["持证人出生日期"] = persons[0].get("出生日期", "")
        if "持证人身份证件号" in key_list:
            fields["持证人身份证件号"] = persons[0].get("身份证件号", "")

        # 原配偶信息
        if "原配偶姓名" in key_list:
            fields["原配偶姓名"] = persons[1].get("姓名", "")
        if "原配偶性别" in key_list:
            fields["原配偶性别"] = persons[1].get("性别", "")
        if "原配偶民族" in key_list:
            fields["原配偶民族"] = persons[1].get("民族", "")
        if "原配偶出生日期" in key_list:
            fields["原配偶出生日期"] = persons[1].get("出生日期", "")
        if "原配偶身份证件号" in key_list:
            fields["原配偶身份证件号"] = persons[1].get("身份证件号", "")

        return fields

    def extract_two_persons_info(self, full_text: str) -> List[Dict[str, str]]:
        """
        提取两组人员信息（用于离婚证等包含双方信息的证件）

        返回: [{姓名, 性别, 民族, 出生日期, 身份证件号}, {...}]
        """
        persons = []

        # 查找所有姓名+性别+民族的组合
        # 模式：姓名 XXX 性别 男/女 民族 汉 ...
        # 使用 [^性]* 代替 .*? 防止跨越"性"字边界
        person_blocks = re.findall(
            r"姓\s*名\s*([^\s]+)\s*[^性]*?性\s*别\s*(男|女)\s*[^民]*?民\s*族\s*([^\s]+)\s*(?:[^出]*?(?:出\s*生\s*(\d{4}年\d{1,2}月\d{1,2}日)))?\s*[^0-9]*?(\d{17}[\dXx])?",
            full_text,
            re.DOTALL,
        )

        for block in person_blocks:
            person = {
                "姓名": block[0] if block[0] else "",
                "性别": block[1] if block[1] else "",
                "民族": block[2] if block[2] else "",
                "出生日期": block[3] if block[3] else "",
                "身份证件号": block[4].upper() if block[4] else "",
            }
            persons.append(person)

        # 如果只找到一个人，尝试找第二个
        if len(persons) == 1:
            # 尝试查找第二个身份证号
            all_ids = re.findall(r"(\d{17}[\dXx])", full_text)
            if len(all_ids) > 1:
                # 第二个身份证号可能属于原配偶
                second_id = all_ids[1].upper()
                if second_id != persons[0].get("身份证件号"):
                    persons.append(
                        {
                            "姓名": "",
                            "性别": "",
                            "民族": "",
                            "出生日期": "",
                            "身份证件号": second_id,
                        }
                    )

        # 确保返回两个人员信息
        while len(persons) < 2:
            persons.append(
                {
                    "姓名": "",
                    "性别": "",
                    "民族": "",
                    "出生日期": "",
                    "身份证件号": "",
                }
            )

        return persons[:2]

