#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2A层：规则层
使用正则表达式从固定格式文档中提取字段

增强：户口本首页支持位置标注提取（通过 PaddleOCR 坐标）
"""

import logging
import re
from typing import Dict, List, Optional

from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
    IExtractionLayer,
)
from ocr_three_layer_hybrid.text_preprocessor import preprocess_text

logger = logging.getLogger(__name__)


class RuleExtractionLayer(IExtractionLayer):
    """规则提取层：身份证、结婚证、户口本、房产证、发票、合同/协议

    户口本首页增强：位置标注提取优先，正则补充。
    """

    def __init__(self, position_extractor=None):
        """
        Args:
            position_extractor: 位置标注提取器（可选，用于户口本首页）
        """
        self._position_extractor = position_extractor

    @property
    def supported_doc_types(self) -> List[DocumentType]:
        return [
            DocumentType.ID_CARD,
            DocumentType.ID_CARD_FRONT,
            DocumentType.ID_CARD_BACK,
            DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_COVER,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP,
            DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_COVER,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT,
            DocumentType.DIVORCE_CERTIFICATE_STAMP,
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_COVER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.INVOICE,
            DocumentType.PURCHASE_CONTRACT,
            DocumentType.STOCK_CONTRACT,
            DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
            DocumentType.FUND_SUPERVISION_CERTIFICATE,
            DocumentType.DIVORCE_AGREEMENT,
        ]

    def can_process(self, doc_info: DocumentInfo) -> bool:
        return doc_info.doc_type in self.supported_doc_types

    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        import time
        start_time = time.time()

        try:
            full_text = " ".join(doc_info.ocr_texts)

            # === OCR文本预处理 ===
            full_text = preprocess_text(full_text)

            # === 封面页/盖章页处理：直接返回空字段 ===
            if doc_info.doc_type in [
                DocumentType.DIVORCE_CERTIFICATE_COVER,
                DocumentType.DIVORCE_CERTIFICATE_STAMP,
                DocumentType.MARRIAGE_CERTIFICATE_COVER,
                DocumentType.MARRIAGE_CERTIFICATE_STAMP,
                DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,  # 资金监管协议签章页
            ]:
                # 封面页和盖章页不需要提取个人信息
                return ExtractionResult(
                    doc_type=doc_info.doc_type,
                    layer=ProcessingLayer.RULE,
                    fields={k: "" for k in key_list},
                    success=True,
                    time_cost=time.time() - start_time,
                    raw_text=full_text,
                    error_message="封面页/盖章页，跳过提取",
                )

            # === 内容页提取 ===
            if doc_info.doc_type == DocumentType.ID_CARD or doc_info.doc_type == DocumentType.ID_CARD_FRONT:
                fields = self._extract_id_card(full_text, key_list)
            elif doc_info.doc_type == DocumentType.ID_CARD_BACK:
                fields = self._extract_id_card_back(full_text, key_list)
            elif doc_info.doc_type in [
                DocumentType.MARRIAGE_CERTIFICATE,
                DocumentType.MARRIAGE_CERTIFICATE_CONTENT,
                DocumentType.MARRIAGE_CERTIFICATE_STAMP,
            ]:
                fields = self._extract_marriage_certificate(full_text, key_list)
            elif doc_info.doc_type in [
                DocumentType.DIVORCE_CERTIFICATE,
                DocumentType.DIVORCE_CERTIFICATE_CONTENT,
                DocumentType.DIVORCE_CERTIFICATE_STAMP,
            ]:
                fields = self._extract_divorce_certificate(full_text, key_list)
            elif doc_info.doc_type in [
                DocumentType.HOUSEHOLD_REGISTER,
                DocumentType.HOUSEHOLD_REGISTER_COVER,
                DocumentType.HOUSEHOLD_REGISTER_CONTENT,
            ]:
                fields = self._extract_household_register(full_text, key_list, doc_info.image_path)
            elif doc_info.doc_type in [
                DocumentType.PROPERTY_CERTIFICATE,
                DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            ]:
                # 内容页使用新的提取逻辑（支持表格布局）
                fields = self._extract_property_certificate_content(full_text, key_list)
            elif doc_info.doc_type in [
                DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
                DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            ]:
                # 首页和附图页不需要提取字段
                fields = {k: "" for k in key_list}
            elif doc_info.doc_type == DocumentType.INVOICE:
                fields = self._extract_invoice(full_text, key_list)
            elif doc_info.doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
                fields = self._extract_contract(full_text, key_list, doc_info.doc_type)
            elif doc_info.doc_type in [
                DocumentType.FUND_SUPERVISION,
                DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
                DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            ]:
                fields = self._extract_fund_supervision(full_text, key_list, doc_info.doc_type)
            elif doc_info.doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
                fields = self._extract_fund_supervision_certificate(full_text, key_list)
            elif doc_info.doc_type == DocumentType.DIVORCE_AGREEMENT:
                fields = self._extract_divorce_agreement(full_text, key_list)
            else:
                fields = {}

            # 只保留key_list中请求的字段
            filtered_fields = {k: fields.get(k, "") for k in key_list}

            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.RULE,
                fields=filtered_fields,
                success=True,
                time_cost=time.time() - start_time,
                raw_text=full_text,
            )
        except Exception as e:
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.RULE,
                fields={k: "" for k in key_list},
                success=False,
                time_cost=time.time() - start_time,
                error_message=str(e),
                raw_text=" ".join(doc_info.ocr_texts),
            )

    def _extract_id_card(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从身份证文本中提取字段（正面+背面）

        支持两种格式：
        1. 标准格式：有字段标签（姓名、性别、民族等）
        2. 无标签格式：OCR只输出值，没有字段标签
        """
        fields = {}

        # 检测是否为无标签格式（通过检查是否有"姓名"、"性别"等标签）
        has_labels = any(keyword in full_text for keyword in ['姓名', '性别', '民族', '出生', '住址'])

        if has_labels:
            # 标准格式：使用标签匹配
            self._extract_id_card_with_labels(full_text, key_list, fields)
        else:
            # 无标签格式：使用位置和模式匹配
            self._extract_id_card_without_labels(full_text, key_list, fields)

        return fields

    def _extract_id_card_with_labels(self, full_text: str, key_list: List[str], fields: Dict[str, str]):
        """标准格式：有字段标签的身份证提取"""
        # 正面字段
        if "姓名" in key_list:
            # 格式1（优先）：标签+同行值 "姓名XXX" 或 "姓名 XXX"（预处理后的常见格式）
            # 这种格式在身份证正面和预处理后都常见
            match = re.search(r'(?<!户主)姓\s*名\s*[:：]?\s*([一-鿿]{2,4})(?=\s|$)', full_text)
            # 格式2：值+标签 "XXX\n姓名"（OCR输出值在标签之前）
            if not match:
                match = re.search(r'([一-鿿]{2,4})\s*\n\s*姓名', full_text)
                # 验证：排除字段标签和常见误匹配
                if match:
                    candidate = match.group(1)
                    if candidate in (
                        "签发机关", "性别", "民族", "出生", "住址", "公民身份号码", "有效期限",
                        "性别男", "性别女", "民族汉"  # 预处理后常见的误匹配
                    ):
                        match = None  # 重置匹配，继续查找
            if match:
                candidate = match.group(1)
                # 再次验证：排除字段标签
                if candidate not in (
                    "签发机关", "性别", "民族", "出生", "住址", "公民身份号码", "有效期限",
                    "性别男", "性别女", "民族汉"
                ):
                    fields["姓名"] = candidate
                else:
                    fields["姓名"] = ""
            else:
                fields["姓名"] = ""

        if "性别" in key_list:
            match = re.search(r'性别\s*(男|女)', full_text)
            if not match:
                match = re.search(r'\b(男|女)\b', full_text)
            fields["性别"] = match.group(1) if match else ""

        if "民族" in key_list:
            match = re.search(r'民族\s*([^\s]+)', full_text)
            fields["民族"] = match.group(1) if match else ""

        if "出生" in key_list or "出生日期" in key_list:
            # OCR 输出可能有空格：出生 2004 年 8 月 3 日
            match = re.search(r'出生\s*(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)', full_text)
            value = match.group(1) if match else ""
            # 标准化：去除日期内空格 "2004 年 8 月 3 日" → "2004年8月3日"
            if value:
                value = re.sub(r'\s+', '', value)
            if "出生" in key_list:
                fields["出生"] = value
            if "出生日期" in key_list:
                fields["出生日期"] = value

        if "住址" in key_list:
            candidate = ""
            # 格式1（优先）：标签+同行值 "住址XXX"（可能跨多行）
            # 匹配"住址"后的地址内容，允许中间有其他字段（OCR可能按位置识别）
            match = re.search(r'住址\s*([一-鿿]+(?:省|市|区|县|镇|乡|村|路|号|室)[^\n]*)', full_text)
            if match:
                candidate = match.group(1).strip()
                # 尝试查找后续行中是否有地址的剩余部分
                # 查找当前行之后的行，看是否有地址特征词
                lines_after = full_text[match.end():].split('\n')
                for line in lines_after[:5]:  # 只检查后面5行
                    line = line.strip()
                    # 如果行包含地址特征词且不是其他字段标签
                    if (any(kw in line for kw in ['镇', '乡', '村', '路', '号', '室']) and
                        not any(label in line for label in ['出生', '性别', '民族', '公民身份', '签发'])):
                        candidate += line
                        break
            # 格式2：标签+换行+多行地址 "住址\n安徽省...\n乡..."
            if not candidate:
                match = re.search(r'住址\s*\n\s*(.+?)(?:\n\s*公民身份号码|\n\s*姓名|\n\s*$)', full_text, re.DOTALL)
                if match:
                    candidate = re.sub(r'\s*\n\s*', '', match.group(1)).strip()
            # 格式3：值+标签 "XXX\n住址"
            if not candidate:
                match = re.search(r'(.+?(?:省|市|区|县|镇|乡|村|路|号|室)[^\n]*)\s*\n\s*住址', full_text)
                if match:
                    candidate = match.group(1).strip()
            # 排除政府机关名称（如"蚌埠市公安局蚌山分局"）
            if candidate and not re.search(r'(公安局|分局|派出所|人民政府)', candidate):
                fields["住址"] = candidate
            else:
                fields["住址"] = ""

        if "公民身份号码" in key_list:
            match = re.search(r'(\d{17}[\dXx])', full_text)
            fields["公民身份号码"] = match.group(1).upper() if match else ""

        # 背面字段：签发机关
        if "签发机关" in key_list:
            # 格式1：标签+值
            match = re.search(r'签发机关\s*([一-龥()（）]+(?:公安局|分局))', full_text)
            if not match:
                match = re.search(r'签发机关\s*([一-龥]+(?:公安局|分局)[一-龥]*)', full_text)
            # 格式2：值+标签
            if not match:
                match = re.search(r'([一-龥]+(?:公安局|分局)[一-龥]*)\s*\n\s*签发机关', full_text)
            fields["签发机关"] = match.group(1).strip() if match else ""

        # 背面字段：有效期限
        if "有效期限" in key_list:
            # 格式1：标签+值
            match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})', full_text)
            if not match:
                match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-长期)', full_text)
            # 格式2：值+标签
            if not match:
                match = re.search(r'(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})\s*\n\s*有效期限', full_text)
            fields["有效期限"] = match.group(1) if match else ""

    def _extract_id_card_without_labels(self, full_text: str, key_list: List[str], fields: Dict[str, str]):
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
        lines = [line.strip() for line in full_text.split('\n') if line.strip()]

        # 提取18位身份证号（最可靠的标识）
        id_number = ""
        if "公民身份号码" in key_list:
            match = re.search(r'(\d{17}[\dXx])', full_text)
            if match:
                id_number = match.group(1).upper()
                fields["公民身份号码"] = id_number

        # 提取性别（男/女）
        gender = ""
        if "性别" in key_list:
            for line in lines:
                if line in ['男', '女']:
                    gender = line
                    fields["性别"] = gender
                    break

        # 提取姓名（2-4个中文字符，排除常见非姓名词）
        name = ""
        if "姓名" in key_list:
            # 查找2-4个中文字符的行
            for line in lines:
                if re.match(r'^[一-鿿]{2,4}$', line):
                    # 排除常见非姓名词（包括身份证背面标签）
                    if line not in [
                        '男', '女', '汉族', '民族', '出生', '住址', '公民身份',
                        '签发机关', '有效期限', '中华人民共和国', '居民身份证',
                    ]:
                        name = line
                        fields["姓名"] = name
                        break

        # 提取民族（处理"族汉"、"民族汉"等变体）
        ethnicity = ""
        if "民族" in key_list:
            # 匹配"族X"或"民族X"
            match = re.search(r'(?:民)?族\s*([一-鿿]{1,2})', full_text)
            if match:
                ethnicity = match.group(1)
                fields["民族"] = ethnicity

        # 提取出生日期（年份+月份）
        birth = ""
        if "出生" in key_list or "出生日期" in key_list:
            # 查找年份（4位数字）
            year_match = re.search(r'\b(19|20)\d{2}\b', full_text)
            year = year_match.group(0) if year_match else ""

            # 查找月份（1-12月）
            month_match = re.search(r'(\d{1,2})\s*月', full_text)
            month = month_match.group(1) if month_match else ""

            # 查找日期（1-31日）
            day_match = re.search(r'(\d{1,2})\s*日', full_text)
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
                if any(keyword in line for keyword in ['省', '市', '区', '县', '镇', '乡', '村', '路', '号']):
                    # 排除政府机关名称（如"蚌埠市公安局蚌山分局"）
                    if re.search(r'(公安局|分局|派出所|人民政府)', line):
                        continue
                    # 收集连续的地址行
                    address_lines.append(line)
                    # 检查下一行是否也是地址的一部分
                    if i + 1 < len(lines) and any(keyword in lines[i+1] for keyword in ['镇', '乡', '村', '路', '号', '室']):
                        # 也要排除下一行是政府机关的情况
                        if not re.search(r'(公安局|分局|派出所|人民政府)', lines[i+1]):
                            address_lines.append(lines[i+1])
                        break

            if address_lines:
                address = ''.join(address_lines)
                fields["住址"] = address

        # 背面字段：签发机关（即使正面标签缺失，背面标签也可能存在）
        if "签发机关" in key_list and "签发机关" not in fields:
            # 格式1：标签+值（签发机关 蚌埠市公安局蚌山分局）
            match = re.search(r'签发机关\s*([一-龥()（）]+(?:公安局|分局))', full_text)
            if not match:
                match = re.search(r'签发机关\s*([一-龥]+(?:公安局|分局)[一-龥]*)', full_text)
            # 格式2：值+标签（蚌埠市公安局蚌山分局\n签发机关）
            if not match:
                match = re.search(r'([一-龥]+(?:公安局|分局)[一-龥]*)\s*\n\s*签发机关', full_text)
            if match:
                fields["签发机关"] = match.group(1).strip()

        # 背面字段：有效期限
        if "有效期限" in key_list and "有效期限" not in fields:
            # 格式1：标签+值
            match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})', full_text)
            if not match:
                match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-长期)', full_text)
            # 格式2：值+标签
            if not match:
                match = re.search(r'(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})\s*\n\s*有效期限', full_text)
            if match:
                fields["有效期限"] = match.group(1)

    def _extract_marriage_certificate(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从结婚证文本中提取字段"""
        fields = {}

        if "持证人" in key_list:
            # OCR 可能输出 "持 证 人"（字间有空格）
            match = re.search(r'持\s*证\s*人\s*([^\s]+)', full_text)
            fields["持证人"] = match.group(1) if match else ""

        if "登记日期" in key_list:
            match = re.search(r'登记日期\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            fields["登记日期"] = match.group(1) if match else ""

        if "结婚证字号" in key_list:
            # OCR 可能输出 "结 婚 证 字 号"，值可能包含中文字符如 "皖固镇结字第010800316号"
            match = re.search(r'结\s*婚\s*证\s*字\s*号\s*([^\n]+)', full_text)
            value = ""
            if match:
                raw = match.group(1).strip()
                # 去除值内空格："J 340322 - 2025 - 000779" → "J340322-2025-000779"
                value = re.sub(r'\s+', '', raw)
            fields["结婚证字号"] = value

        if "男方姓名" in key_list:
            match = re.search(r'男方姓名\s*([^\s]+)', full_text)
            if not match:
                # 允许姓名和性别之间有其他字段（国籍、证件号等）
                match = re.search(
                    r'姓名\s*([^\s]+)(?:(?!姓名).)*?性别\s*男',
                    full_text, re.DOTALL,
                )
            fields["男方姓名"] = match.group(1) if match else ""

        if "女方姓名" in key_list:
            match = re.search(r'女方姓名\s*([^\s]+)', full_text)
            if not match:
                # 查找姓名+性别女的组合（允许中间有其他字段）
                persons = re.findall(
                    r'姓名\s*([^\s]+)(?:(?!姓名).)*?性别\s*(男|女)',
                    full_text, re.DOTALL,
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
                r'姓名\s*[^\s]+\s*(?:(?!姓名).)*?(\d{17}[\dXx])\s*(?:(?!姓名).)*?性\s*别\s*男',
                full_text, re.DOTALL,
            )
            if not match:
                # 模式2：身份证号在性别后
                match = re.search(
                    r'性\s*别\s*男(?:(?!姓名).)*?(\d{17}[\dXx])',
                    full_text, re.DOTALL,
                )
            fields["男方身份证号"] = match.group(1).upper() if match else ""

        if "女方身份证号" in key_list:
            # 模式1：同一person块内
            match = re.search(
                r'姓名\s*[^\s]+\s*(?:(?!姓名).)*?(\d{17}[\dXx])\s*(?:(?!姓名).)*?性\s*别\s*女',
                full_text, re.DOTALL,
            )
            if not match:
                # 模式2：身份证号在性别后
                match = re.search(
                    r'性\s*别\s*女(?:(?!姓名).)*?(\d{17}[\dXx])',
                    full_text, re.DOTALL,
                )
            fields["女方身份证号"] = match.group(1).upper() if match else ""

        return fields

    def _extract_divorce_certificate(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """
        从离婚证文本中提取字段

        离婚证内容页包含两组人员信息：持证人和原配偶
        """
        fields = {}

        # === 基本信息 ===
        if "离婚证字号" in key_list:
            match = re.search(r'离婚证字号\s*([^\n]+)', full_text)
            value = ""
            if match:
                raw = match.group(1).strip()
                value = re.sub(r'\s+', '', raw)
            fields["离婚证字号"] = value

        if "登记日期" in key_list:
            match = re.search(r'登记日期\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            fields["登记日期"] = match.group(1) if match else ""

        # === 持证人信息 ===
        if "持证人" in key_list:
            match = re.search(r'持\s*证\s*人\s*([^\s]+)', full_text)
            fields["持证人"] = match.group(1) if match else ""

        # 提取两组人员信息（持证人和原配偶）
        # 离婚证通常有两组：姓名、性别、民族、出生日期、身份证件号
        persons = self._extract_two_persons_info(full_text)

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

    def _extract_two_persons_info(self, full_text: str) -> List[Dict[str, str]]:
        """
        提取两组人员信息（用于离婚证等包含双方信息的证件）

        返回: [{姓名, 性别, 民族, 出生日期, 身份证件号}, {...}]
        """
        persons = []

        # 查找所有姓名+性别+民族的组合
        # 模式：姓名 XXX 性别 男/女 民族 汉 ...
        person_blocks = re.findall(
            r'姓\s*名\s*([^\s]+)\s*(?:.*?)?性\s*别\s*(男|女)\s*(?:.*?)?民\s*族\s*([^\s]+)\s*(?:.*?)?'
            r'(?:出\s*生\s*(\d{4}年\d{1,2}月\d{1,2}日))?\s*(?:.*?)?'
            r'(\d{17}[\dXx])?',
            full_text,
            re.DOTALL
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
            all_ids = re.findall(r'(\d{17}[\dXx])', full_text)
            if len(all_ids) > 1:
                # 第二个身份证号可能属于原配偶
                second_id = all_ids[1].upper()
                if second_id != persons[0].get("身份证件号"):
                    persons.append({
                        "姓名": "",
                        "性别": "",
                        "民族": "",
                        "出生日期": "",
                        "身份证件号": second_id,
                    })

        # 确保返回两个人员信息
        while len(persons) < 2:
            persons.append({
                "姓名": "",
                "性别": "",
                "民族": "",
                "出生日期": "",
                "身份证件号": "",
            })

        return persons[:2]

    def _extract_id_card_back(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从身份证背面的文本中提取字段（签发机关、有效期限）"""
        fields = {}

        if "签发机关" in key_list:
            match = re.search(r'签发机关\s*([^\n]+)', full_text)
            fields["签发机关"] = match.group(1).strip() if match else ""

        if "有效期限" in key_list:
            # 匹配格式：2020.01.01-2040.01.01 或 2020.01.01-2040.01.01
            match = re.search(r'(\d{4}\.\d{2}\.\d{2})\s*[-—]\s*(\d{4}\.\d{2}\.\d{2})', full_text)
            if match:
                fields["有效期限"] = f"{match.group(1)}-{match.group(2)}"
            else:
                # 尝试匹配：2020.01.01-2040.01.01（无空格）
                match = re.search(r'(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})', full_text)
                if match:
                    fields["有效期限"] = match.group(1)

        return fields

    def _extract_household_register(
        self, full_text: str, key_list: List[str], image_path: str = ""
    ) -> Dict[str, str]:
        """
        从户口本文本中提取字段（位置标注优先，正则兜底）

        首页字段（位置标注可处理）：户别、户主姓名、户号、住址
        个人页字段（正则处理）：姓名、与户主关系、性别、公民身份号码
        """
        fields = {}

        # 空白模板页检测："常住人口登记卡" 页面若无身份证号，则只有字段标签无数据
        if "常住人口登记卡" in full_text and not re.search(r"\d{17}[\dXx]", full_text):
            return fields

        # 第1层：位置标注提取（首页字段）
        pos_fields = {}
        if image_path and self._position_extractor:
            try:
                pos_fields = self._position_extractor.extract(image_path)
                logger.debug(f"位置标注结果: {pos_fields}")
            except Exception as e:
                logger.warning(f"位置标注提取失败，回退到正则: {e}")

        # 合并位置标注结果（优先）
        pos_field_names = ["户别", "户主姓名", "户号", "住址"]
        for key in pos_field_names:
            if key in key_list and pos_fields.get(key):
                value = pos_fields[key]
                # 验证：户主姓名不应该包含地址关键词
                if key == "户主姓名" and re.search(r'(省|市|区|县|镇|乡|村|路|号|室)', value):
                    logger.warning(f"位置标注户主姓名含地址关键词，跳过: {value}")
                    continue
                # 验证：住址不应该以"户号"开头
                if key == "住址" and value.startswith("户号"):
                    logger.warning(f"位置标注住址以户号开头，跳过: {value}")
                    continue
                fields[key] = value
                if key == "户主姓名" and "户主" in key_list:
                    fields["户主"] = value
                if key == "住址" and "地址" in key_list:
                    fields["地址"] = value

        # 第2层：正则提取（补充位置标注未覆盖的字段）
        # 只填充 fields 中尚未有值的字段

        if ("户主姓名" in key_list or "户主" in key_list) and "户主姓名" not in fields:
            # OCR 可能输出 "户 主 姓 名"（字间有空格）
            match = re.search(r'户\s*主\s*姓\s*名\s*([^\s]+)', full_text)
            if not match:
                match = re.search(r'户主\s+姓名\s*([^\s]+)', full_text)
            if not match:
                # Fallback：无"户主姓名"标签，从"姓名"字段取（当该页是户主页时）
                if re.search(r'户\s*主\s*或\s*与\s*户\s*主\s*关\s*系\s*户\s*主', full_text):
                    m = re.search(r'姓\s*名\s*([^\s]+)', full_text)
                    if m:
                        value = m.group(1)
                        if "户主姓名" in key_list:
                            fields["户主姓名"] = value
                        if "户主" in key_list:
                            fields["户主"] = value
                        # 跳过后续重复赋值
                        value = None
                    else:
                        value = ""
                else:
                    value = ""
                if value is not None:
                    # 过滤封面页噪声
                    if value and ("签章" in value or value in (
                        "姓名", "与户主关系", "性别", "住址", "出生日期", "公民身份号码",
                    )):
                        value = ""
                    if "户主姓名" in key_list:
                        fields["户主姓名"] = value
                    if "户主" in key_list:
                        fields["户主"] = value
            else:
                value = match.group(1) if match else ""
                # 过滤封面页噪声（承办人签章、字段标签等）
                if value and ("签章" in value or value in (
                    "姓名", "与户主关系", "性别", "住址", "出生日期", "公民身份号码",
                )):
                    value = ""
                if "户主姓名" in key_list:
                    fields["户主姓名"] = value
                if "户主" in key_list:
                    fields["户主"] = value

        if "户号" in key_list and "户号" not in fields:
            # OCR 可能输出 "户 号"（字间有空格）
            match = re.search(r'户\s*号\s*([A-Z0-9]+)', full_text, re.IGNORECASE)
            if not match:
                match = re.search(r'^([0-9]{6,12})\s*常住人口登记卡', full_text, re.MULTILINE)
            if not match:
                match = re.search(r'^([0-9]{6,12})\s*\n', full_text, re.MULTILINE)
            fields["户号"] = match.group(1) if match else ""

        if ("住址" in key_list or "地址" in key_list) and "住址" not in fields:
            # 避免匹配"住址变动登记"等噪声
            # 同时避免匹配 "其他住址" 等复合词（前面不能有中文字符）
            candidate = ""
            # 格式1：同行有值 "住址 XXX"
            match = re.search(r'(?<![一-鿿])住\s*址\s*(?!变动)([^\n]+)', full_text)
            if match:
                value = match.group(1).strip()
                # 如果同行是"户号"，则跳过，从下一行取地址
                if value.startswith("户号"):
                    # 格式2：住址同行是户号，地址在后续行
                    match = re.search(r'住\s*址\s*\n\s*户\s*号[^\n]*\n\s*(.+?)(?:\n\s*省级|\n\s*徽|\n\s*$)', full_text, re.DOTALL)
                    if match:
                        candidate = re.sub(r'\s*\n\s*', '', match.group(1)).strip()
                else:
                    candidate = value
            # 格式3：多行地址 "住址\n地址内容..."
            if not candidate:
                match = re.search(r'(?<![一-鿿])住\s*址\s*\n\s*(.+?)(?:\n\s*省级|\n\s*徽|\n\s*$)', full_text, re.DOTALL)
                if match:
                    candidate = re.sub(r'\s*\n\s*', '', match.group(1)).strip()
            # 格式4：地址标签
            if not candidate:
                match = re.search(r'(?<![一-鿿])地\s*址\s*(?!变动)([^\n]+)', full_text)
                if match:
                    candidate = match.group(1).strip()
            # 验证：住址应该包含地址关键词
            if candidate and re.search(r'(省|市|区|县|镇|乡|村|路|号|室)', candidate):
                if "住址" in key_list:
                    fields["住址"] = candidate
                if "地址" in key_list:
                    fields["地址"] = candidate
            else:
                if "住址" in key_list:
                    fields["住址"] = ""
                if "地址" in key_list:
                    fields["地址"] = ""

        if "姓名" in key_list:
            # 格式1：姓名 张玉德
            # 格式2：姓 名 张玉德（带空格）
            # 注意：用负向后行断言排除 "户主姓名"（封面页），避免户主值覆盖个人页姓名
            match = re.search(r'(?<!户主)姓\s*名\s*[:：]?\s*([^\s]+)', full_text)
            # 格式3：登记事项变更页格式 "姓\n张玉德"（标签分行）
            if not match:
                match = re.search(r'姓\s*\n\s*([一-鿿]{2,4})\s*\n', full_text)
            fields["姓名"] = match.group(1) if match else ""

        if "与户主关系" in key_list or "关系" in key_list:
            # OCR 可能输出 "户主或与户主关系"（字间有空格）
            # 捕获长度限制 ≤5 字符，避免匹配"注意事项"法律条文（如"户主或本户成员..."）
            match = re.search(r'户\s*主\s*或\s*与\s*户\s*主\s*关\s*系\s*(\S{1,5})', full_text)
            if not match:
                match = re.search(r'(?:与\s*户\s*主\s*关\s*系|关\s*系)\s*[:：]?\s*(\S{1,5})', full_text)
            value = match.group(1) if match else ""
            # 过滤明显的非关系词（如法律术语、字段名等）
            if value and (
                value in ("姓名", "性别", "曾用名", "出生地", "籍贯", "民族",
                          "宗教信仰", "公民身份号码", "出生日期", "文化程度",
                          "婚姻状况", "兵役状况", "服务处所", "职业",
                          "承办人签章", "登记日期", "户号", "住址")
                or "法律" in value or "效力" in value or "机关" in value
            ):
                value = ""
            if "与户主关系" in key_list:
                fields["与户主关系"] = value
            if "关系" in key_list:
                fields["关系"] = value

        if "性别" in key_list:
            match = re.search(r'性\s*别\s*[:：]?\s*(男|女)', full_text)
            # 格式2：登记事项变更页格式 "别\n性\n男"（标签分行或反转）
            if not match:
                match = re.search(r'[性别]\s*\n\s*[性别]?\s*\n\s*(男|女)\s*\n', full_text)
            if not match:
                # 宽松匹配：在"性"或"别"附近找到"男"或"女"
                match = re.search(r'(?:性|别)\s*\n?\s*(?:性|别)?\s*\n?\s*(男|女)', full_text)
            fields["性别"] = match.group(1) if match else ""

        if "公民身份号码" in key_list or "身份证号" in key_list:
            # OCR 可能输出 "公 民 身 份 号 码" 或 "公民身份证件编号"（字间有空格）
            match = re.search(
                r'(?:公\s*民\s*身\s*份\s*号\s*码|公\s*民\s*身\s*份\s*证\s*件\s*编\s*号|身\s*份\s*证\s*号)\s*[:：]?\s*(\d{17}[\dXx])',
                full_text, re.IGNORECASE,
            )
            # 格式2：登记事项变更页格式，标签分行或简化（如"份号"、"证件编"等后跟身份证号）
            if not match:
                match = re.search(r'(?:份号|证件编|编号)\s*\n?\s*(?:公|民)?\s*\n?\s*(?:民)?\s*\n?\s*(\d{17}[\dXx])', full_text)
            # 格式3：宽松匹配，直接找18位身份证号（作为兜底）
            if not match:
                match = re.search(r'(\d{17}[\dXx])', full_text)
            value = match.group(1).upper() if match else ""
            if "公民身份号码" in key_list:
                fields["公民身份号码"] = value
            if "身份证号" in key_list:
                fields["身份证号"] = value

        return fields

    def _extract_property_certificate(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从房产证文本中提取字段"""
        fields = {}

        if "不动产权证书号" in key_list or "证书号" in key_list:
            # 标准格式：皖（2017）蚌埠市不动产权第0025588号
            # OCR 可能输出: "皖（ 2025 ） 蚌埠市 不动产权第 0058326 号"（括号内/数字后有空格）
            match = re.search(
                r'[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号',
                full_text,
            )
            if match:
                value = re.sub(r'\s+', '', match.group(0))  # 标准化去空格
            else:
                value = ""
            # Fallback: "编号 № 34026135082" 格式
            if not value:
                match = re.search(r'编\s*号\s*[№#]+\s*([A-Z0-9]+)', full_text)
                if match:
                    value = match.group(1).strip()
            # Fallback: 直接 "不动产权证书号：..."
            if not value:
                match = re.search(r'不动产权证书号\s*[:：]?\s*([^\n]+)', full_text)
                if match:
                    value = re.sub(r'\s+', '', match.group(1).strip())
            if "不动产权证书号" in key_list:
                fields["不动产权证书号"] = value
            if "证书号" in key_list:
                fields["证书号"] = value

        if "权利人" in key_list:
            # 权利人必须出现在行首，避免匹配法律条文中的 "保护不动产权利人合法权益"
            # OCR 可能输出 "土地权利人" 而非 "权利人"
            match = re.search(r'^(?:土地)?权利人\s*[:：]?\s*([^\n]+)', full_text, re.MULTILINE)
            if not match:
                # fallback: 前面不是中文字符的情况（避免匹配"...保护不动产权利人..."）
                match = re.search(r'(?<=[^一-鿿])(?:土地)?权利人\s*[:：]?\s*([^\n]+)', full_text)
            fields["权利人"] = match.group(1).strip() if match else ""

        if "共有情况" in key_list:
            match = re.search(r'共有情况\s*[:：]?\s*([^\n]+)', full_text)
            fields["共有情况"] = match.group(1).strip() if match else ""

        if "不动产单元号" in key_list or "单元号" in key_list:
            match = re.search(r'不动产单元号\s*[:：]?\s*([A-Z0-9]+)', full_text, re.IGNORECASE)
            if not match:
                match = re.search(r'单元号\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "不动产单元号" in key_list:
                fields["不动产单元号"] = value
            if "单元号" in key_list:
                fields["单元号"] = value

        if "房屋地址" in key_list or "地址" in key_list or "坐落" in key_list:
            # OCR 可能输出 "坐 落"（字间有空格）
            # 必须匹配行首，避免匹配房产分户图表头中的 "坐落"（与 "结构 层数..." 同行）
            match = re.search(r'^(?:房屋坐落|坐\s*落|地址)\s*[:：]?\s*([^\n]+)', full_text, re.MULTILINE)
            if not match:
                match = re.search(r'^房屋地址\s*[:：]?\s*([^\n]+)', full_text, re.MULTILINE)
            value = match.group(1).strip() if match else ""
            if "房屋地址" in key_list:
                fields["房屋地址"] = value
            if "地址" in key_list:
                fields["地址"] = value
            if "坐落" in key_list:
                fields["坐落"] = value

        if "建筑面积" in key_list or "面积" in key_list:
            # OCR 可能输出:
            # - "房屋建筑面积 101.79 平方米"
            # - "共有宗地面积932.58平方米/房屋建筑面积101.79平方米"
            # - "建筑面积,m²\n... 88.32" （房产分户图表格格式）
            # - "面 积 ... 101.79平方米"
            match = re.search(r'房\s*屋\s*建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:㎡|平方米|m2)', full_text)
            if not match:
                match = re.search(r'建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:㎡|平方米|m2)', full_text)
            if not match:
                # 房产分户图表格数据：数字直接跟 m²（如 "88.32 m²"）
                match = re.search(r'([\d.]+)\s*m²', full_text)
            if not match:
                # 表格格式：表头 "建筑面积,m²" 后跟数值（可能换行）
                match = re.search(r'建\s*筑\s*面\s*积\s*,?\s*(?:㎡|m²|m2)?\s*\n?\s*([\d.]+)', full_text)
            if not match:
                # 通用 fallback：排除 "宗地面积"
                match = re.search(r'(?<!宗地)面\s*积\s*[:：]?\s*([\d.]+)', full_text)
            value = match.group(1) if match else ""
            if "建筑面积" in key_list:
                fields["建筑面积"] = value
            if "面积" in key_list:
                fields["面积"] = value

        if "用途" in key_list:
            # OCR 可能输出 "用 途"（字间有空格）
            match = re.search(r'用\s*途\s*[:：]?\s*([^\n]+)', full_text)
            fields["用途"] = match.group(1).strip() if match else ""

        return fields

    def _extract_property_certificate_content(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """
        从不动产权证书内容页提取10个字段（针对表格布局优化）

        字段：不动产编号、权利人、共有情况、坐落、不动产单元号、
              权利类型、权利性质、用途、面积、使用期限
        """
        fields = {}

        # 1. 不动产编号（对应"不动产第 {数字}号"）
        if "不动产编号" in key_list:
            match = re.search(r'不动产权第\s*(\d+)\s*号', full_text)
            if match:
                fields["不动产编号"] = match.group(1)

        # 2. 权利人 - 查找2-4个汉字的姓名（针对表格布局）
        if "权利人" in key_list:
            lines = full_text.split('\n')
            found_ren_label = False
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if '权利人' in line_stripped and len(line_stripped) < 10:
                    found_ren_label = True
                    continue

                if found_ren_label:
                    # 跳过空行和其他标签
                    if not line_stripped:
                        continue
                    # 如果是其他标签，继续
                    if any(tag in line_stripped for tag in ['共有情况', '不动产单元号', '权利类型', '权利性质', '使用期限', '坐落']):
                        continue
                    # 查找2-4个汉字的姓名
                    match = re.match(r'^([一-龥]{2,4})$', line_stripped)
                    if match:
                        fields["权利人"] = match.group(1)
                        break
                    # 如果这一行包含姓名（可能和其他文字混在一起）
                    match = re.search(r'([一-龥]{2,4})', line_stripped)
                    if match and len(line_stripped) < 10:
                        fields["权利人"] = match.group(1)
                        break

            # 备选策略：直接查找常见的姓名模式
            if "权利人" not in fields:
                all_names = re.findall(r'\n([一-龥]{2,4})\n', full_text)
                if all_names:
                    for name in all_names:
                        if name not in ['共有情况', '不动产单元号', '权利类型', '权利性质', '使用期限', '坐落', '和念老具']:
                            fields["权利人"] = name
                            break

        # 3. 共有情况
        if "共有情况" in key_list:
            if '共同共有' in full_text:
                fields["共有情况"] = "共同共有"
            elif '单独所有' in full_text:
                fields["共有情况"] = "单独所有"

        # 4. 坐落 - 查找包含"号楼"、"单元"的地址
        if "坐落" in key_list:
            # 优先匹配完整地址（如"绿地世纪城·柏仕公馆6号楼2单元8层2号"）
            match = re.search(r'([一-龥]+[·・]?[一-龥]+[0-9]*号楼[0-9]*单元[0-9]+层[0-9]+号)', full_text)
            if match:
                fields["坐落"] = match.group(1)
            else:
                # 备选：匹配包含"号楼"或"单元"的地址
                match = re.search(r'([一-龥]+(?:号楼|单元)[^\n]{0,30})', full_text)
                if match:
                    address = match.group(1).strip()
                    if '号楼' in address or '单元' in address:
                        fields["坐落"] = address

        # 5. 不动产单元号 - 查找包含空格分隔的编码
        if "不动产单元号" in key_list:
            match = re.search(r'(\d{6}\s+\d{6}\s+[A-Z]+\d+\s+[A-Z]+\d+)', full_text)
            if match:
                fields["不动产单元号"] = match.group(1)

        # 6. 权利类型
        if "权利类型" in key_list:
            if '国有建设用地使用权/房屋所有权' in full_text:
                fields["权利类型"] = "国有建设用地使用权/房屋所有权"
            elif '国有建设用地使用权' in full_text:
                fields["权利类型"] = "国有建设用地使用权"

        # 7. 权利性质
        if "权利性质" in key_list:
            if '出让/市场化商品房' in full_text:
                fields["权利性质"] = "出让/市场化商品房"
            elif '出让' in full_text:
                fields["权利性质"] = "出让"

        # 8. 用途
        if "用途" in key_list:
            if '城镇住宅用地/住宅' in full_text:
                fields["用途"] = "城镇住宅用地/住宅"
            elif '住宅' in full_text:
                fields["用途"] = "住宅"

        # 9. 面积（房屋建筑面积）
        if "面积" in key_list:
            match = re.search(r'房屋建筑面积\s*([\d.]+)', full_text)
            if match:
                fields["面积"] = match.group(1)
            else:
                # 备选：匹配 "建筑面积xxx"
                match = re.search(r'建筑面积[：:\s]*([\d.]+)', full_text)
                if match:
                    fields["面积"] = match.group(1)

        # 10. 使用期限 - 查找日期范围
        if "使用期限" in key_list:
            match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日[起止].*\d{4}年\d{1,2}月\d{1,2}日[起止止]?)', full_text)
            if match:
                fields["使用期限"] = match.group(1)

        return fields

    def _extract_invoice(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从发票文本中提取字段"""
        fields = {}

        if "发票代码" in key_list:
            match = re.search(r'发票代码\s*[:：]?\s*(\d{10,12})', full_text)
            fields["发票代码"] = match.group(1) if match else ""

        if "发票号码" in key_list:
            match = re.search(r'发票号码\s*[:：]?\s*(\d{8,20})', full_text)
            fields["发票号码"] = match.group(1) if match else ""

        if "开票日期" in key_list or "日期" in key_list:
            match = re.search(r'开票日期\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if not match:
                match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            value = match.group(1) if match else ""
            if "开票日期" in key_list:
                fields["开票日期"] = value
            if "日期" in key_list:
                fields["日期"] = value

        if "税额" in key_list:
            match = re.search(r'税额\s*[:：]?\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'增值税额\s*[:：]?\s*([\d,.]+)', full_text)
            fields["税额"] = match.group(1) if match else ""

        if "不含税金额" in key_list or "金额" in key_list:
            match = re.search(r'不含税金额\s*[:：]?\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'(?:金额|价款)\s*[:：]?\s*([\d,.]+)', full_text)
            value = match.group(1) if match else ""
            if "不含税金额" in key_list:
                fields["不含税金额"] = value
            if "金额" in key_list:
                fields["金额"] = value

        if "价税合计" in key_list or "合计" in key_list:
            # 匹配：价税合计（大写）⊗柒拾玖万伍仟陆佰肆拾圆整 （小写）¥795640.00
            # 或：合计 ¥729944.95
            # 注意：OCR可能输出全角（小写）或半角(小写)，且中间有换行，需要re.DOTALL
            match = re.search(r'价税合计.*?[（(]小写[）)]\s*[¥￥]?\s*([\d,.]+)', full_text, re.DOTALL)
            if not match:
                match = re.search(r'价税合计\s*[:：]?\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'合计\s*[¥￥]?\s*([\d,.]+)', full_text)
            value = match.group(1) if match else ""
            if "价税合计" in key_list:
                fields["价税合计"] = value
            if "合计" in key_list:
                fields["合计"] = value

        if "购买方名称" in key_list or "购买方" in key_list:
            # 格式1：购买方信息 → 名称：张玉德
            # 格式2：购买方名称：张玉德（负向后行断言排除"共同购买方"）
            # 格式3：名称：张铭辉（无"购买方"前缀，出现在发票头部）
            match = re.search(r'购买方信息\s*\n\s*名称\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'(?<!共同)购买方\s*名称\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'(?<!共同)购买方\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                # 格式3：无"购买方"前缀，匹配第一个非销售方/共同购买方的名称行
                match = re.search(
                    r'(?<!销售方)(?<!卖方信息)(?<!共同购买方)\n\s*名称\s*[:：]\s*([^\n]+)',
                    full_text,
                )
            value = match.group(1).strip() if match else ""
            # 清理可能的噪声
            if value in ('信息', '名称'):
                value = ""
            if "购买方名称" in key_list:
                fields["购买方名称"] = value
            if "购买方" in key_list:
                fields["购买方"] = value

        if "购买方纳税人识别号" in key_list:
            # 购买方信息 → 统一社会信用代码/纳税人识别号：34030320040803351X
            match = re.search(r'购买方信息\s*\n.*?纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})', full_text, re.DOTALL)
            if not match:
                # 负向后行断言：排除"共同购买方"
                match = re.search(r'(?<!共同)购买方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]{15,20})', full_text, re.DOTALL)
            if not match:
                # 格式3：名称行直接跟纳税人识别号行（无"购买方"前缀，不跨行匹配）
                match = re.search(
                    r'(?<!共同)名称[^\n]+\n\s*统一社会信用代码/纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})',
                    full_text,
                )
            fields["购买方纳税人识别号"] = match.group(1) if match else ""

        if "销售方名称" in key_list or "销售方" in key_list:
            # 格式1：销售方信息 → 名称：蚌埠宏翔置业有限公司
            # 格式2：销售方名称：蚌埠宏翔置业有限公司
            match = re.search(r'销售方信息\s*\n\s*名称\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'销售方\s*名称\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'销售方\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if value in ('信息', '名称'):
                value = ""
            if "销售方名称" in key_list:
                fields["销售方名称"] = value
            if "销售方" in key_list:
                fields["销售方"] = value

        if "销售方纳税人识别号" in key_list:
            match = re.search(r'销售方信息\s*\n.*?纳税人识别号\s*[:：]\s*([A-Z0-9]{15,20})', full_text, re.DOTALL)
            if not match:
                match = re.search(r'销售方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]{15,20})', full_text, re.DOTALL)
            fields["销售方纳税人识别号"] = match.group(1) if match else ""

        return fields

    def _extract_contract(self, full_text: str, key_list: List[str], doc_type: DocumentType) -> Dict[str, str]:
        """从买卖合同文本中提取字段（购房合同/存量房合同通用）"""
        fields = {}

        if "合同编号" in key_list:
            match = re.search(r'合同编号\s*[:：]?\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            fields["合同编号"] = match.group(1) if match else ""

        if "买受人" in key_list:
            # 格式1：乙方/买受人（签章）：张玉煌
            # 格式2：买受人（签章）：张玉煌
            # 避免匹配：买受人已详细阅读...
            # 注意：[ \t]* 只匹配空格/制表符，不匹配换行
            match = re.search(r'(?:乙方/)?买受人[（(]签章[）)][ \t]*[:：][ \t]*([^\n]+)', full_text)
            if not match:
                match = re.search(r'买受人[ \t]*[:：][ \t]*([^\s,，已详阅]+)', full_text)
            if not match:
                # 存量房合同格式：买方： 凡荣，尹笑男
                match = re.search(r'(?:乙方[/／]?)?买方\s*[:：]\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            # 清理噪声
            if value.startswith('已') or value in ('签章', '（签章）', '签字'):
                value = ""
            fields["买受人"] = value

        if "出卖人" in key_list:
            # 格式1：甲方/出卖人（签章）：蚌埠宏翔置业有限公司
            # 格式2：甲方/出卖人（签章）：（值在下一行或印章中）
            # 注意：[ \t]* 只匹配空格/制表符，不匹配换行
            match = re.search(r'(?:甲方/)?出卖人[（(]签章[）)][ \t]*[:：][ \t]*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            # 如果同一行没有值，尝试从下一行获取
            if not value:
                match = re.search(r'(?:甲方/)?出卖人[（(]签章[）)][ \t]*[:：]\n[ \t]*([^\n]+)', full_text)
                next_line = match.group(1).strip() if match else ""
                # 下一行不能是买受人信息
                if next_line and '买受人' not in next_line and '乙方' not in next_line:
                    value = next_line
            # 如果还是没有，尝试从印章中提取
            if not value:
                match = re.search(r'[（(]印章[：:][ \t]*([^\s)）]+)', full_text)
                stamp_value = match.group(1) if match else ""
                # 印章值不能是个人名（通常是公司名）
                if stamp_value and len(stamp_value) > 4:
                    value = stamp_value
            if not value:
                # 简单格式：出卖人：蚌埠宏翔置业有限公司（无签章标记）
                match = re.search(r'出卖人\s*[:：]\s*([^\n]+)', full_text)
                if match:
                    candidate = match.group(1).strip()
                    # 排除法律条文中的匹配
                    if candidate and len(candidate) < 30:
                        value = candidate
            if not value:
                # 存量房合同格式：卖方： 褚作宝
                match = re.search(r'(?:甲方[/／]?)?卖方\s*[:：]\s*([^\n]+)', full_text)
                value = match.group(1).strip() if match else ""
            # 清理噪声
            if value in ('签章', '（签章）', '签字', '：', ''):
                value = ""
            fields["出卖人"] = value

        if "总价款" in key_list or "价款" in key_list or "合同金额" in key_list:
            # 优先匹配带冒号的格式（避免匹配章节标题 "第三章 商品房价款"）
            match = re.search(r'(?:总价款|合同金额)\s*[:：]\s*([\d,.]+)\s*(?:元|万元)?', full_text)
            if not match:
                # 内联格式：总价款为 人民币 800000 元
                match = re.search(r'总价款\s*为\s*(?:人民币\s*)?(?:（[^）]*）\s*)?([\d,.]+)\s*(?:元|万元)', full_text)
            if not match:
                # 回退匹配（无冒号，但需要至少2位数字以避免匹配 "价款\n1." 噪声）
                match = re.search(r'(?:总价款|合同金额)\s*[:：]?\s*(\d{2,}[,.]?\d*)\s*(?:元|万元)?', full_text)
            value = match.group(1) if match else ""
            # 过滤噪声值
            if value in ("1", "1.", "2", "3", "4"):
                value = ""
            if "总价款" in key_list:
                fields["总价款"] = value
            if "价款" in key_list:
                fields["价款"] = value
            if "合同金额" in key_list:
                fields["合同金额"] = value

        if "签订日期" in key_list or "合同签订日期" in key_list:
            # 格式：签署日期：2024.2.21 或 签订日期：2024年2月21日（数字与年月日间可能有空格）
            match = re.search(r'(?:签署日期|签订日期|合同签订日期)\s*[:：]\s*(\d{4}\s*[.年\-]\s*\d{1,2}\s*[.月\-]\s*\d{1,2}\s*[日]?)', full_text)
            if not match:
                # 后备：找文本中的日期，排除扫描时间戳
                all_dates = list(re.finditer(r'(\d{4}\s*[.年\-]\s*\d{1,2}\s*[.月\-]\s*\d{1,2}\s*[日]?)', full_text))
                for dm in all_dates:
                    # 排除扫描时间戳（日期后紧跟 "HH:MM"）
                    after = full_text[dm.end():dm.end()+10]
                    if re.match(r'\s*\d{1,2}:\d{2}', after):
                        continue
                    match = dm
                    break
            value = match.group(1) if match else ""
            # 去除日期内的所有空格，统一格式
            value = value.replace(' ', '').replace('　', '')
            if "签订日期" in key_list:
                fields["签订日期"] = value
            if "合同签订日期" in key_list:
                fields["合同签订日期"] = value

        if "房屋地址" in key_list or "房屋坐落" in key_list or "地址" in key_list:
            match = re.search(r'(?:房屋坐落|坐落|房屋地址|地址)\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "房屋地址" in key_list:
                fields["房屋地址"] = value
            if "房屋坐落" in key_list:
                fields["房屋坐落"] = value
            if "地址" in key_list:
                fields["地址"] = value

        if "建筑面积" in key_list or "面积" in key_list:
            match = re.search(r'(?:建筑面积|面积)\s*[:：]?\s*([\d.]+)\s*(?:平方米|㎡|m2)?', full_text)
            value = match.group(1) if match else ""
            if "建筑面积" in key_list:
                fields["建筑面积"] = value
            if "面积" in key_list:
                fields["面积"] = value

        return fields

    def _extract_fund_supervision(
        self, full_text: str, key_list: List[str], doc_type: DocumentType = DocumentType.FUND_SUPERVISION
    ) -> Dict[str, str]:
        """从资金监管协议文本中提取字段

        Args:
            full_text: 完整OCR文本
            key_list: 需要提取的字段列表
            doc_type: 文档类型（首页/信息页/通用）
        """
        fields = {}

        # ===== 协议首页字段 =====
        # 编号
        if "编号" in key_list:
            match = re.search(r'编\s*号\s*[:：]?\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            fields["编号"] = match.group(1) if match else ""

        # 甲方/乙方/丙方
        for party in ["甲方", "乙方", "丙方"]:
            if party in key_list:
                # 模式1: "甲方（卖方）：褚作宝" / "乙方｛买方｝：尹笑男"
                match = re.search(rf'{party}[（(｛{{][^）)）}}｝]*[）)）}}｝]\s*[:：]\s*([一-龥]+)', full_text)
                if not match:
                    # 模式2: "甲方：xxx"
                    match = re.search(rf'{party}\s*[:：]\s*([一-龥]+)', full_text)
                fields[party] = match.group(1) if match else ""

        # 签署日期
        if "签署日期" in key_list or "签订日期" in key_list:
            match = re.search(r'(?:签署日期|签订日期)\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if not match:
                # 模式2: "于XXXX年X月X签订" (处理OCR缺少"日"字的情况)
                match = re.search(r'于\s*(\d{4}年\d{1,2}月\d{1,2})\s*签订', full_text)
                if match:
                    # 补充"日"字
                    value = match.group(1) + "日"
                else:
                    value = ""
            else:
                value = match.group(1)

            if "签署日期" in key_list:
                fields["签署日期"] = value
            if "签订日期" in key_list:
                fields["签订日期"] = value

        # 网上签约备案合同号
        if "网上签约备案合同号" in key_list:
            match = re.search(r'(?:网上签约备案合同号|备案合同号|合同号)\s*(?:为)?\s*[:：]?\s*([A-Z0-9\-()（）]+)', full_text, re.IGNORECASE)
            if not match:
                # 模式2: "Y(2024)12345"
                match = re.search(r'([A-Z]\s*[(（]\s*\d{4}\s*[)）]\s*\d+)', full_text, re.IGNORECASE)
            fields["网上签约备案合同号"] = match.group(1).strip() if match else ""

        # 房屋地址
        if "房屋地址" in key_list:
            match = re.search(r'(?:房屋地址|房屋坐落|坐落)\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                # 模式2: "位于xxx"
                match = re.search(r'位于\s*([^\n，,。]+(?:号|室|栋|楼|单元|层))', full_text)
            fields["房屋地址"] = match.group(1).strip() if match else ""

        # 建筑面积
        if "建筑面积" in key_list:
            match = re.search(r'建\s*筑\s*面\s*积\s*[:：]?\s*([\d.]+)\s*(?:平方米|㎡|m2)?', full_text)
            fields["建筑面积"] = match.group(1) if match else ""

        # 不动产权证号
        if "不动产权证号" in key_list:
            # 模式1: "皖（2024）蚌埠市不动产权第XXXXXXX号"
            match = re.search(
                r'[一-龥]*\s*[（(]\s*\d{4}\s*[）)]\s*[一-龥]+\s*市?\s*不动产权第\s*[A-Z0-9]+\s*号',
                full_text,
                re.DOTALL,  # 允许跨行匹配
            )
            if match:
                value = re.sub(r'\s+', '', match.group(0))
            else:
                # 模式2: "不动产权证号：xxx"
                match = re.search(r'不动产权证号\s*[:：]?\s*([^\n]+)', full_text)
                if not match:
                    # 模式3: "证号为：xxx" (简化版，处理跨行)
                    match = re.search(r'证号为\s*[:：]\s*([^\n]+)', full_text)
                value = match.group(1).strip() if match else ""
            fields["不动产权证号"] = value

        # 购房款（合并字段）
        if "购房款" in key_list:
            # 优先提取小写金额（更精确）
            match = re.search(r'购房款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'购房款[^\d\n]*?[¥￥]\s*([\d,.]+)', full_text)
            if not match:
                # 模式3: 处理顺序反转 "小写XXX元...购房款" (支持跨行)
                match = re.search(r'[（(]小写\s*([\d,.]+)\s*元[)）][\s\S]*?购房款', full_text)
            if match:
                fields["购房款"] = match.group(1)
            else:
                # 如果没有小写，尝试提取大写
                match = re.search(r'购房款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                if not match:
                    match = re.search(r'购房款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                fields["购房款"] = match.group(1) if match else ""

        # 购房款（大写/小写）
        for amount_type in ["购房款(大写)", "购房款(小写)"]:
            if amount_type in key_list:
                if "(大写)" in amount_type:
                    # 匹配中文大写金额
                    match = re.search(r'购房款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                    if not match:
                        # 模式2: "购房款（大写）：捌拾万元整"
                        match = re.search(r'购房款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                else:
                    # 匹配数字金额
                    match = re.search(r'购房款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)', full_text)
                    if not match:
                        match = re.search(r'购房款[^\d\n]*?[¥￥]\s*([\d,.]+)', full_text)
                    if not match:
                        # 模式3: 处理顺序反转 "小写XXX元...购房款" (支持跨行)
                        match = re.search(r'[（(]小写\s*([\d,.]+)\s*元[)）][\s\S]*?购房款', full_text)
                fields[amount_type] = match.group(1) if match else ""

        # 贷款（大写/小写）- 可选字段，空值表示无贷款
        for loan_type in ["贷款(大写)", "贷款(小写)"]:
            if loan_type in key_list:
                if "(大写)" in loan_type:
                    match = re.search(r'贷\s*款\s*[（(]*大写[)）]?\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                    if not match:
                        match = re.search(r'贷\s*款[^小\n]*?([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
                else:
                    match = re.search(r'贷\s*款\s*[（(]*小写[)）]?\s*[:：]?\s*[¥￥]?\s*([\d,.]+)', full_text)
                    if not match:
                        match = re.search(r'贷\s*款[^\d\n]*?[¥￥]\s*([\d,.]+)', full_text)
                    # 检查是否为null（表示无贷款）
                    if not match:
                        null_match = re.search(r'贷\s*款\s*[^\n]*?小写\s*null', full_text, re.IGNORECASE)
                        if null_match:
                            # 明确标记为null，表示无贷款
                            fields[loan_type] = ""
                            continue
                # 如果没有匹配到，返回空字符串（表示无贷款）
                fields[loan_type] = match.group(1) if match else ""

        # ===== 协议信息页字段 =====
        # 甲方姓名/身份证号/银行/账号
        for party in ["甲方", "乙方"]:
            for field_suffix in ["姓名", "身份证号", "银行", "账号"]:
                field_name = f"{party}{field_suffix}"
                if field_name in key_list:
                    # 模式1: "甲方姓名：xxx"
                    match = re.search(rf'{party}\s*{field_suffix}\s*[:：]?\s*([^\n]+)', full_text)
                    if not match and field_suffix == "身份证号":
                        # 模式2: 在甲方/乙方后找身份证号
                        match = re.search(rf'{party}[^\n]*?(\d{{17}}[\dXx])', full_text)
                    value = match.group(1).strip() if match else ""
                    if field_suffix == "身份证号" and value:
                        value = value.upper()
                    fields[field_name] = value

        # ===== 兼容旧字段 =====
        # 监管金额
        if "监管金额" in key_list or "监管价款" in key_list:
            match = re.search(r'(?:监管总额|监管金额|监管价款)\s*[^\n]*?[¥￥]\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'(?:监管金额|监管价款)\s*[:：]\s*([\d,.]+)\s*(?:元|万元)?', full_text)
            if not match:
                match = re.search(r'(?:监管总额|监管金额)\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+(?:[¥￥][\d,.]+)?)', full_text)
            value = match.group(1) if match else ""
            if "监管金额" in key_list:
                fields["监管金额"] = value
            if "监管价款" in key_list:
                fields["监管价款"] = value

        # 买方/卖方
        if "买方" in key_list or "卖方" in key_list:
            buyer_match = re.search(r'[｛{]买方[}｝]\s*[:：]\s*(\S+)', full_text)
            seller_match = re.search(r'[｛{]卖方[}｝]\s*[:：]\s*(\S+)', full_text)
            if not buyer_match:
                buyer_match = re.search(r'买[房方]人\s+([^\n]+?)(?:\s+卖|$)', full_text)
            if not buyer_match:
                buyer_match = re.search(r'买方\s*[:：]\s*(\S+)', full_text)
            if not seller_match:
                seller_match = re.search(r'卖[房方]人\s+([^\n]+?)(?:\s|$)', full_text)
            if not seller_match:
                seller_match = re.search(r'卖方\s*[:：]\s*(\S+)', full_text)
            buyer_val = buyer_match.group(1).strip() if buyer_match else ""
            seller_val = seller_match.group(1).strip() if seller_match else ""
            if buyer_val:
                buyer_val = re.split(r'卖[房方]人', buyer_val)[0].strip()
                names = buyer_val.split()
                buyer_val = "、".join(names) if names else buyer_val
            if "买方" in key_list:
                fields["买方"] = buyer_val
            if "卖方" in key_list:
                fields["卖方"] = seller_val

        # 监管机构
        if "监管机构" in key_list:
            match = re.search(r'[｛{]监管机构[}｝]\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'监管机构\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'([^\n]{4,30}公司)\s*\n\s*资金监管专用章', full_text)
            if not match:
                match = re.search(r'印章\s*[:：]\s*([^\s）]+公司)', full_text)
            value = match.group(1).strip() if match else ""
            value = re.sub(r'^[｝}]\s*[:：]?\s*', '', value)
            fields["监管机构"] = value

        # 合同编号
        if "合同编号" in key_list and "合同编号" not in fields:
            match = re.search(r'合同编号\s*[:：]?\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            fields["合同编号"] = match.group(1) if match else ""

        return fields

    def _extract_fund_supervision_certificate(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从资金监管凭证文本中提取字段

        资金监管凭证包含表格形式的信息：
        - 协议编号、日期
        - 买房人、买房人姓名、身份证号
        - 房屋坐落（地址）、建筑面积
        - 监管总额
        - 收款单位（红章，忽略）

        注意：凭证格式特殊，标签可能在值后面（如"张新\n买房人"）
        """
        fields = {}

        # 协议编号
        if "协议编号" in key_list:
            match = re.search(r'(?:协议编号|编\s*号)\s*[:：]?\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            if not match:
                # 模式2: "协议编号\n2026011900010627"（标签在前）
                match = re.search(r'协议编号\s*\n\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            if not match:
                # 模式3: "2026011600010591\n协议编号"（值在前）
                match = re.search(r'([A-Z0-9\-]+)\s*\n\s*协议编号', full_text, re.IGNORECASE)
            fields["协议编号"] = match.group(1) if match else ""

        # 日期
        if "日期" in key_list:
            # 模式1: "年月日"格式
            match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if not match:
                # 模式2: "YYYY-MM-DD"格式（凭证常用）
                match = re.search(r'(\d{4}-\d{2}-\d{2})', full_text)
            if not match:
                # 模式3: "YYYY/MM/DD"格式
                match = re.search(r'(\d{4}/\d{2}/\d{2})', full_text)
            fields["日期"] = match.group(1) if match else ""

        # 买房人
        if "买房人" in key_list:
            # 模式1: "买房人：xxx"（标准格式）
            match = re.search(r'买[房方]人\s*[:：]\s*([^\n]+)', full_text)
            if match:
                value = match.group(1).strip()
                # 清理可能的后续字段
                value = re.split(r'身份证|姓名', value)[0].strip()
                fields["买房人"] = value
            else:
                # 模式2: "xxx\n买房人"（凭证格式，值在标签前面）
                match = re.search(r'([一-龥]{2,4})\s*\n\s*买房人', full_text)
                if match:
                    fields["买房人"] = match.group(1).strip()
                else:
                    fields["买房人"] = ""

        # 买房人姓名
        if "买房人姓名" in key_list:
            # 模式1: "买房人姓名：xxx"
            match = re.search(r'(?:买房人\s*姓名|姓\s*名)\s*[:：]?\s*([一-龥]{2,4})', full_text)
            if not match:
                # 模式2: 复用"买房人"字段的值
                fields["买房人姓名"] = fields.get("买房人", "")
            else:
                fields["买房人姓名"] = match.group(1) if match else ""

        # 身份证号
        if "身份证号" in key_list:
            # 找到所有身份证号
            matches = re.findall(r'(\d{17}[\dXx])', full_text)
            if matches:
                # 凭证格式：第一个是卖房人，第二个是买房人
                # 如果有两个，取第二个（买房人）
                if len(matches) >= 2:
                    fields["身份证号"] = matches[1].upper()
                else:
                    fields["身份证号"] = matches[0].upper()
            else:
                fields["身份证号"] = ""

        # 房屋坐落（地址）
        if "房屋坐落" in key_list:
            # 模式1: "房屋坐落：xxx"（标准格式）
            match = re.search(r'(?:房屋坐落|坐落|房屋地址)\s*[:：]\s*([^\n]+)', full_text)
            if not match:
                # 模式2: "房屋坐落\nxxx"（标签在前）
                match = re.search(r'(?:房屋坐落|坐落)\s*\n\s*([^\n]+)', full_text)
                # 但要排除金额（如"贰拾壹万捌仟元整"）
                if match and re.match(r'[零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+', match.group(1).strip()):
                    match = None
            if not match:
                # 模式3: "xxx\n房屋坐落"（值在前）
                match = re.search(r'([^\n]*(?:号|室|栋|楼|单元|层|座|幢))\s*\n\s*(?:房屋坐落|坐落)', full_text)
            fields["房屋坐落"] = match.group(1).strip() if match else ""

        # 建筑面积
        if "建筑面积" in key_list:
            # 模式1: "建筑面积：xxx"（标准格式）
            match = re.search(r'建\s*筑\s*面\s*积\s*[:：]\s*([\d.]+)\s*(?:平方米|㎡|m2|m²)?', full_text)
            if not match:
                # 模式2: "建筑面积\nxxx m²"（标签在前）
                match = re.search(r'建筑面积\s*\n\s*([\d.]+)\s*(?:平方米|㎡|m2|m²)?', full_text)
            if not match:
                # 模式3: "xxx m²\n建筑面积"（值在前，紧接着）
                match = re.search(r'([\d.]+)\s*(?:平方米|㎡|m2|m²)\s*\n\s*建筑面积', full_text)
            if not match:
                # 模式4: 找到"建筑面积"，然后往前找最近的数字+单位
                # 分割文本为行
                lines = full_text.split('\n')
                for i, line in enumerate(lines):
                    if '建筑面积' in line:
                        # 往前搜索最多5行
                        for j in range(max(0, i-5), i):
                            area_match = re.search(r'([\d.]+)\s*(?:平方米|㎡|m2|m²)', lines[j])
                            if area_match:
                                fields["建筑面积"] = area_match.group(1)
                                match = area_match  # 标记为已找到
                                break
                        if match:
                            break
            fields["建筑面积"] = match.group(1) if match else fields.get("建筑面积", "")

        # 监管总额
        if "监管总额" in key_list:
            # 模式1: "监管总额：xxx"（标准格式）
            match = re.search(r'监管总额\s*[:：]\s*[¥￥]?\s*([\d,.]+)', full_text)
            if not match:
                # 模式2: "监管总额\n￥40000.00"（凭证格式，值在标签前面）
                match = re.search(r'[¥￥]\s*([\d,.]+)\s*\n\s*监管总额', full_text)
            if not match:
                # 模式3: 中文大写金额在监管总额前面
                match = re.search(r'([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)\s*\n\s*监管总额', full_text)
            if not match:
                # 模式4: "监管总额：xxx元"
                match = re.search(r'监管总额\s*[:：]?\s*([\d,.]+)\s*(?:元|万元)?', full_text)
            if not match:
                # 模式5: 中文大写金额
                match = re.search(r'监管总额\s*[:：]?\s*([零壹贰叁肆伍陆柒捌拾拾佰仟万亿元整]+)', full_text)
            fields["监管总额"] = match.group(1) if match else ""

        # 收款单位（忽略红章，只提取文字）
        if "收款单位" in key_list:
            # 模式1: "收款单位：xxx公司"
            match = re.search(r'收款单位\s*[:：]\s*([一-龥]+(?:公司|集团|中心))', full_text)
            if not match:
                # 模式2: "收款单位签章：xxx"
                match = re.search(r'收款单位签章\s*[:：]?\s*([一-龥]+(?:公司|集团|中心))', full_text)
            if not match:
                # 模式3: 在"资金监管专用章"前的公司名
                match = re.search(r'([一-龥]+(?:公司|集团|中心))\s*\n?\s*(?:资金监管)?专用章', full_text)
            if not match:
                # 模式4: 在"收款单位"附近的公司名
                match = re.search(r'收款单位[^一-龥]*([一-龥]+(?:公司|集团|中心))', full_text)
            fields["收款单位"] = match.group(1) if match else ""

        return fields

    def _extract_divorce_agreement(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从离婚协议文本中提取字段"""
        fields = {}

        # ===== 男方姓名 =====
        if "男方姓名" in key_list:
            match = re.search(r'男方姓名\s*[:：]\s*(\S+)', full_text)
            if not match:
                match = re.search(r'男\s*方\s*[:：]\s*(\S+)', full_text)
            fields["男方姓名"] = match.group(1).strip() if match else ""

        # ===== 女方姓名 =====
        if "女方姓名" in key_list:
            match = re.search(r'女方姓名\s*[:：]\s*(\S+)', full_text)
            if not match:
                match = re.search(r'女\s*方\s*[:：]\s*(\S+)', full_text)
            fields["女方姓名"] = match.group(1).strip() if match else ""

        # ===== 离婚日期 =====
        if "离婚日期" in key_list:
            # 模式1: "离婚日期：2018年7月30日"
            match = re.search(r'离婚日期\s*[:：]\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if match:
                fields["离婚日期"] = match.group(1)
            else:
                # 策略：取最后一个非结婚登记日期
                all_dates = re.findall(r'(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
                marriage_date = None
                m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)[^\n]{0,30}结婚登记', full_text)
                if m:
                    marriage_date = m.group(1)
                # 取最后一个不是结婚日期的日期（即签署日期）
                non_marriage_dates = [d for d in all_dates if d != marriage_date]
                if non_marriage_dates:
                    fields["离婚日期"] = non_marriage_dates[-1]

        # ===== 子女抚养 =====
        if "子女抚养" in key_list:
            # "一、子女抚养问题：婚后子女已成年。"
            match = re.search(r'子女抚养[^\n]*?[:：]\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'子女抚养\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            # 清理：截取到下一个编号条目之前
            value = re.split(r'[一二三四五六七八九十]+[、.]', value)[0].strip()
            fields["子女抚养"] = value

        # ===== 财产分割约定 =====
        if "财产分割约定" in key_list:
            # "二、财产分割及债务、债权处理问题：\n 1、婚后男女双方无共同财产分割\n 2、婚后男女双方无共同债务..."
            # 先找到该条款区域
            section_match = re.search(r'财产分割[^\n]*?[:：]([\s\S]+?)(?:三[、.]|其他协议|$)', full_text)
            if section_match:
                section_text = section_match.group(1)
                # 提取各子条款内容
                sub_items = re.findall(r'\d+[、.]\s*([^\n]+)', section_text)
                if sub_items:
                    # 合并所有子条款，去除尾部日期等噪声
                    parts = []
                    for item in sub_items:
                        # 去除尾部的数字日期格式 "2018.7.30"
                        item = re.sub(r'\s*\d{4}\.\d{1,2}\.\d{1,2}\s*', '', item)
                        # 去除尾部句号
                        item = item.rstrip('。')
                        if item.strip():
                            parts.append(item.strip())
                    # 去除后续子条款中与第一项重复的主语前缀
                    if len(parts) > 1:
                        first = parts[0]
                        # 尝试提取主语（取第一个谓语之前的部分）
                        # "婚后男女双方无共同财产分割" → 主语 "婚后男女双方"
                        prefix_match = re.match(r'^(.+?)(无|有|应|须|由|已|不)', first)
                        if prefix_match:
                            subject = prefix_match.group(1)
                            for i in range(1, len(parts)):
                                if parts[i].startswith(subject):
                                    parts[i] = parts[i][len(subject):]
                    value = "，".join(parts)
                else:
                    value = section_text.strip()
            else:
                # 简单模式: "财产分割：xxx"
                match = re.search(r'财产分割[^\n]*?[:：]?\s*([^\n]+)', full_text)
                value = match.group(1).strip() if match else ""
            fields["财产分割约定"] = value

        return fields
