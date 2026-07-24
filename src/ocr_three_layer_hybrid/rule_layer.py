#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
第2A层：规则层
使用正则表达式从固定格式文档中提取字段

增强：户口本首页支持位置标注提取（通过 PaddleOCR 坐标）

重构：提取逻辑已拆分为独立的提取器模块
- PersonalIdExtractor: 身份证、结婚证、离婚证
- HouseholdPropertyExtractor: 户口本、房产证
- FinancialExtractor: 发票、合同、资金监管协议
- AgreementExtractor: 离婚协议书等
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
from ocr_three_layer_hybrid.extractors import (
    PersonalIdExtractor,
    HouseholdPropertyExtractor,
    FinancialExtractor,
    AgreementExtractor,
)

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

        # 初始化提取器实例
        self._personal_id_extractor = PersonalIdExtractor()
        self._household_property_extractor = HouseholdPropertyExtractor()
        self._financial_extractor = FinancialExtractor()
        self._agreement_extractor = AgreementExtractor()

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
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
            DocumentType.INVOICE,
            DocumentType.PURCHASE_CONTRACT,
            DocumentType.PURCHASE_CONTRACT_FIRST_PAGE,
            DocumentType.PURCHASE_CONTRACT_CONTENT,
            DocumentType.PURCHASE_CONTRACT_STAMP,
            DocumentType.STOCK_CONTRACT,
            DocumentType.STOCK_CONTRACT_FIRST_PAGE,
            DocumentType.STOCK_CONTRACT_CONTENT,
            DocumentType.STOCK_CONTRACT_STAMP,
            DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
            DocumentType.FUND_SUPERVISION_CERTIFICATE,
            DocumentType.DIVORCE_AGREEMENT,
            DocumentType.NOTARY_CERTIFICATE,
            DocumentType.POWER_OF_ATTORNEY,
        ]

    def can_process(self, doc_info: DocumentInfo) -> bool:
        return doc_info.doc_type in self.supported_doc_types

    # 跳过提取的文档类型（封面/盖章/附图页）
    _SKIP_TYPES = frozenset([
        DocumentType.DIVORCE_CERTIFICATE_COVER,
        DocumentType.DIVORCE_CERTIFICATE_STAMP,
        DocumentType.MARRIAGE_CERTIFICATE_COVER,
        DocumentType.MARRIAGE_CERTIFICATE_STAMP,
        DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP,
        DocumentType.PURCHASE_CONTRACT_STAMP,
        DocumentType.STOCK_CONTRACT_STAMP,
        DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT,
    ])

    def _is_skip_page(self, doc_type: DocumentType) -> bool:
        """是否跳过提取（封面/盖章/附图页）"""
        return doc_type in self._SKIP_TYPES

    def _dispatch_extract(self, full_text: str, key_list: List[str], doc_info: DocumentInfo) -> Dict[str, str]:
        """按文档类型分派提取逻辑（T6: 降低 extract 圈复杂度，早返回替代 if-elif）"""
        doc_type = doc_info.doc_type
        if doc_type in (DocumentType.ID_CARD, DocumentType.ID_CARD_FRONT, DocumentType.ID_CARD_BACK):
            return self._personal_id_extractor.extract_id_card(full_text, key_list)
        if doc_type in (DocumentType.MARRIAGE_CERTIFICATE, DocumentType.MARRIAGE_CERTIFICATE_CONTENT):
            return self._personal_id_extractor.extract_marriage_certificate(full_text, key_list)
        if doc_type in (DocumentType.DIVORCE_CERTIFICATE, DocumentType.DIVORCE_CERTIFICATE_CONTENT):
            return self._personal_id_extractor.extract_divorce_certificate(full_text, key_list)
        if doc_type in (DocumentType.HOUSEHOLD_REGISTER, DocumentType.HOUSEHOLD_REGISTER_COVER, DocumentType.HOUSEHOLD_REGISTER_CONTENT):
            return self._household_property_extractor.extract_household_register(full_text, key_list, doc_info.image_path)
        if doc_type in (DocumentType.PROPERTY_CERTIFICATE, DocumentType.PROPERTY_CERTIFICATE_CONTENT):
            return self._household_property_extractor.extract_property_certificate_content(full_text, key_list)
        if doc_type == DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE:
            return self._household_property_extractor.extract_property_certificate_first_page(full_text, key_list)
        if doc_type == DocumentType.INVOICE:
            return self._financial_extractor.extract_invoice(full_text, key_list)
        if doc_type in (DocumentType.PURCHASE_CONTRACT, DocumentType.STOCK_CONTRACT):
            return self._financial_extractor.extract_contract(full_text, key_list, doc_type)
        if doc_type in (DocumentType.FUND_SUPERVISION, DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE, DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE):
            return self._financial_extractor.extract_fund_supervision(full_text, key_list, doc_type)
        if doc_type == DocumentType.FUND_SUPERVISION_CERTIFICATE:
            return self._financial_extractor.extract_fund_supervision_certificate(full_text, key_list)
        if doc_type == DocumentType.DIVORCE_AGREEMENT:
            return self._agreement_extractor.extract_divorce_agreement(full_text, key_list)
        if doc_type in (DocumentType.PURCHASE_CONTRACT_FIRST_PAGE, DocumentType.PURCHASE_CONTRACT_CONTENT, DocumentType.STOCK_CONTRACT_FIRST_PAGE, DocumentType.STOCK_CONTRACT_CONTENT):
            return self._financial_extractor.extract_contract(full_text, key_list, doc_type)
        if doc_type in (DocumentType.PURCHASE_CONTRACT_STAMP, DocumentType.STOCK_CONTRACT_STAMP, DocumentType.NOTARY_CERTIFICATE, DocumentType.POWER_OF_ATTORNEY):
            return {k: "" for k in key_list}
        return {}

    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        """规则层字段提取（T6: 重构为预处理 + 跳过检查 + 分派，降低圈复杂度）"""
        import time

        start_time = time.time()

        try:
            full_text = " ".join(doc_info.ocr_texts)
            full_text = preprocess_text(full_text)

            # 跳过页（封面/盖章/附图）
            if self._is_skip_page(doc_info.doc_type):
                return ExtractionResult(
                    doc_type=doc_info.doc_type,
                    layer=ProcessingLayer.RULE,
                    fields={k: "" for k in key_list},
                    success=True,
                    time_cost=time.time() - start_time,
                    raw_text=full_text,
                    error_message="封面页/盖章页，跳过提取",
                )

            # 分派提取
            fields = self._dispatch_extract(full_text, key_list, doc_info)
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

