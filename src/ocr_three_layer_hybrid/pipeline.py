#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR 两层混合架构 v2.1 — 编排管道
将文档分类器、规则层、VLM层组合成完整流程

架构：
- Layer 1: 文档分类（关键词6级联）
- Layer 2A: 规则层（正则/位置标注）+ 字段级VLM重试
- Layer 2B: VLM层（未知文档直接提取）

v2.1 变更：
- 移除 LLM 层
- 移除 VLM 分类兜底
- 重命名 "第3层VLM兜底" → "Rule层字段级VLM重试"（非独立层）
"""

import logging
import time
from pathlib import Path
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
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.field_config import (
    FieldConfig,
    FieldPriority,
    DocumentFieldConfig,
    get_default_document_field_configs,
    get_default_key_lists,
)

logger = logging.getLogger(__name__)


class PlanEPlusPipeline:
    """OCR 两层混合架构 v2.1 管道"""

    # 文档类型的详细字段配置（区分必须/可选字段）
    # 用于 RULE 层失败判定和 VLM 兜底决策
    # 完整配置由 field_config.get_default_document_field_configs() 提供
    DEFAULT_FIELD_CONFIGS: Dict[DocumentType, DocumentFieldConfig] = get_default_document_field_configs()

    # 从字段配置动态生成默认的 key_lists
    # 内容由 field_config.get_default_key_lists() 提供，避免硬编码 ~250 行字典
    DEFAULT_KEY_LISTS: Dict[DocumentType, List[str]] = get_default_key_lists()

    # 文档类型到默认处理层的映射（v2.1：规则层优先，封面页跳过）
    DEFAULT_LAYER_ROUTING: Dict[DocumentType, ProcessingLayer] = {
        # 身份证
        DocumentType.ID_CARD: ProcessingLayer.RULE,
        DocumentType.ID_CARD_FRONT: ProcessingLayer.RULE,
        DocumentType.ID_CARD_BACK: ProcessingLayer.RULE,
        # 结婚证
        DocumentType.MARRIAGE_CERTIFICATE: ProcessingLayer.RULE,
        DocumentType.MARRIAGE_CERTIFICATE_COVER: ProcessingLayer.RULE,  # 封面页用规则层（返回空）
        DocumentType.MARRIAGE_CERTIFICATE_CONTENT: ProcessingLayer.RULE,  # 内容页用规则层
        DocumentType.MARRIAGE_CERTIFICATE_STAMP: ProcessingLayer.RULE,  # 盖章页用规则层
        # 离婚证
        DocumentType.DIVORCE_CERTIFICATE: ProcessingLayer.RULE,  # 规则层优先，VLM字段级兜底
        DocumentType.DIVORCE_CERTIFICATE_COVER: ProcessingLayer.RULE,  # 封面页用规则层（返回空）
        DocumentType.DIVORCE_CERTIFICATE_CONTENT: ProcessingLayer.RULE,  # 内容页用规则层
        DocumentType.DIVORCE_CERTIFICATE_STAMP: ProcessingLayer.RULE,  # 盖章页用规则层
        # 户口本
        DocumentType.HOUSEHOLD_REGISTER: ProcessingLayer.RULE,
        DocumentType.HOUSEHOLD_REGISTER_COVER: ProcessingLayer.RULE,  # 首页用规则层
        DocumentType.HOUSEHOLD_REGISTER_CONTENT: ProcessingLayer.RULE,  # 个人页用规则层
        # 不动产权证书
        DocumentType.PROPERTY_CERTIFICATE: ProcessingLayer.RULE,  # 改为规则层（已实现100%完成率）
        DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE: ProcessingLayer.RULE,  # 首页用规则层（返回空）
        DocumentType.PROPERTY_CERTIFICATE_CONTENT: ProcessingLayer.RULE,  # 内容页用规则层（100%完成率）
        DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT: ProcessingLayer.RULE,  # 附图页用规则层（返回空）
        # 发票
        DocumentType.INVOICE: ProcessingLayer.RULE,
        # 合同/协议（规则层优先，VLM字段级兜底）
        DocumentType.PURCHASE_CONTRACT: ProcessingLayer.RULE,  # 规则层优先
        DocumentType.PURCHASE_CONTRACT_FIRST_PAGE: ProcessingLayer.RULE,  # 首页用规则层
        DocumentType.PURCHASE_CONTRACT_CONTENT: ProcessingLayer.RULE,  # 内容页用规则层
        DocumentType.PURCHASE_CONTRACT_STAMP: ProcessingLayer.RULE,  # 签署页用规则层（返回空）
        DocumentType.STOCK_CONTRACT: ProcessingLayer.RULE,  # 规则层优先
        DocumentType.STOCK_CONTRACT_FIRST_PAGE: ProcessingLayer.RULE,  # 首页用规则层
        DocumentType.STOCK_CONTRACT_CONTENT: ProcessingLayer.RULE,  # 内容页用规则层
        DocumentType.STOCK_CONTRACT_STAMP: ProcessingLayer.RULE,  # 签署页用规则层（返回空）
        DocumentType.FUND_SUPERVISION: ProcessingLayer.RULE,
        DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: ProcessingLayer.RULE,  # 协议首页用规则层
        DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: ProcessingLayer.RULE,  # 协议信息页用规则层
        DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP: ProcessingLayer.RULE,  # 签章页用规则层（返回空）
        DocumentType.FUND_SUPERVISION_CERTIFICATE: ProcessingLayer.RULE,  # 凭证用规则层
        DocumentType.DIVORCE_AGREEMENT: ProcessingLayer.RULE,
        # 公证书、委托书（只需要分类，不需要提取）
        DocumentType.NOTARY_CERTIFICATE: ProcessingLayer.RULE,  # 返回空字段
        DocumentType.POWER_OF_ATTORNEY: ProcessingLayer.RULE,  # 返回空字段
        # 未知
        DocumentType.UNKNOWN: ProcessingLayer.VLM,
    }

    def __init__(
        self,
        classifier: Optional[IDocumentClassifier] = None,
        rule_layer: Optional[IExtractionLayer] = None,
        vlm_layer: Optional[IExtractionLayer] = None,
        key_lists: Optional[Dict[DocumentType, List[str]]] = None,
        layer_routing: Optional[Dict[DocumentType, ProcessingLayer]] = None,
        vlm_fallback_handler=None,  # VLM字段级兜底处理器
    ):
        """
        初始化管道

        Args:
            classifier: 文档分类器（如果不传，默认使用规则分类器）
            rule_layer: 规则层
            vlm_layer: VLM层
            key_lists: 各文档类型的默认字段列表
            layer_routing: 文档类型到处理层的映射
            vlm_fallback_handler: VLM字段级兜底处理器（校验失败时触发）
        """
        # v2.0: 只使用规则分类器
        self.classifier = classifier or KeywordDocumentClassifier()

        self.rule_layer = rule_layer or RuleExtractionLayer()
        self.vlm_layer = vlm_layer
        self.vlm_fallback_handler = vlm_fallback_handler

        self.key_lists = key_lists or self.DEFAULT_KEY_LISTS.copy()
        self.layer_routing = layer_routing or self.DEFAULT_LAYER_ROUTING.copy()

    def process(
        self,
        image_path: str,
        ocr_texts: List[str],
        key_list: Optional[List[str]] = None,
        force_layer: Optional[ProcessingLayer] = None,
        doc_info: Optional[DocumentInfo] = None,
    ) -> ExtractionResult:
        """
        处理文档并提取字段

        Args:
            image_path: 图片路径
            ocr_texts: OCR识别文本列表
            key_list: 指定提取的字段列表，不传则使用默认字段
            force_layer: 强制使用某一层处理
            doc_info: 预计算的分类结果（若提供则跳过内部重复分类）

        Returns:
            ExtractionResult对象
        """
        start_time = time.time()

        # 第1层：文档分类（如果未提供预计算结果）
        if doc_info is None:
            classify_start = time.time()
            doc_info = self.classifier.classify(image_path, ocr_texts)
            classify_time = time.time() - classify_start

            logger.info(
                "[分类] %s | 方法=规则分类器 | 路由=%s | 结果=%s | 耗时=%.2fs",
                Path(image_path).name,
                doc_info.metadata.get("route", "unknown"),
                doc_info.doc_type.value,
                classify_time,
            )

        # 附属页面检查：如果识别为附属页面，跳过提取
        if (
            doc_info.metadata.get("is_attachment")
            and doc_info.doc_type == DocumentType.UNKNOWN
        ):
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
            doc_info.doc_type, ProcessingLayer.VLM  # v2.0: 默认使用 VLM 层
        )

        # 回退逻辑：规则层提取依赖OCR文本，若无文本则回退到VLM提取
        full_text = " ".join(ocr_texts).strip()
        if target_layer == ProcessingLayer.RULE and not full_text:
            if self.vlm_layer is not None:
                target_layer = ProcessingLayer.VLM

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

        # 记录提取方法
        extract_start = time.time()
        layer_name = target_layer.value
        model_name = ""

        if target_layer == ProcessingLayer.RULE:
            model_name = "正则表达式"
            # rule_layer 始终在 __init__ 声明 _position_extractor（可能为 None），
            # 用 getattr 默认值替代 hasattr+属性访问，避免属性不存在时的 AttributeError
            if (
                self.rule_layer
                and getattr(self.rule_layer, "_position_extractor", None)
            ):
                if doc_info.doc_type == DocumentType.HOUSEHOLD_REGISTER:
                    model_name = "位置标注提取器(PaddleOCR)"
        elif target_layer == ProcessingLayer.VLM:
            if self.vlm_layer:
                model_name = getattr(self.vlm_layer, "model_name", "Qwen2.5-VL-7B")

        logger.info(
            "[提取] %s | 层=%s | 模型=%s | 文档类型=%s",
            Path(image_path).name,
            layer_name,
            model_name,
            doc_info.doc_type.value,
        )

        result = layer.extract(doc_info, key_list)
        extract_time = time.time() - extract_start

        logger.info(
            "[提取] %s | 完成 | 成功=%s | 字段数=%d | 耗时=%.2fs",
            Path(image_path).name,
            result.success,
            len([v for v in result.fields.values() if v]),
            extract_time,
        )

        # Rule层字段级VLM重试（校验失败时触发）
        if self.vlm_fallback_handler and result.success:
            fallback_start = time.time()
            result = self._apply_vlm_fallback(image_path, result, doc_info)
            fallback_time = time.time() - fallback_start

            if fallback_time > 0.1:  # 只有实际触发重试时才记录
                logger.info(
                    "[Rule层VLM重试] %s | 完成 | 耗时=%.2fs",
                    Path(image_path).name,
                    fallback_time,
                )

        # VLM 分类结果反馈：如果 doc_type 是 UNKNOWN 且 VLM 识别出了类型，替换 doc_type
        # 注意：字段保持原样（用 UNKNOWN 通用 key_list 提取的），只是类型反映真实类型
        # 这让最终结果能体现 VLM 的分类能力，便于监控/后续优化
        if (
            doc_info.doc_type == DocumentType.UNKNOWN
            and result.vlm_classified_type is not None
        ):
            logger.info(
                "[VLM分类替换] %s | UNKNOWN → %s",
                Path(image_path).name,
                result.vlm_classified_type.value,
            )
            result.doc_type = result.vlm_classified_type

        result.time_cost = time.time() - start_time  # 包含分类时间
        return result

    def _apply_vlm_fallback(
        self, image_path: str, result: ExtractionResult, doc_info: DocumentInfo
    ) -> ExtractionResult:
        """
        对提取结果进行校验，失败字段触发VLM聚焦重试

        仅对启用VLM重试的文档类型生效（当前：户口本、结婚证、身份证）
        这是 Rule 层(2A) 的子步骤，不是独立的处理层。
        """
        # 只对特定文档类型启用VLM字段级重试
        fallback_enabled_types = {
            DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.ID_CARD,
        }
        if doc_info.doc_type not in fallback_enabled_types:
            return result

        try:
            failed_fields = self.vlm_fallback_handler.get_failed_fields(result.fields)
            if not failed_fields:
                return result

            logger.info(
                f"[Rule层VLM重试] {doc_info.doc_type.value} | 失败字段: {failed_fields}"
            )
            vlm_fields = self.vlm_fallback_handler.fallback_extract(
                image_path, failed_fields, doc_info.doc_type
            )

            # 合并VLM结果（只覆盖失败字段）
            for field_name in failed_fields:
                if vlm_fields.get(field_name):
                    result.fields[field_name] = vlm_fields[field_name]

            # 标记已触发VLM字段级兜底
            result.vlm_fallback_triggered = True
            result.vlm_fallback_fields = list(failed_fields)

            return result
        except Exception as e:
            logger.warning("[Rule层VLM重试] 异常: %s", e)
            return result

    def _get_layer(self, layer: ProcessingLayer) -> Optional[IExtractionLayer]:
        """根据层类型获取对应的处理器"""
        if layer == ProcessingLayer.RULE:
            return self.rule_layer
        elif layer == ProcessingLayer.VLM:
            return self.vlm_layer
        # v2.0: 移除 LLM 层
        return None

    def get_layer_for_doc_type(self, doc_type: DocumentType) -> ProcessingLayer:
        """获取文档类型对应的默认处理层"""
        return self.layer_routing.get(doc_type, ProcessingLayer.VLM)
