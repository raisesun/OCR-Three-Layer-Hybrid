#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案E+编排管道
将文档分类器、规则层、VLM层、LLM层组合成完整流程
"""

import time
from typing import Dict, List, Optional, Any
from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    DocumentInfo,
    ExtractionResult,
    ProcessingLayer,
    IDocumentClassifier,
    IExtractionLayer,
)
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.vlm_classifier import VLMDocumentClassifier, HybridDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer


class PlanEPlusPipeline:
    """方案E+三层混合架构管道"""

    # 文档类型到默认字段的映射
    DEFAULT_KEY_LISTS: Dict[DocumentType, List[str]] = {
        DocumentType.ID_CARD: [
            "姓名", "性别", "民族", "出生", "住址", "公民身份号码"
        ],
        DocumentType.MARRIAGE_CERTIFICATE: [
            "持证人", "登记日期", "结婚证字号", "男方姓名", "女方姓名"
        ],
        DocumentType.HOUSEHOLD_REGISTER: [
            "姓名", "户主", "与户主关系", "性别", "户籍地址", "公民身份号码"
        ],
        DocumentType.PROPERTY_CERTIFICATE: [
            "权利人", "共有情况", "房屋地址", "不动产单元号", "建筑面积"
        ],
        DocumentType.INVOICE: [
            "发票代码", "发票号码", "开票日期", "税额", "不含税金额", "价税合计",
            "购买方名称", "销售方名称"
        ],
        DocumentType.PURCHASE_CONTRACT: [
            "合同编号", "买受人", "出卖人", "总价款", "合同签订日期", "房屋地址", "建筑面积"
        ],
        DocumentType.STOCK_CONTRACT: [
            "合同编号", "买受人", "出卖人", "总价款", "合同签订日期", "房屋地址", "建筑面积"
        ],
        DocumentType.FUND_SUPERVISION: [
            "监管金额", "买方", "卖方", "监管机构"
        ],
        DocumentType.DIVORCE_CERTIFICATE: [
            "离婚证字号", "持证人", "登记日期"
        ],
        DocumentType.DIVORCE_AGREEMENT: [
            "男方姓名", "女方姓名", "离婚日期", "财产分割", "子女抚养"
        ],
    }

    # 文档类型到默认处理层的映射
    DEFAULT_LAYER_ROUTING: Dict[DocumentType, ProcessingLayer] = {
        DocumentType.ID_CARD: ProcessingLayer.RULE,
        DocumentType.MARRIAGE_CERTIFICATE: ProcessingLayer.RULE,
        DocumentType.HOUSEHOLD_REGISTER: ProcessingLayer.RULE,  # 已添加到规则层
        DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.RULE,  # 已添加到规则层
        DocumentType.INVOICE: ProcessingLayer.RULE,  # 新增：发票由规则层处理
        DocumentType.PURCHASE_CONTRACT: ProcessingLayer.RULE,  # 已添加到规则层
        DocumentType.STOCK_CONTRACT: ProcessingLayer.RULE,  # 已添加到规则层
        DocumentType.FUND_SUPERVISION: ProcessingLayer.RULE,  # 新增：资金监管协议由规则层处理
        DocumentType.DIVORCE_CERTIFICATE: ProcessingLayer.VLM,  # 离婚证由VLM层处理
        DocumentType.DIVORCE_AGREEMENT: ProcessingLayer.LLM,  # 离婚协议由LLM层处理
        DocumentType.UNKNOWN: ProcessingLayer.VLM,  # VLM兜底
    }

    def __init__(
        self,
        classifier: Optional[IDocumentClassifier] = None,
        rule_layer: Optional[IExtractionLayer] = None,
        vlm_layer: Optional[IExtractionLayer] = None,
        llm_layer: Optional[IExtractionLayer] = None,
        key_lists: Optional[Dict[DocumentType, List[str]]] = None,
        layer_routing: Optional[Dict[DocumentType, ProcessingLayer]] = None,
        enable_vlm_classification_fallback: bool = True,
    ):
        """
        初始化方案E+管道

        Args:
            classifier: 文档分类器（如果不传，默认使用混合分类器）
            rule_layer: 规则层
            vlm_layer: VLM层
            llm_layer: LLM层
            key_lists: 各文档类型的默认字段列表
            layer_routing: 文档类型到处理层的映射
            enable_vlm_classification_fallback: 是否启用VLM分类兜底（默认True）
        """
        # 如果没有指定分类器，创建混合分类器（规则优先，VLM兜底）
        if classifier is None:
            rule_clf = KeywordDocumentClassifier()
            if enable_vlm_classification_fallback:
                vlm_clf = VLMDocumentClassifier()
                self.classifier = HybridDocumentClassifier(rule_clf, vlm_clf)
            else:
                self.classifier = rule_clf
        else:
            self.classifier = classifier

        self.rule_layer = rule_layer or RuleExtractionLayer()
        self.vlm_layer = vlm_layer
        self.llm_layer = llm_layer

        self.key_lists = key_lists or self.DEFAULT_KEY_LISTS.copy()
        self.layer_routing = layer_routing or self.DEFAULT_LAYER_ROUTING.copy()

    def process(
        self,
        image_path: str,
        ocr_texts: List[str],
        key_list: Optional[List[str]] = None,
        force_layer: Optional[ProcessingLayer] = None,
    ) -> ExtractionResult:
        """
        处理文档并提取字段

        Args:
            image_path: 图片路径
            ocr_texts: OCR识别文本列表
            key_list: 指定提取的字段列表，不传则使用默认字段
            force_layer: 强制使用某一层处理

        Returns:
            ExtractionResult对象
        """
        start_time = time.time()

        # 第1层：文档分类
        doc_info = self.classifier.classify(image_path, ocr_texts)

        # 附属页面检查：如果VLM识别为附属页面，跳过提取
        if doc_info.metadata.get("is_attachment"):
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=ProcessingLayer.VLM,
                fields={},
                success=True,
                time_cost=time.time() - start_time,
                error_message="附属页面，跳过提取",
            )

        # 获取字段列表
        if key_list is None:
            key_list = self.key_lists.get(doc_info.doc_type, [])

        # 选择处理层
        target_layer = force_layer or self.layer_routing.get(
            doc_info.doc_type, ProcessingLayer.LLM
        )

        # 第2层：字段提取
        layer = self._get_layer(target_layer)

        if layer is None or not layer.can_process(doc_info):
            return ExtractionResult(
                doc_type=doc_info.doc_type,
                layer=target_layer,
                fields={k: "" for k in key_list},
                success=False,
                time_cost=time.time() - start_time,
                error_message=f"没有可用的{target_layer.value}层处理器",
            )

        result = layer.extract(doc_info, key_list)
        result.time_cost = time.time() - start_time  # 包含分类时间
        return result

    def _get_layer(self, layer: ProcessingLayer) -> Optional[IExtractionLayer]:
        """根据层类型获取对应的处理器"""
        if layer == ProcessingLayer.RULE:
            return self.rule_layer
        elif layer == ProcessingLayer.VLM:
            return self.vlm_layer
        elif layer == ProcessingLayer.LLM:
            return self.llm_layer
        return None

    def get_layer_for_doc_type(self, doc_type: DocumentType) -> ProcessingLayer:
        """获取文档类型对应的默认处理层"""
        return self.layer_routing.get(doc_type, ProcessingLayer.LLM)
