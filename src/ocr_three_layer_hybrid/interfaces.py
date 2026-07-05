#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案E+核心接口定义
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class DocumentType(str, Enum):
    """支持的文档类型"""
    # 第一类：标准证件
    ID_CARD = "身份证"
    ID_CARD_FRONT = "身份证-正面"
    ID_CARD_BACK = "身份证-背面"

    MARRIAGE_CERTIFICATE = "结婚证"
    MARRIAGE_CERTIFICATE_COVER = "结婚证-封面"
    MARRIAGE_CERTIFICATE_CONTENT = "结婚证-内容页"
    MARRIAGE_CERTIFICATE_STAMP = "结婚证-盖章页"

    DIVORCE_CERTIFICATE = "离婚证"
    DIVORCE_CERTIFICATE_COVER = "离婚证-封面"
    DIVORCE_CERTIFICATE_CONTENT = "离婚证-内容页"
    DIVORCE_CERTIFICATE_STAMP = "离婚证-盖章页"

    HOUSEHOLD_REGISTER = "户口本"
    HOUSEHOLD_REGISTER_COVER = "户口本-首页"
    HOUSEHOLD_REGISTER_CONTENT = "户口本-个人页"

    PROPERTY_CERTIFICATE = "不动产权证书"
    PROPERTY_CERTIFICATE_FIRST_PAGE = "不动产权证书-首页"
    PROPERTY_CERTIFICATE_CONTENT = "不动产权证书-内容页"
    PROPERTY_CERTIFICATE_ATTACHMENT = "不动产权证书-附图页"

    # 第二类：标准单证
    INVOICE = "发票"

    # 第三类：合同/协议
    PURCHASE_CONTRACT = "购房合同"
    PURCHASE_CONTRACT_FIRST_PAGE = "购房合同-首页"
    PURCHASE_CONTRACT_CONTENT = "购房合同-内容页"
    PURCHASE_CONTRACT_STAMP = "购房合同-签署页"

    STOCK_CONTRACT = "存量房合同"
    STOCK_CONTRACT_FIRST_PAGE = "存量房合同-首页"
    STOCK_CONTRACT_CONTENT = "存量房合同-内容页"
    STOCK_CONTRACT_STAMP = "存量房合同-签署页"

    # 公证书
    NOTARY_CERTIFICATE = "公证书"

    # 委托书
    POWER_OF_ATTORNEY = "委托书"

    # 离婚协议书
    DIVORCE_AGREEMENT = "离婚协议书"
    FUND_SUPERVISION = "资金监管协议"
    FUND_SUPERVISION_AGREEMENT_FIRST_PAGE = "资金监管协议-首页"
    FUND_SUPERVISION_AGREEMENT_INFO_PAGE = "资金监管协议-信息页"
    FUND_SUPERVISION_AGREEMENT_STAMP = "资金监管协议-签章页"
    FUND_SUPERVISION_CERTIFICATE = "资金监管凭证"

    UNKNOWN = "未知"


class PageType(str, Enum):
    """页面类型"""
    COVER = "封面页"           # 证件封面（如：离婚证红色封面）
    CONTENT = "内容页"         # 核心内容页（如：离婚证内页，包含双方信息）
    STAMP = "盖章页"           # 盖章页（如：结婚证登记机关章）
    ATTACHMENT = "附件页"      # 附件页（如：房产证附图）
    BACK = "封底页"            # 封底页
    FIRST_PAGE = "首页"        # 户口本首页
    PERSONAL_PAGE = "个人页"   # 户口本个人页
    UNKNOWN = "未知页"         # 无法识别


class ProcessingLayer(str, Enum):
    """处理层类型"""
    RULE = "rule"
    VLM = "vlm"
    LLM = "llm"


@dataclass
class DocumentInfo:
    """文档信息"""
    image_path: str
    doc_type: DocumentType = DocumentType.UNKNOWN
    page_type: PageType = PageType.UNKNOWN
    ocr_texts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def should_extract(self) -> bool:
        """是否需要进行字段提取（封面页、封底页跳过）"""
        return self.page_type not in [PageType.COVER, PageType.BACK]

    def is_content_page(self) -> bool:
        """是否是内容页（核心数据页）"""
        return self.page_type in [
            PageType.CONTENT,
            PageType.FIRST_PAGE,
            PageType.PERSONAL_PAGE,
        ]


@dataclass
class ExtractionResult:
    """字段提取结果"""
    doc_type: DocumentType
    layer: ProcessingLayer
    fields: Dict[str, str] = field(default_factory=dict)
    success: bool = True
    time_cost: float = 0.0
    error_message: str = ""
    raw_text: str = ""
    vlm_fallback_triggered: bool = False  # 是否触发了VLM字段级兜底
    vlm_fallback_fields: List[str] = field(default_factory=list)  # 触发兜底的字段名

    def get(self, key: str, default: str = "") -> str:
        """安全获取字段值"""
        return self.fields.get(key, default)


class IDocumentClassifier(ABC):
    """文档分类器接口"""

    @abstractmethod
    def classify(self, image_path: str, ocr_texts: List[str]) -> DocumentInfo:
        """
        根据图片路径和OCR文本分类文档

        Args:
            image_path: 图片路径
            ocr_texts: OCR识别文本列表

        Returns:
            DocumentInfo对象
        """
        pass


class IExtractionLayer(ABC):
    """字段提取层接口"""

    @property
    @abstractmethod
    def supported_doc_types(self) -> List[DocumentType]:
        """支持的文档类型列表"""
        pass

    @abstractmethod
    def can_process(self, doc_info: DocumentInfo) -> bool:
        """判断是否能处理该文档"""
        pass

    @abstractmethod
    def extract(self, doc_info: DocumentInfo, key_list: List[str]) -> ExtractionResult:
        """
        提取字段

        Args:
            doc_info: 文档信息
            key_list: 需要提取的字段列表

        Returns:
            ExtractionResult对象
        """
        pass
