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
    MARRIAGE_CERTIFICATE = "结婚证"
    DIVORCE_CERTIFICATE = "离婚证"
    HOUSEHOLD_REGISTER = "户口本"
    PROPERTY_CERTIFICATE = "不动产权证书"

    # 第二类：标准单证
    INVOICE = "发票"

    # 第三类：合同/协议
    PURCHASE_CONTRACT = "购房合同"
    STOCK_CONTRACT = "存量房合同"
    FUND_SUPERVISION = "资金监管协议"
    DIVORCE_AGREEMENT = "离婚协议"

    UNKNOWN = "未知"


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
    ocr_texts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


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
