#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR三层混合架构 v2.0 — 编排管道
将文档分类器、规则层、VLM层组合成完整流程

v2.0 简化：
- 移除 LLM 层
- 移除 VLM 分类兜底
- 合同类文档路由到 VLM 层
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
)

logger = logging.getLogger(__name__)


class PlanEPlusPipeline:
    """OCR三层混合架构 v2.0 管道"""

    # 文档类型到默认字段的映射
    DEFAULT_KEY_LISTS: Dict[DocumentType, List[str]] = {
        DocumentType.ID_CARD: [
            "姓名",
            "性别",
            "民族",
            "出生",
            "住址",
            "公民身份号码",
            "签发机关",
            "有效期限",
        ],
        DocumentType.ID_CARD_FRONT: [
            "姓名",
            "性别",
            "民族",
            "出生",
            "住址",
            "公民身份号码",
        ],
        DocumentType.ID_CARD_BACK: [
            "签发机关",
            "有效期限",
        ],
        DocumentType.MARRIAGE_CERTIFICATE: [
            "持证人",
            "登记日期",
            "结婚证字号",
            "男方姓名",
            "女方姓名",
            "男方身份证号",
            "女方身份证号",
        ],
        DocumentType.MARRIAGE_CERTIFICATE_CONTENT: [
            "持证人",
            "登记日期",
            "结婚证字号",
            "男方姓名",
            "女方姓名",
            "男方身份证号",
            "女方身份证号",
        ],
        DocumentType.MARRIAGE_CERTIFICATE_STAMP: [
            # 盖章页通常不需要提取字段
        ],
        DocumentType.HOUSEHOLD_REGISTER: [
            "户主姓名",
            "户号",
            "住址",
            "姓名",
            "与户主关系",
            "性别",
            "公民身份号码",
        ],
        DocumentType.HOUSEHOLD_REGISTER_CONTENT: [
            "户主姓名",
            "户号",
            "住址",
            "姓名",
            "与户主关系",
            "性别",
            "公民身份号码",
        ],
        DocumentType.PROPERTY_CERTIFICATE: [
            "不动产编号",
            "权利人",
            "共有情况",
            "坐落",
            "不动产单元号",
            "权利类型",
            "权利性质",
            "用途",
            "面积",
            "使用期限",
        ],
        DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE: [
            # 首页字段（通常不需要提取，但可以记录）
            "登记机构",
            "编号",
            "登记日期",
        ],
        DocumentType.INVOICE: [
            "发票代码",
            "发票号码",
            "开票日期",
            "价税合计",
            "购买方名称",
            "购买方纳税人识别号",
            "销售方名称",
            "销售方纳税人识别号",
        ],
        DocumentType.PURCHASE_CONTRACT: [
            "合同编号",
            "买受人",
            "出卖人",
            "总价款",
            "签订日期",
            "房屋地址",
            "建筑面积",
        ],
        DocumentType.PURCHASE_CONTRACT_FIRST_PAGE: [
            "合同编号",
            "买受人",
            "出卖人",
            "房屋坐落",
        ],
        DocumentType.PURCHASE_CONTRACT_CONTENT: [
            "合同编号",
            "买受人",
            "出卖人",
            "总价款",
            "签订日期",
            "房屋地址",
            "建筑面积",
        ],
        DocumentType.PURCHASE_CONTRACT_STAMP: [
            # 签署页通常不需要提取字段
        ],
        DocumentType.STOCK_CONTRACT: [
            "合同编号",
            "买受人",
            "出卖人",
            "总价款",
            "签订日期",
            "房屋地址",
            "建筑面积",
        ],
        DocumentType.STOCK_CONTRACT_FIRST_PAGE: [
            "合同编号",
            "买受人",
            "出卖人",
            "房屋坐落",
        ],
        DocumentType.STOCK_CONTRACT_CONTENT: [
            "合同编号",
            "买受人",
            "出卖人",
            "总价款",
            "签订日期",
            "房屋地址",
            "建筑面积",
        ],
        DocumentType.STOCK_CONTRACT_STAMP: [
            # 签署页通常不需要提取字段
        ],
        DocumentType.FUND_SUPERVISION: [
            # 协议首页字段
            "编号",
            "甲方",
            "乙方",
            "丙方",
            "签署日期",
            "网上签约备案合同号",
            "房屋地址",
            "建筑面积",
            "不动产权证号",
            "购房款",
            "购房款(大写)",
            "购房款(小写)",
            "贷款(大写)",
            "贷款(小写)",  # 可选字段，空值表示无贷款
            # 协议信息页字段
            "甲方姓名",
            "甲方身份证号",
            "甲方银行",
            "甲方账号",
            "乙方姓名",
            "乙方身份证号",
            "乙方银行",
            "乙方账号",
            # 兼容旧字段
            "监管金额",
            "监管账户",
            "买方",
            "买方身份证号",
            "卖方",
            "卖方身份证号",
            "监管机构",
            "监管期限",
            "合同编号",
            "签订日期",
        ],
        DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: [
            "编号",
            "甲方",
            "乙方",
            "丙方",
            "签署日期",
            "网上签约备案合同号",
            "房屋地址",
            "建筑面积",
            "不动产权证号",
            "购房款",
            "购房款(大写)",
            "购房款(小写)",
            "贷款(大写)",
            "贷款(小写)",  # 可选字段，空值表示无贷款
        ],
        DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: [
            "甲方姓名",
            "甲方身份证号",
            "甲方银行",
            "甲方账号",
            "乙方姓名",
            "乙方身份证号",
            "乙方银行",
            "乙方账号",
        ],
        DocumentType.FUND_SUPERVISION_CERTIFICATE: [
            "协议编号",
            "日期",
            "买房人",
            "买房人姓名",
            "身份证号",
            "房屋坐落",
            "建筑面积",
            "监管总额",
        ],
        DocumentType.DIVORCE_CERTIFICATE: [
            # 离婚证基本信息
            "离婚证字号",
            "登记日期",
            # 持证人信息
            "持证人",
            "持证人性别",
            "持证人民族",
            "持证人出生日期",
            "持证人身份证件号",
            # 原配偶信息
            "原配偶姓名",
            "原配偶性别",
            "原配偶民族",
            "原配偶出生日期",
            "原配偶身份证件号",
            # 其他
            "备注",
        ],
        DocumentType.DIVORCE_AGREEMENT: [
            "男方姓名",
            "男方身份证号",
            "女方姓名",
            "女方身份证号",
            "离婚日期",
            "财产分割约定",
            "子女抚养",
            "债务处理",
            "其他约定",
        ],
        # 公证书（不需要提取字段，只需分类）
        DocumentType.NOTARY_CERTIFICATE: [
            "公证书编号",
            "公证日期",
            "公证事项",
        ],
        # 委托书（不需要提取字段，只需分类）
        DocumentType.POWER_OF_ATTORNEY: [
            "委托人",
            "受托人",
            "委托事项",
            "委托日期",
        ],
        # UNKNOWN文档的通用字段列表（覆盖所有可能的字段）
        DocumentType.UNKNOWN: [
            # 通用字段
            "文档类型",
            "编号",
            "日期",
            "金额",
            # 人员信息
            "姓名",
            "身份证号",
            "买方",
            "卖方",
            "权利人",
            # 房屋信息
            "房屋地址",
            "建筑面积",
            "用途",
            # 合同信息
            "合同编号",
            "买受人",
            "出卖人",
            "总价款",
            "签订日期",
            # 证件信息
            "证书号",
            "不动产单元号",
            "共有情况",
            # 发票信息
            "发票代码",
            "发票号码",
            "开票日期",
            "价税合计",
            "购买方名称",
            "销售方名称",
            # 其他
            "监管金额",
            "监管机构",
        ],
    }

    # 文档类型的详细字段配置（区分必须/可选字段）
    # 用于多页文档的字段合并和冲突检测
    DEFAULT_FIELD_CONFIGS: Dict[DocumentType, DocumentFieldConfig] = {
        # 购房合同 - 内容页
        DocumentType.PURCHASE_CONTRACT_CONTENT: DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
                FieldConfig(name="签订日期", priority=FieldPriority.REQUIRED),
                FieldConfig(name="建筑面积", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                # 这些字段主要在首页，内容页可能没有
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="买受人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="出卖人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="房屋地址", priority=FieldPriority.OPTIONAL),
            ]
        ),
        # 购房合同 - 首页
        DocumentType.PURCHASE_CONTRACT_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[],  # 首页没有必须字段（都是可选）
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="买受人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="出卖人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="房屋坐落", priority=FieldPriority.OPTIONAL),
            ]
        ),
        # 存量房合同 - 内容页
        DocumentType.STOCK_CONTRACT_CONTENT: DocumentFieldConfig(
            required_fields=[
                FieldConfig(name="总价款", priority=FieldPriority.REQUIRED),
                FieldConfig(name="签订日期", priority=FieldPriority.REQUIRED),
                FieldConfig(name="建筑面积", priority=FieldPriority.REQUIRED),
            ],
            optional_fields=[
                # 这些字段主要在首页，内容页可能没有
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="买受人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="出卖人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="房屋地址", priority=FieldPriority.OPTIONAL),
            ]
        ),
        # 存量房合同 - 首页
        DocumentType.STOCK_CONTRACT_FIRST_PAGE: DocumentFieldConfig(
            required_fields=[],  # 首页没有必须字段（都是可选）
            optional_fields=[
                FieldConfig(name="合同编号", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="买受人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="出卖人", priority=FieldPriority.OPTIONAL),
                FieldConfig(name="房屋坐落", priority=FieldPriority.OPTIONAL),
            ]
        ),
    }

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
            if (
                self.rule_layer
                and hasattr(self.rule_layer, "_position_extractor")
                and self.rule_layer._position_extractor
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

        # 第2.5层：VLM字段级兜底（校验失败时触发）
        if self.vlm_fallback_handler and result.success:
            fallback_start = time.time()
            result = self._apply_vlm_fallback(image_path, result, doc_info)
            fallback_time = time.time() - fallback_start

            if fallback_time > 0.1:  # 只有实际触发兜底时才记录
                logger.info(
                    "[VLM兜底] %s | 完成 | 耗时=%.2fs",
                    Path(image_path).name,
                    fallback_time,
                )

        result.time_cost = time.time() - start_time  # 包含分类时间
        return result

    def _apply_vlm_fallback(
        self, image_path: str, result: ExtractionResult, doc_info: DocumentInfo
    ) -> ExtractionResult:
        """
        对提取结果进行校验，失败字段触发VLM兜底

        仅对启用VLM兜底的文档类型生效（当前：户口本、结婚证、身份证）
        """
        # 只对特定文档类型启用VLM字段级兜底
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
                f"[VLM兜底] {doc_info.doc_type.value} | 失败字段: {failed_fields}"
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
            logger.warning(f"[VLM兜底] 异常: {e}")
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
