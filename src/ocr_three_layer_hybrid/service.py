#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR 两层混合架构 v2.1 — 正式服务层

提供对外统一的服务接口，封装 Pipeline 的分类+提取完整流程。
架构：分类器 + 规则层(2A) + VLM层(2B)，规则层失败时触发字段级VLM重试。

Usage:
    from ocr_three_layer_hybrid.service import OCRService

    service = OCRService()                      # 默认配置
    service = OCRService.from_env()             # 从环境变量加载
    result = service.process_single(path, text) # 单图处理
    results = service.process_batch(images)     # 批量处理
    dir_result = service.process_directory(dir) # 目录批量处理
"""

import time
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ocr_three_layer_hybrid.config import OCRConfig, SUPPORTED_FILE_EXTENSIONS
from ocr_three_layer_hybrid.external_services import VLMClient
from ocr_three_layer_hybrid.interfaces import (
    DocumentType, DocumentInfo, ExtractionResult, FieldDetail, FieldStatus, ProcessingLayer,
)
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline
from ocr_three_layer_hybrid.field_config import DocumentFieldConfig, get_default_document_field_configs
from ocr_three_layer_hybrid.ui_metadata import ROUTE_NAMES, PIPELINE_STAGES, LAYER_COLORS


# ========== 日志配置 ==========

logger = logging.getLogger("ocr_three_layer_hybrid")


def setup_logging(level: str = "INFO", log_file: Optional[str] = None):
    """配置服务日志格式和级别

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径（可选，不指定则只输出到控制台）
    """
    log_format = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = []
    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    handlers.append(console_handler)

    # 文件 handler（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        handlers.append(file_handler)

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in handlers:
        logger.addHandler(h)

    logger.info("日志系统初始化完成 (level=%s, file=%s)", level, log_file or "无")


class OCRService:
    """OCR 两层混合架构 v2.1 — 统一服务接口

    整合分类器、Pipeline、VLM客户端，提供完整的文档处理服务。
    分类器只创建一次，同时注入到Pipeline中避免重复分类。

    架构（v2.1 简化）：
    - Layer 1: 关键词分类器
    - Layer 2A: 规则层（正则/位置标注）+ 字段级VLM重试
    - Layer 2B: VLM层（未知文档直接提取）
    """

    def __init__(self, config: Optional[OCRConfig] = None):
        """
        初始化服务

        Args:
            config: 服务配置，不传则使用默认配置
        """
        self.config = config or OCRConfig()
        self._paddleocr_lock = threading.Lock()  # PaddleOCR 初始化锁
        self._paddleocr_wrapper = None  # 延迟初始化，首次调用时创建

        # VLM客户端：根据vlm_ocr_engine配置选择模型
        vlm_ocr_config = self.config.get_vlm_config(self.config.vlm_ocr_engine)
        self._vlm_client = VLMClient(vlm_ocr_config)

        # 分类器：只使用规则分类器
        self._classifier = KeywordDocumentClassifier()

        # 位置标注提取器（延迟初始化PaddleOCR）
        self._position_extractor = None
        if self.config.enable_position_extraction:
            try:
                from ocr_three_layer_hybrid.position_extractor import (
                    HouseholdPositionExtractor,
                )

                self._position_extractor = HouseholdPositionExtractor()
                logger.info("位置标注提取器已启用")
            except ImportError as e:
                logger.warning("位置标注提取器未启用（导入失败）: %s", e)

        # Rule层字段级VLM重试处理器：根据vlm_fallback_engine配置选择模型
        self._vlm_fallback_handler = None
        if self.config.enable_vlm_field_fallback:
            try:
                from ocr_three_layer_hybrid.vlm_fallback import VLMFieldRetryHandler

                # 创建独立的VLM客户端用于字段级重试
                vlm_fallback_config = self.config.get_vlm_config(
                    self.config.vlm_fallback_engine
                )
                vlm_fallback_client = VLMClient(vlm_fallback_config)
                self._vlm_fallback_handler = VLMFieldRetryHandler(
                    vlm_client=vlm_fallback_client
                )
                logger.info(
                    f"Rule层字段级VLM重试已启用 (引擎: {self.config.vlm_fallback_engine})"
                )
            except ImportError as e:
                logger.warning("Rule层字段级VLM重试未启用（导入失败）: %s", e)

        # 规则层：注入位置标注提取器
        from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer

        rule_layer = RuleExtractionLayer(position_extractor=self._position_extractor)

        # VLM 提取层：根据vlm_extraction_engine配置选择模型
        vlm_extraction_config = self.config.get_vlm_config(
            self.config.vlm_extraction_engine
        )
        logger.info(
            f"VLM 提取层使用: {self.config.vlm_extraction_engine} ({vlm_extraction_config.base_url})"
        )

        # Pipeline：注入规则层和VLM层
        self._pipeline = PlanEPlusPipeline(
            classifier=self._classifier,
            rule_layer=rule_layer,
            vlm_layer=VLMExtractionLayer(
                base_url=vlm_extraction_config.base_url,
                model_name=vlm_extraction_config.model_name,
                timeout=vlm_extraction_config.timeout,
            ),
            vlm_fallback_handler=self._vlm_fallback_handler,  # Rule层字段级VLM重试
        )
        logger.info(
            "OCRService v2.1 初始化 | VLM提取=%s | Rule层VLM重试=%s | 位置标注=%s",
            self.config.vlm_extraction_engine,
            self.config.vlm_fallback_engine,
            "启用" if self._position_extractor else "禁用",
        )

    @classmethod
    def from_env(cls) -> "OCRService":
        """从环境变量加载配置创建服务实例"""
        return cls(config=OCRConfig.from_env())

    # ========== 纯OCR文本提取 ==========

    def run_ocr(self, image_path: str) -> str:
        """
        调用OCR引擎进行纯文本提取（不做字段解析）

        v2.0 简化：只使用 PP-OCRv6
        v4.0 新增：可选的图像预处理

        Args:
            image_path: 图片路径

        Returns:
            OCR识别的文本，失败返回空字符串
        """
        ocr_start = time.time()

        try:
            from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper

            # 延迟初始化 PaddleOCRWrapper（双重检查锁定模式）
            if self._paddleocr_wrapper is None:
                with self._paddleocr_lock:
                    if self._paddleocr_wrapper is None:
                        self._paddleocr_wrapper = PaddleOCRWrapper(
                            device="cpu",
                            default_engine="ppocr",
                        )
                        logger.info("PaddleOCR 引擎已初始化: PP-OCRv6")

            # 图像预处理（如果启用）
            preprocess_path = None
            if self.config.enable_image_preprocessing:
                try:
                    from ocr_three_layer_hybrid.image_preprocessor import enhance_image

                    preprocess_start = time.time()
                    preprocess_path = enhance_image(
                        image_path,
                        enable_denoise=self.config.preprocessing_denoise,
                        enable_deskew=self.config.preprocessing_deskew,
                        enable_contrast=self.config.preprocessing_contrast,
                        enable_binarize=self.config.preprocessing_binarize,
                    )
                    preprocess_time = time.time() - preprocess_start
                    logger.info(
                        "[预处理] %s | 耗时=%.2fs",
                        Path(image_path).name,
                        preprocess_time,
                    )
                    # 使用预处理后的图片进行 OCR
                    ocr_image_path = preprocess_path
                except Exception as e:
                    logger.warning("[预处理] 失败，使用原图: %s", e)
                    ocr_image_path = image_path
            else:
                ocr_image_path = image_path

            # 运行 OCR
            result = self._paddleocr_wrapper.run_ocr(ocr_image_path)
            text = result.full_text

            ocr_time = time.time() - ocr_start
            logger.info(
                "[OCR] %s | 引擎=ppocr | 耗时=%.2fs | 文本长度=%d字 | 预处理=%s",
                Path(image_path).name,
                ocr_time,
                len(text),
                "是" if self.config.enable_image_preprocessing else "否",
            )
            return text
        except Exception as e:
            ocr_time = time.time() - ocr_start
            logger.error(
                "[OCR] 失败 | %s | 引擎=ppocr | 耗时=%.2fs | 错误=%s",
                Path(image_path).name,
                ocr_time,
                e,
            )
            return ""

    # ========== 单图处理 ==========

    def process_single(self, image_path: str, ocr_text: str = "") -> Dict[str, Any]:
        """
        处理单张图片：分类 + 提取

        Args:
            image_path: 图片路径
            ocr_text: OCR识别文本（可为空，空时自动运行OCR）

        Returns:
            包含分类结果、提取结果、Pipeline详情的字典
        """
        img_name = Path(image_path).name

        # 如果未提供OCR文本，自动运行OCR
        if not ocr_text:
            ocr_text = self.run_ocr(image_path)

        ocr_texts = [ocr_text] if ocr_text else []
        full_text = " ".join(ocr_texts)

        # 1. 分类（获取详细metadata）
        classify_start = time.time()
        doc_info = self._classifier.classify(image_path, ocr_texts)
        classify_time = time.time() - classify_start

        # 2. 提取（通过Pipeline，传入已分类的doc_info避免重复分类）
        extract_start = time.time()
        result = self._pipeline.process(image_path, ocr_texts, doc_info=doc_info)
        extract_time = time.time() - extract_start

        total_ms = round((classify_time + extract_time) * 1000, 1)
        logger.info(
            "[处理] %s | 类型=%s | 路由=%s | 层=%s | 分类=%.1fms | 提取=%.1fms | 总计=%.1fms",
            img_name,
            doc_info.doc_type.value,
            doc_info.metadata.get("route", "unknown"),
            result.layer.value if result.layer else "none",
            round(classify_time * 1000, 1),
            round(extract_time * 1000, 1),
            total_ms,
        )
        if not result.success:
            logger.warning(
                "[提取失败] %s | 类型=%s | 错误=%s",
                img_name,
                doc_info.doc_type.value,
                result.error_message,
            )

        # 3. 构建返回结果
        return {
            "classification": self._build_classification_dict(doc_info),
            "extraction": {
                "success": result.success,
                "layer": result.layer.value if result.layer else "none",
                "fields": result.fields,
                "error_message": result.error_message,
                "vlm_fallback_enabled": self._vlm_fallback_handler is not None,
                "vlm_fallback_triggered": getattr(
                    result, "vlm_fallback_triggered", False
                ),
                "vlm_fallback_fields": getattr(result, "vlm_fallback_fields", []),
            },
            "pipeline_flow": self._build_pipeline_flow(doc_info, result),
            "timing": {
                "classify_ms": round(classify_time * 1000, 1),
                "extract_ms": round(extract_time * 1000, 1),
                "total_ms": round((classify_time + extract_time) * 1000, 1),
            },
            "ocr_text": full_text,
            "image_path": image_path,
        }

    # 向后兼容别名
    process_image = process_single

    # ========== 多页文档处理 ==========

    def process_multi_page(
        self,
        image_paths: List[str],
        max_pages: int = 15,
    ) -> Dict[str, Any]:
        """
        处理多页文档：逐页独立分类 + 逐页 RULE 提取 + 失败页 VLM 兜底 + 字段合并

        核心原则：RULE 优先，VLM 兜底。
        所有文档类型统一走逐页分类 → 提取 → 合并流程。

        Args:
            image_paths: 图片路径列表（按页码排序）
            max_pages: 最大处理页数（默认15页，性能优化）

        Returns:
            包含分类结果、合并后的提取结果、处理详情的字典
        """
        if not image_paths:
            return {
                "classification": {"doc_type": "未知", "confidence": 0},
                "extraction": {
                    "success": False,
                    "layer": "none",
                    "fields": {},
                    "error_message": "没有图片",
                },
                "timing": {"total_ms": 0},
            }

        total_start = time.time()
        pages_to_process = image_paths[:max_pages]

        # 1. 对第一页进行OCR和分类（仅用于日志和返回结果的 doc_type）
        first_page_text = self.run_ocr(pages_to_process[0])
        first_page_texts = [first_page_text] if first_page_text else []

        classify_start = time.time()
        first_doc_info = self._classifier.classify(pages_to_process[0], first_page_texts)
        classify_time = time.time() - classify_start

        # 获取基础文档类型（用于返回结果）
        base_doc_type = self._get_base_doc_type(first_doc_info.doc_type)

        logger.info(
            "[多页] 基础类型=%s | 首页细分=%s | 总页数=%d | 处理页数=%d",
            base_doc_type.value,
            first_doc_info.doc_type.value,
            len(image_paths),
            len(pages_to_process),
        )

        # 2. 所有类型统一走逐页分类 + 提取 + 合并
        result = self._extract_multi_page_merge(pages_to_process, first_doc_info)

        extract_time = time.time() - total_start - classify_time
        total_time = time.time() - total_start

        logger.info(
            "[多页] 完成 | 基础类型=%s | 页数=%d | 成功字段=%d | 分类=%.1fms | 提取=%.1fms | 总计=%.1fms",
            base_doc_type.value,
            len(pages_to_process),
            len([v for v in result.fields.values() if v and v.strip()]),
            round(classify_time * 1000, 1),
            round(extract_time * 1000, 1),
            round(total_time * 1000, 1),
        )

        return {
            "classification": self._build_classification_dict(first_doc_info),
            "extraction": {
                "success": result.success,
                "layer": result.layer.value if result.layer else "none",
                "fields": result.fields,
                "error_message": result.error_message,
            },
            "multi_page": {
                "total_pages": len(image_paths),
                "processed_pages": len(pages_to_process),
                "doc_type": base_doc_type.value,
            },
            "timing": {
                "classify_ms": round(classify_time * 1000, 1),
                "extract_ms": round(extract_time * 1000, 1),
                "total_ms": round(total_time * 1000, 1),
            },
            "image_paths": image_paths,
        }

    def _get_base_doc_type(self, doc_type: DocumentType) -> DocumentType:
        """获取基础文档类型（去除页面类型后缀）

        例如：HOUSEHOLD_REGISTER_COVER → HOUSEHOLD_REGISTER
              PURCHASE_CONTRACT_FIRST_PAGE → PURCHASE_CONTRACT
              DIVORCE_CERTIFICATE_CONTENT → DIVORCE_CERTIFICATE
        """
        base_mapping = {
            # 身份证
            DocumentType.ID_CARD_FRONT: DocumentType.ID_CARD,
            DocumentType.ID_CARD_BACK: DocumentType.ID_CARD,
            # 结婚证
            DocumentType.MARRIAGE_CERTIFICATE_COVER: DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_CONTENT: DocumentType.MARRIAGE_CERTIFICATE,
            DocumentType.MARRIAGE_CERTIFICATE_STAMP: DocumentType.MARRIAGE_CERTIFICATE,
            # 离婚证
            DocumentType.DIVORCE_CERTIFICATE_COVER: DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_CONTENT: DocumentType.DIVORCE_CERTIFICATE,
            DocumentType.DIVORCE_CERTIFICATE_STAMP: DocumentType.DIVORCE_CERTIFICATE,
            # 户口本
            DocumentType.HOUSEHOLD_REGISTER_COVER: DocumentType.HOUSEHOLD_REGISTER,
            DocumentType.HOUSEHOLD_REGISTER_CONTENT: DocumentType.HOUSEHOLD_REGISTER,
            # 不动产权证书
            DocumentType.PROPERTY_CERTIFICATE_FIRST_PAGE: DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_CONTENT: DocumentType.PROPERTY_CERTIFICATE,
            DocumentType.PROPERTY_CERTIFICATE_ATTACHMENT: DocumentType.PROPERTY_CERTIFICATE,
            # 购房合同
            DocumentType.PURCHASE_CONTRACT_FIRST_PAGE: DocumentType.PURCHASE_CONTRACT,
            DocumentType.PURCHASE_CONTRACT_CONTENT: DocumentType.PURCHASE_CONTRACT,
            DocumentType.PURCHASE_CONTRACT_STAMP: DocumentType.PURCHASE_CONTRACT,
            # 存量房合同
            DocumentType.STOCK_CONTRACT_FIRST_PAGE: DocumentType.STOCK_CONTRACT,
            DocumentType.STOCK_CONTRACT_CONTENT: DocumentType.STOCK_CONTRACT,
            DocumentType.STOCK_CONTRACT_STAMP: DocumentType.STOCK_CONTRACT,
            # 资金监管协议
            DocumentType.FUND_SUPERVISION_AGREEMENT_FIRST_PAGE: DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_INFO_PAGE: DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_AGREEMENT_STAMP: DocumentType.FUND_SUPERVISION,
            DocumentType.FUND_SUPERVISION_CERTIFICATE: DocumentType.FUND_SUPERVISION,
        }
        return base_mapping.get(doc_type, doc_type)

    def _extract_multi_page_merge(
        self,
        image_paths: List[str],
        first_page_doc_info: Any,
    ) -> Any:
        """逐页独立分类 + RULE 提取 + 失败页 VLM 兜底 + 字段合并

        核心流程：
        1. 首页复用已有分类，后续页独立分类
        2. 根据 field_configs 判断是否跳过（skip=True 的页面不提取）
        3. RULE 层提取后检查必填字段是否满足
        4. 必填字段未满足 → 该页 VLM 兜底
        5. 合并所有页的提取结果（取第一个非空值）
        6. 返回基础文档类型（非首页细分类型）

        使用 multi_page_utils.iterate_extract_merge() 公共函数处理
        逐页迭代+合并逻辑，避免与 vlm_layer.py 重复实现。
        """
        from ocr_three_layer_hybrid.interfaces import ExtractionResult, FieldConflict
        from ocr_three_layer_hybrid.multi_page_utils import (
            iterate_extract_merge,
            determine_extraction_success,
        )

        # 获取字段配置（用于判断 skip 和 required）
        field_configs = get_default_document_field_configs()

        # 收集每页的提取结果（用于冲突检测）和其他状态
        page_results: List[tuple] = []  # (page_type, result)
        last_layer = ProcessingLayer.RULE
        last_error = ""
        any_vlm_fallback = False
        total_time = 0.0

        # 定义单页提取函数（闭包，捕获 self、field_configs 等上下文）
        def extract_page(img_path: str, page_idx: int) -> Optional[Dict[str, str]]:
            nonlocal last_layer, last_error, any_vlm_fallback, total_time

            page_type = f"page_{page_idx}"

            # === 1. 分类：首页复用，后续页独立分类 ===
            if page_idx == 0:
                page_doc_info = first_page_doc_info
            else:
                ocr_text_for_classify = self.run_ocr(img_path)
                ocr_texts_for_classify = [ocr_text_for_classify] if ocr_text_for_classify else []
                page_doc_info = self._classifier.classify(img_path, ocr_texts_for_classify)

                # ★ 方案C：多页协同 - UNKNOWN页从首页继承细分类型 ★
                # 仅在以下条件同时满足时继承：
                #   1. 当前页分类为 UNKNOWN
                #   2. 首页置信度 >= 0.85（首页分类可信）
                #   3. 首页细分类型非 UNKNOWN（首页有明确类型）
                #   4. 继承的类型有 field_config 且不是 skip（确保能被处理）
                # 注意：继承细分类型（非基础类型），因为 field_config 只配置了细分类型。
                # 避免重蹈 commit 3925d64 "全页复用首页" 的 bug：仅 UNKNOWN 页继承。
                if (
                    page_doc_info.doc_type == DocumentType.UNKNOWN
                    and first_page_doc_info.confidence >= 0.85
                ):
                    inherited_type = first_page_doc_info.doc_type
                    inherited_config = field_configs.get(inherited_type)
                    if (
                        inherited_type != DocumentType.UNKNOWN
                        and inherited_config is not None
                        and not inherited_config.skip
                    ):
                        logger.info(
                            "[多页] 页 %d | 分类为UNKNOWN | 首页类型=%s(conf=%.2f) → 继承为%s",
                            page_idx,
                            first_page_doc_info.doc_type.value,
                            first_page_doc_info.confidence,
                            inherited_type.value,
                        )
                        page_doc_info = DocumentInfo(
                            image_path=page_doc_info.image_path,
                            doc_type=inherited_type,
                            page_type=page_doc_info.page_type,
                            ocr_texts=page_doc_info.ocr_texts,
                            confidence=first_page_doc_info.confidence * 0.9,
                            metadata={
                                **page_doc_info.metadata,
                                "inherited_from_first_page": True,
                                "original_doc_type": "UNKNOWN",
                                "inherited_doc_type": inherited_type.value,
                            },
                        )

            current_doc_type = page_doc_info.doc_type

            # === 2. 获取该细分类型的字段配置 ===
            config = field_configs.get(current_doc_type)
            if config is None:
                logger.info(
                    "[多页] 页 %d | %s | 无字段配置，跳过",
                    page_idx, current_doc_type.value,
                )
                return None

            # === 3. 检查是否跳过 ===
            if config.skip:
                logger.info(
                    "[多页] 页 %d | %s | 跳过（明确定义不提取）",
                    page_idx, current_doc_type.value,
                )
                return None

            all_field_names = config.get_all_field_names()
            if not all_field_names:
                return None

            # === 4. RULE 层提取 ===
            ocr_text = self.run_ocr(img_path)
            ocr_texts = [ocr_text] if ocr_text else []

            result = self._pipeline.process(img_path, ocr_texts, doc_info=page_doc_info)
            page_results.append((page_type, result))
            last_layer = result.layer
            total_time += result.time_cost

            if not result.success and result.error_message:
                last_error = result.error_message
                logger.warning(
                    "[多页] 页 %d | %s | RULE 层失败: %s",
                    page_idx, current_doc_type.value, result.error_message,
                )

            # === 5. 检查必填字段，决定是否需要 Rule层VLM重试 ===
            missing_required = config.get_missing_required_fields(result.fields)

            if missing_required:
                logger.info(
                    "[多页] 页 %d | %s | RULE层缺失必填字段: %s → Rule层VLM重试",
                    page_idx, current_doc_type.value, missing_required,
                )
                any_vlm_fallback = True

                # Rule层VLM重试：用所有字段名构建 prompt
                vlm_result = self._vlm_fallback_for_page(page_doc_info, all_field_names)

                if vlm_result and vlm_result.success:
                    # 方案 C：只用 VLM 填充 RULE 缺失的字段，已有的不覆盖
                    for field_name in missing_required:
                        vlm_value = vlm_result.fields.get(field_name, "")
                        rule_value = result.fields.get(field_name, "")
                        if vlm_value and vlm_value.strip():
                            if rule_value and rule_value.strip() and rule_value != vlm_value:
                                logger.info(
                                    "[Rule层VLM重试] 页 %d | 字段'%s': RULE='%s', VLM='%s' → 保留RULE值",
                                    page_idx, field_name, rule_value, vlm_value,
                                )
                            else:
                                result.fields[field_name] = vlm_value
                                logger.info(
                                    "[Rule层VLM重试] 页 %d | 字段'%s' 由VLM填充: '%s'",
                                    page_idx, field_name, vlm_value,
                                )
                    result.vlm_fallback_triggered = True
                    result.vlm_fallback_fields = missing_required

            return result.fields

        # === 使用公共函数执行逐页迭代+合并 ===
        merged_fields, _ = iterate_extract_merge(
            image_paths,
            extract_page,
            max_pages=len(image_paths),  # 已在 process_multi_page 中截断
            log_context="多页",
        )

        # === 6. 检测字段冲突 ===
        conflicts: List[FieldConflict] = []
        for page_idx, (page_type, result) in enumerate(page_results):
            if not result.success:
                continue
            for key, value in result.fields.items():
                if not value or not value.strip():
                    continue
                for other_idx, (other_page_type, other_result) in enumerate(page_results):
                    if other_idx <= page_idx or not other_result.success:
                        continue
                    other_value = other_result.fields.get(key, "")
                    if not other_value or not other_value.strip():
                        continue
                    if value != other_value:
                        conflicts.append(FieldConflict(
                            field_name=key,
                            source_a_value=value,
                            source_b_value=other_value,
                            source_a_page=page_type,
                            source_b_page=other_page_type,
                            resolved_value=merged_fields.get(key, value),
                        ))

        # === 7. 成功判断：基于基础类型的 field_configs ===
        base_doc_type = self._get_base_doc_type(first_page_doc_info.doc_type)
        base_config = field_configs.get(base_doc_type)

        if base_config and base_config.required_fields:
            required_names = [f.name for f in base_config.required_fields]
            success = determine_extraction_success(merged_fields, required_names)
            if not success:
                missing = base_config.get_missing_required_fields(merged_fields)
                logger.info("[多页] 合并后仍缺失必填字段: %s", missing)
        else:
            success = determine_extraction_success(merged_fields)

        # === 8. 构建返回结果 ===
        extraction_result = ExtractionResult(
            doc_type=base_doc_type,  # 返回基础类型
            layer=last_layer,
            fields=merged_fields,
            success=success,
            time_cost=total_time,
            error_message=last_error if not success else "",
            vlm_fallback_triggered=any_vlm_fallback,
        )

        if conflicts:
            extraction_result.field_conflicts = conflicts

        return extraction_result

    def _vlm_fallback_for_page(
        self,
        doc_info: DocumentInfo,
        field_names: List[str],
    ) -> Optional[ExtractionResult]:
        """对单页进行 Rule层VLM重试提取

        Args:
            doc_info: 页面分类信息
            field_names: 需要提取的字段列表

        Returns:
            VLM 提取结果，失败返回 None
        """
        try:
            vlm_layer = self._pipeline._get_layer(ProcessingLayer.VLM)
            if vlm_layer is None:
                return None

            # 使用 VLM 层提取（传入完整的字段列表）
            return vlm_layer.extract(doc_info, field_names)
        except Exception as e:
            logger.warning("[Rule层VLM重试] 页提取失败: %s", e)
            return None

    # ========== 批量处理 ==========

    def process_batch(self, images: List[Dict]) -> List[Dict]:
        """
        批量处理图片

        Args:
            images: 图片列表，每项包含 file_path, text, expected_type 等

        Returns:
            每张图片的处理结果列表
        """
        total = len(images)
        batch_start = time.time()
        logger.info("[批量] 开始处理 %d 张图片", total)

        results = []
        for idx, img in enumerate(images, 1):
            file_path = img.get("file_path", "")
            text = img.get("text", "")
            expected = img.get("expected_type", "")
            page_status = img.get("page_status", "")

            try:
                result = self.process_single(file_path, text)
                actual_type = result["classification"]["doc_type"]
                is_correct = actual_type == expected

                # 附属页面特殊处理
                if not is_correct and page_status == "附属页面":
                    if result["classification"].get("vlm_result") == "附属页面":
                        is_correct = True

                results.append(
                    {
                        **result,
                        "file_path": file_path,
                        "expected_type": expected,
                        "page_status": page_status,
                        "is_correct": is_correct,
                        "file_name": Path(file_path).name,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "file_path": file_path,
                        "file_name": Path(file_path).name,
                        "expected_type": expected,
                        "page_status": page_status,
                        "is_correct": False,
                        "error": str(e),
                        "classification": {
                            "doc_type": "错误",
                            "confidence": 0,
                            "route": "error",
                        },
                        "extraction": {"success": False, "layer": "none", "fields": {}},
                        "timing": {"total_ms": 0},
                    }
                )

        # 批量统计
        correct = sum(1 for r in results if r.get("is_correct"))
        batch_time = time.time() - batch_start
        logger.info(
            "[批量] 完成 | 总数=%d | 正确=%d | 准确率=%.1f%% | 耗时=%.2fs",
            total,
            correct,
            (correct / total * 100) if total > 0 else 0,
            batch_time,
        )
        return results

    # ========== 目录批量处理 ==========

    def process_directory(self, dir_path: str) -> Dict[str, Any]:
        """
        扫描目录并批量处理其中的所有图片

        流程：扫描图片 → OCR文本提取 → 分类+提取 → 统计

        Args:
            dir_path: 目录路径

        Returns:
            {
                "results": [...],
                "stats": {
                    "total": int,
                    "total_time_s": float,
                    "ocr_time_s": float,
                    "pipeline_time_s": float,
                    "avg_time_ms": float,
                    "type_distribution": {...}
                }
            }
            或目录不存在时返回 {"error": "..."}
        """
        dir_p = Path(dir_path)
        if not dir_p.exists() or not dir_p.is_dir():
            return {"error": f"目录不存在: {dir_path}"}

        # 收集图片文件
        image_files = sorted(
            [
                f
                for f in dir_p.iterdir()
                if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTENSIONS
            ]
        )

        if not image_files:
            return {"error": f"目录中没有找到图片文件: {dir_path}"}

        # Phase 1: OCR文本提取
        start_time = time.time()
        images = []
        for f in image_files:
            ocr_text = self.run_ocr(str(f))
            images.append(
                {
                    "file_path": str(f),
                    "file_name": f.name,
                    "text": ocr_text,
                    "expected_type": "",
                    "page_status": "",
                }
            )
        ocr_time = time.time() - start_time

        # Phase 2: 分类+提取
        results = self.process_batch(images)
        total_time = time.time() - start_time
        pipeline_time = total_time - ocr_time

        total = len(results)

        # 按类型统计
        type_stats: Dict[str, int] = {}
        layer_stats: Dict[str, int] = {}
        for r in results:
            actual = r.get("classification", {}).get("doc_type", "未知")
            type_stats[actual] = type_stats.get(actual, 0) + 1
            layer = r.get("extraction", {}).get("layer", "none")
            layer_stats[layer] = layer_stats.get(layer, 0) + 1

        logger.info(
            "[目录] %s | 图片=%d | OCR=%.2fs | Pipeline=%.2fs | 总计=%.2fs | 类型分布=%s | 层分布=%s",
            dir_p.name,
            total,
            ocr_time,
            pipeline_time,
            total_time,
            dict(sorted(type_stats.items(), key=lambda x: -x[1])),
            layer_stats,
        )

        return {
            "results": results,
            "stats": {
                "total": total,
                "total_time_s": round(total_time, 2),
                "ocr_time_s": round(ocr_time, 2),
                "pipeline_time_s": round(pipeline_time, 2),
                "avg_time_ms": round(total_time / total * 1000, 1) if total > 0 else 0,
                "type_distribution": type_stats,
            },
        }

    # ========== 内部辅助方法 ==========

    @staticmethod
    def _build_classification_dict(doc_info) -> Dict[str, Any]:
        """构建分类结果字典"""
        return {
            "doc_type": doc_info.doc_type.value,
            "doc_type_label": doc_info.doc_type.value,
            "confidence": doc_info.confidence,
            "route": doc_info.metadata.get("route", "unknown"),
            "route_name": ROUTE_NAMES.get(
                doc_info.metadata.get("route", ""),
                doc_info.metadata.get("route", "unknown"),
            ),
            "signal": doc_info.metadata.get("signal", ""),
            "primary_signals": doc_info.metadata.get("primary", []),
            "vlm_result": doc_info.metadata.get("vlm_result", ""),
            "is_attachment": doc_info.metadata.get("is_attachment", False),
        }

    @staticmethod
    def _build_pipeline_flow(doc_info, result) -> Dict[str, Any]:
        """构建Pipeline流程图数据"""
        route = doc_info.metadata.get("route", "")

        # 确定哪个阶段匹配了
        active_stage = None
        stage_match_info = ""

        if route == "multi_doc_conflict_resolution":
            active_stage = "stage0"
            stage_match_info = doc_info.metadata.get("signal", "")
        elif route == "standard_certificate":
            active_stage = "stage1"
            stage_match_info = doc_info.metadata.get("signal", "")
        elif route == "backup_certificate":
            active_stage = "stage1_5"
            signals = doc_info.metadata.get("primary", []) + doc_info.metadata.get(
                "required", []
            )
            stage_match_info = " + ".join(signals)
        elif route == "additional_backup":
            active_stage = "stage1_6"
            signals = doc_info.metadata.get("primary", [])
            stage_match_info = " + ".join(signals)
        elif route in ("standard_document", "standard_document_weak"):
            active_stage = "stage2"
            stage_match_info = doc_info.metadata.get("signal", "")
        elif route == "contract_field_combination":
            active_stage = "stage3"
            stage_match_info = "合同字段匹配"
        elif route == "vlm_fallback_required":
            active_stage = "stage4"
            stage_match_info = doc_info.metadata.get("vlm_result", "")

        # 确定提取层
        extraction_layer = result.layer.value if result.layer else "none"

        return {
            "stages": PIPELINE_STAGES,
            "active_stage": active_stage,
            "stage_match_info": stage_match_info,
            "extraction_layer": extraction_layer,
            "layer_color": LAYER_COLORS.get(extraction_layer, "#6b7280"),
            "doc_type": doc_info.doc_type.value,
        }
