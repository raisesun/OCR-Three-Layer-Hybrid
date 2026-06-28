#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2A层：规则层
使用正则表达式从固定格式文档中提取字段
"""

import re
from typing import Dict, List
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
    IExtractionLayer,
)


class RuleExtractionLayer(IExtractionLayer):
    """规则提取层：身份证、结婚证、户口本、房产证、发票、合同/协议"""

    @property
    def supported_doc_types(self) -> List[DocumentType]:
        return [
            DocumentType.ID_CARD,
            DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.INVOICE,
            DocumentType.PURCHASE_CONTRACT,
            DocumentType.STOCK_CONTRACT,
            DocumentType.FUND_SUPERVISION,
        ]

    def can_process(self, doc_info: DocumentInfo) -> bool:
        return doc_info.doc_type in self.supported_doc_types

    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        import time
        start_time = time.time()

        try:
            full_text = " ".join(doc_info.ocr_texts)

            if doc_info.doc_type == DocumentType.ID_CARD:
                fields = self._extract_id_card(full_text, key_list)
            elif doc_info.doc_type == DocumentType.MARRIAGE_CERTIFICATE:
                fields = self._extract_marriage_certificate(full_text, key_list)
            elif doc_info.doc_type == DocumentType.HOUSEHOLD_REGISTER:
                fields = self._extract_household_register(full_text, key_list)
            elif doc_info.doc_type == DocumentType.PROPERTY_CERTIFICATE:
                fields = self._extract_property_certificate(full_text, key_list)
            elif doc_info.doc_type == DocumentType.INVOICE:
                fields = self._extract_invoice(full_text, key_list)
            elif doc_info.doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
                fields = self._extract_contract(full_text, key_list, doc_info.doc_type)
            elif doc_info.doc_type == DocumentType.FUND_SUPERVISION:
                fields = self._extract_fund_supervision(full_text, key_list)
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
        """从身份证文本中提取字段（正面+背面）"""
        fields = {}

        # 正面字段
        if "姓名" in key_list:
            # 匹配 "姓名 XXX"，排除后面紧跟"性别"的情况（避免匹配到"姓名 王琼\n性别 男"这种跨行情况）
            match = re.search(r'姓名\s*([^\s\n]+?)(?:\s+性别|\s*$)', full_text)
            if not match:
                match = re.search(r'姓名\s*([^\s]+)', full_text)
            fields["姓名"] = match.group(1) if match else ""

        if "性别" in key_list:
            match = re.search(r'性别\s*(男|女)', full_text)
            if not match:
                match = re.search(r'\b(男|女)\b', full_text)
            fields["性别"] = match.group(1) if match else ""

        if "民族" in key_list:
            match = re.search(r'民族\s*([^\s]+)', full_text)
            fields["民族"] = match.group(1) if match else ""

        if "出生" in key_list or "出生日期" in key_list:
            match = re.search(r'出生\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            value = match.group(1) if match else ""
            if "出生" in key_list:
                fields["出生"] = value
            if "出生日期" in key_list:
                fields["出生日期"] = value

        if "住址" in key_list:
            match = re.search(r'住址\s*([^\s]+(?:省|市|区|县|镇|乡|村|路|号|室)[^\s]*)', full_text)
            fields["住址"] = match.group(1) if match else ""

        if "公民身份号码" in key_list:
            match = re.search(r'(\d{17}[\dXx])', full_text)
            fields["公民身份号码"] = match.group(1).upper() if match else ""

        # 背面字段：签发机关
        if "签发机关" in key_list:
            match = re.search(r'签发机关\s*([一-龥()（）]+(?:公安局|分局))', full_text)
            if not match:
                match = re.search(r'签发机关\s*([一-龥]+(?:公安局|分局)[一-龥]*)', full_text)
            fields["签发机关"] = match.group(1).strip() if match else ""

        # 背面字段：有效期限
        if "有效期限" in key_list:
            # 匹配格式：2024.06.21-2044.06.21 或 2016.10.11-长期
            match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-\d{4}\.\d{2}\.\d{2})', full_text)
            if not match:
                match = re.search(r'有效期限\s*(\d{4}\.\d{2}\.\d{2}-长期)', full_text)
            fields["有效期限"] = match.group(1) if match else ""

        return fields

    def _extract_marriage_certificate(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从结婚证文本中提取字段"""
        fields = {}

        if "持证人" in key_list:
            match = re.search(r'持证人\s*([^\s]+)', full_text)
            fields["持证人"] = match.group(1) if match else ""

        if "登记日期" in key_list:
            match = re.search(r'登记日期\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            fields["登记日期"] = match.group(1) if match else ""

        if "结婚证字号" in key_list:
            match = re.search(r'结婚证字号\s*([A-Z0-9\-]+)', full_text)
            fields["结婚证字号"] = match.group(1) if match else ""

        if "男方姓名" in key_list:
            match = re.search(r'男方姓名\s*([^\s]+)', full_text)
            if not match:
                match = re.search(r'姓名\s*([^\s]+)\s*性别\s*男', full_text)
            fields["男方姓名"] = match.group(1) if match else ""

        if "女方姓名" in key_list:
            match = re.search(r'女方姓名\s*([^\s]+)', full_text)
            if not match:
                # 查找第二个姓名+性别女的组合
                persons = re.findall(r'姓名\s*([^\s]+)\s*性别\s*(男|女)', full_text)
                for name, gender in persons:
                    if gender == "女":
                        fields["女方姓名"] = name
                        break
            else:
                fields["女方姓名"] = match.group(1)

        if "男方身份证号" in key_list:
            # 尝试找男方姓名后的身份证号
            match = re.search(r'性别\s*男.*?(\d{17}[\dXx])', full_text, re.DOTALL)
            fields["男方身份证号"] = match.group(1).upper() if match else ""

        if "女方身份证号" in key_list:
            # 尝试找女方姓名后的身份证号
            match = re.search(r'性别\s*女.*?(\d{17}[\dXx])', full_text, re.DOTALL)
            fields["女方身份证号"] = match.group(1).upper() if match else ""

        return fields

    def _extract_household_register(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从户口本文本中提取字段"""
        fields = {}

        if "户主姓名" in key_list or "户主" in key_list:
            match = re.search(r'户主姓名\s*([^\s]+)', full_text)
            if not match:
                match = re.search(r'户主\s*([^\s]+)', full_text)
            value = match.group(1) if match else ""
            if "户主姓名" in key_list:
                fields["户主姓名"] = value
            if "户主" in key_list:
                fields["户主"] = value

        if "户号" in key_list:
            match = re.search(r'户号\s*([A-Z0-9]+)', full_text, re.IGNORECASE)
            fields["户号"] = match.group(1) if match else ""

        if "住址" in key_list or "地址" in key_list:
            match = re.search(r'住址\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'地址\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "住址" in key_list:
                fields["住址"] = value
            if "地址" in key_list:
                fields["地址"] = value

        if "姓名" in key_list:
            # 匹配常住人口登记卡中的姓名
            match = re.search(r'姓名\s*[:：]?\s*([^\s]+)', full_text)
            fields["姓名"] = match.group(1) if match else ""

        if "与户主关系" in key_list or "关系" in key_list:
            match = re.search(r'(?:与户主关系|关系)\s*[:：]?\s*([^\s]+)', full_text)
            value = match.group(1) if match else ""
            if "与户主关系" in key_list:
                fields["与户主关系"] = value
            if "关系" in key_list:
                fields["关系"] = value

        if "性别" in key_list:
            match = re.search(r'性别\s*[:：]?\s*(男|女)', full_text)
            fields["性别"] = match.group(1) if match else ""

        if "公民身份号码" in key_list or "身份证号" in key_list:
            match = re.search(r'(?:公民身份号码|身份证号)\s*[:：]?\s*(\d{17}[\dXx])', full_text, re.IGNORECASE)
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
            # 匹配格式：皖（2017）蚌埠市不动产权第0025588号
            match = re.search(r'([（(]\d{4}[）)]\s*[一-龥]+市?\s*不动产权第\s*[A-Z0-9]+号)', full_text)
            if not match:
                match = re.search(r'不动产权证书号\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "不动产权证书号" in key_list:
                fields["不动产权证书号"] = value
            if "证书号" in key_list:
                fields["证书号"] = value

        if "权利人" in key_list:
            match = re.search(r'权利人\s*[:：]?\s*([^\n]+)', full_text)
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
            match = re.search(r'(?:房屋坐落|坐落|地址)\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'房屋地址\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "房屋地址" in key_list:
                fields["房屋地址"] = value
            if "地址" in key_list:
                fields["地址"] = value
            if "坐落" in key_list:
                fields["坐落"] = value

        if "建筑面积" in key_list or "面积" in key_list:
            match = re.search(r'建筑面积\s*[:：]?\s*([\d.]+)\s*(?:平方米|㎡|m2)', full_text)
            if not match:
                match = re.search(r'面积\s*[:：]?\s*([\d.]+)', full_text)
            value = match.group(1) if match else ""
            if "建筑面积" in key_list:
                fields["建筑面积"] = value
            if "面积" in key_list:
                fields["面积"] = value

        if "用途" in key_list:
            match = re.search(r'用途\s*[:：]?\s*([^\n]+)', full_text)
            fields["用途"] = match.group(1).strip() if match else ""

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
            match = re.search(r'价税合计\s*[:：]?\s*([\d,.]+)', full_text)
            if not match:
                match = re.search(r'合计\s*[:：]?\s*([\d,.]+)', full_text)
            value = match.group(1) if match else ""
            if "价税合计" in key_list:
                fields["价税合计"] = value
            if "合计" in key_list:
                fields["合计"] = value

        if "购买方名称" in key_list or "购买方" in key_list:
            match = re.search(r'购买方\s*名称\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'购买方\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "购买方名称" in key_list:
                fields["购买方名称"] = value
            if "购买方" in key_list:
                fields["购买方"] = value

        if "购买方纳税人识别号" in key_list:
            match = re.search(r'购买方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]+)', full_text, re.DOTALL)
            fields["购买方纳税人识别号"] = match.group(1) if match else ""

        if "销售方名称" in key_list or "销售方" in key_list:
            match = re.search(r'销售方\s*名称\s*[:：]?\s*([^\n]+)', full_text)
            if not match:
                match = re.search(r'销售方\s*[:：]?\s*([^\n]+)', full_text)
            value = match.group(1).strip() if match else ""
            if "销售方名称" in key_list:
                fields["销售方名称"] = value
            if "销售方" in key_list:
                fields["销售方"] = value

        if "销售方纳税人识别号" in key_list:
            match = re.search(r'销售方.*?纳税人识别号\s*[:：]?\s*([A-Z0-9]+)', full_text, re.DOTALL)
            fields["销售方纳税人识别号"] = match.group(1) if match else ""

        return fields

    def _extract_contract(self, full_text: str, key_list: List[str], doc_type: DocumentType) -> Dict[str, str]:
        """从买卖合同文本中提取字段（购房合同/存量房合同通用）"""
        fields = {}

        if "合同编号" in key_list:
            match = re.search(r'合同编号\s*[:：]?\s*([A-Z0-9\-]+)', full_text, re.IGNORECASE)
            fields["合同编号"] = match.group(1) if match else ""

        if "买受人" in key_list:
            match = re.search(r'买受人\s*[:：]?\s*([^\s,，]+)', full_text)
            fields["买受人"] = match.group(1) if match else ""

        if "出卖人" in key_list:
            match = re.search(r'出卖人\s*[:：]?\s*([^\s,，]+)', full_text)
            fields["出卖人"] = match.group(1) if match else ""

        if "总价款" in key_list or "价款" in key_list or "合同金额" in key_list:
            match = re.search(r'(?:总价款|价款|合同金额)\s*[:：]?\s*([\d,.]+)\s*(?:元|万元)?', full_text)
            value = match.group(1) if match else ""
            if "总价款" in key_list:
                fields["总价款"] = value
            if "价款" in key_list:
                fields["价款"] = value
            if "合同金额" in key_list:
                fields["合同金额"] = value

        if "合同签订日期" in key_list or "签订日期" in key_list:
            match = re.search(r'(?:合同签订日期|签订日期)\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            if not match:
                match = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
            value = match.group(1) if match else ""
            if "合同签订日期" in key_list:
                fields["合同签订日期"] = value
            if "签订日期" in key_list:
                fields["签订日期"] = value

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

    def _extract_fund_supervision(self, full_text: str, key_list: List[str]) -> Dict[str, str]:
        """从资金监管协议文本中提取字段"""
        fields = {}

        if "监管金额" in key_list or "监管价款" in key_list:
            match = re.search(r'(?:监管金额|监管价款)\s*[:：]?\s*([\d,.]+)\s*(?:元|万元)?', full_text)
            value = match.group(1) if match else ""
            if "监管金额" in key_list:
                fields["监管金额"] = value
            if "监管价款" in key_list:
                fields["监管价款"] = value

        if "买方" in key_list or "卖方" in key_list:
            buyer_match = re.search(r'买方\s*[:：]?\s*([^\s,，]+)', full_text)
            seller_match = re.search(r'卖方\s*[:：]?\s*([^\s,，]+)', full_text)
            if "买方" in key_list:
                fields["买方"] = buyer_match.group(1) if buyer_match else ""
            if "卖方" in key_list:
                fields["卖方"] = seller_match.group(1) if seller_match else ""

        if "监管机构" in key_list:
            match = re.search(r'监管机构\s*[:：]?\s*([^\n]+)', full_text)
            fields["监管机构"] = match.group(1).strip() if match else ""

        return fields
