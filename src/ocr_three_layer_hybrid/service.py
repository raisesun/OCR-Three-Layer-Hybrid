#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR三层混合架构 — 正式服务层

提供对外统一的服务接口，封装 Pipeline 的分类+提取完整流程。

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
from pathlib import Path
from typing import Any, Dict, List, Optional

from ocr_three_layer_hybrid.config import OCRConfig
from ocr_three_layer_hybrid.external_services import VLMClient
from ocr_three_layer_hybrid.interfaces import DocumentType, ProcessingLayer
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.vlm_classifier import (
    VLMDocumentClassifier,
    HybridDocumentClassifier,
)
from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline


# ========== Pipeline 元数据常量（供前端流程图使用） ==========

# Pipeline阶段名称映射
ROUTE_NAMES = {
    "multi_doc_conflict_resolution": "阶段0: 多文档冲突检测",
    "standard_certificate": "阶段1: 标准证件强信号",
    "backup_certificate": "阶段1.5: 备选强信号",
    "additional_backup": "阶段1.6: 更多备选信号",
    "standard_document": "阶段2: 标准单证强信号",
    "standard_document_weak": "阶段2: 弱信号组合",
    "contract_field_combination": "阶段3: 合同字段组合",
    "vlm_fallback_required": "阶段4: VLM兜底",
    "vlm_classification": "VLM分类兜底",
}

# Pipeline阶段列表（用于流程图显示）
PIPELINE_STAGES = [
    {"id": "stage0", "name": "阶段0", "title": "多文档冲突检测", "keywords": "买受人+出卖人+房屋类型"},
    {"id": "stage1", "name": "阶段1", "title": "标准证件强信号", "keywords": "公民身份号码、常住人口登记卡等"},
    {"id": "stage1_5", "name": "阶段1.5", "title": "备选强信号", "keywords": "户口簿+户主、持证人+登记日期"},
    {"id": "stage1_6", "name": "阶段1.6", "title": "更多备选信号", "keywords": "户别+户主姓名、结婚证+登记机关"},
    {"id": "stage2", "name": "阶段2", "title": "标准单证强信号", "keywords": "发票代码+发票号码"},
    {"id": "stage3", "name": "阶段3", "title": "合同字段组合", "keywords": "买受人+出卖人+价款"},
    {"id": "stage4", "name": "阶段4", "title": "VLM分类兜底", "keywords": "Qwen3.5-4B视觉识别"},
]

# 提取层颜色映射
LAYER_COLORS = {
    "rule": "#10b981",    # 绿色
    "vlm": "#3b82f6",     # 蓝色
    "llm": "#8b5cf6",     # 紫色
    "none": "#6b7280",    # 灰色
}

# 支持的图片扩展名
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}


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

    handlers = []
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
    """OCR三层混合架构 — 统一服务接口

    整合分类器、Pipeline、VLM客户端，提供完整的文档处理服务。
    分类器只创建一次，同时注入到Pipeline中避免重复分类。

    增强（v2）：
    - 位置标注提取（户口本首页，通过PaddleOCR坐标）
    - VLM字段级兜底（校验失败时触发VLM重新提取）
    """

    def __init__(self, config: Optional[OCRConfig] = None, enable_vlm_fallback: bool = True):
        """
        初始化服务

        Args:
            config: 服务配置，不传则使用默认配置
            enable_vlm_fallback: 是否启用VLM分类兜底（向后兼容参数）
        """
        self.config = config or OCRConfig()
        self.config.enable_vlm_fallback = enable_vlm_fallback
        self._vlm_client = VLMClient(self.config.vlm_service)

        # 分类器：只创建一次
        self._rule_classifier = KeywordDocumentClassifier()
        self._vlm_classifier = VLMDocumentClassifier(
            base_url=self.config.classification.base_url,
            model=self.config.classification.model_name,
            timeout=self.config.classification.timeout,
        )

        if self.config.enable_vlm_fallback:
            self._classifier = HybridDocumentClassifier(
                self._rule_classifier, self._vlm_classifier
            )
        else:
            self._classifier = self._rule_classifier

        # 位置标注提取器（延迟初始化PaddleOCR）
        self._position_extractor = None
        if self.config.enable_position_extraction:
            try:
                from ocr_three_layer_hybrid.position_extractor import HouseholdPositionExtractor
                self._position_extractor = HouseholdPositionExtractor()
                logger.info("位置标注提取器已启用")
            except ImportError as e:
                logger.warning(f"位置标注提取器未启用（导入失败）: {e}")

        # VLM字段级兜底处理器
        self._vlm_fallback_handler = None
        if self.config.enable_vlm_field_fallback:
            try:
                from ocr_three_layer_hybrid.vlm_fallback import VLMFallbackHandler
                self._vlm_fallback_handler = VLMFallbackHandler(vlm_client=self._vlm_client)
                logger.info("VLM字段级兜底已启用")
            except ImportError as e:
                logger.warning(f"VLM字段级兜底未启用（导入失败）: {e}")

        # 规则层：注入位置标注提取器
        from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
        rule_layer = RuleExtractionLayer(position_extractor=self._position_extractor)

        # Pipeline：注入所有组件
        self._pipeline = PlanEPlusPipeline(
            classifier=self._classifier,
            rule_layer=rule_layer,
            vlm_layer=VLMExtractionLayer(
                base_url=self.config.vlm_service.base_url,
                model_name=self.config.vlm_service.model_name,
                timeout=self.config.vlm_service.timeout,
            ),
            enable_vlm_classification_fallback=self.config.enable_vlm_fallback,
            vlm_fallback_handler=self._vlm_fallback_handler,
        )
        logger.info(
            "OCRService 初始化 | VLM=%s | 分类=%s | 位置标注=%s | VLM兜底=%s",
            self.config.vlm_service.base_url,
            self.config.classification.base_url,
            "启用" if self._position_extractor else "禁用",
            "启用" if self._vlm_fallback_handler else "禁用",
        )

    @classmethod
    def from_env(cls) -> "OCRService":
        """从环境变量加载配置创建服务实例"""
        return cls(config=OCRConfig.from_env())

    # ========== 纯OCR文本提取 ==========

    def run_ocr(self, image_path: str) -> str:
        """
        调用OCR引擎进行纯文本提取（不做字段解析）

        支持多种引擎（通过 config.ocr_engine 配置）：
        - glm_ocr: GLM-OCR（当前生产环境，27秒/张）
        - ppocr: PP-OCRv6（推荐，11.88秒/张，稳定）
        - paddleocr_vl: PaddleOCR-VL（备用，151秒/张，精度高）
        - structure_v3: PP-StructureV3（已弃用，性能不稳定）

        Args:
            image_path: 图片路径

        Returns:
            OCR识别的文本，失败返回空字符串
        """
        ocr_start = time.time()
        engine_name = self.config.ocr_engine

        try:
            # 根据配置选择 OCR 引擎
            if engine_name == "glm_ocr":
                # 使用 GLM-OCR（原有逻辑）
                text = self._vlm_client.call(
                    prompt="请仔细识别图片中的所有文字内容，直接输出识别到的文字。",
                    image_path=image_path,
                    max_tokens=2048,
                )
            elif engine_name in ["ppocr", "paddleocr_vl", "structure_v3"]:
                # 使用 PaddleOCR 系列引擎
                from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper

                # 延迟初始化 PaddleOCRWrapper
                if not hasattr(self, "_paddleocr_wrapper"):
                    # 引擎名称映射：service 配置 → paddleocr_wrapper
                    engine_map = {
                        "ppocr": "ppocr",           # PP-OCRv6
                        "paddleocr_vl": "vlm",      # PaddleOCR-VL
                        "structure_v3": "structure_v3",  # PP-StructureV3（弃用）
                    }
                    self._paddleocr_wrapper = PaddleOCRWrapper(
                        device="cpu",
                        default_engine=engine_map.get(engine_name, "auto"),
                    )
                    logger.info(f"PaddleOCR 引擎已初始化: {engine_name} → {engine_map.get(engine_name)}")

                # 运行 OCR
                result = self._paddleocr_wrapper.run_ocr(image_path)
                text = result.full_text
            else:
                logger.error(f"未知的 OCR 引擎: {engine_name}，使用默认 ppocr")
                from ocr_three_layer_hybrid.paddleocr_wrapper import PaddleOCRWrapper
                if not hasattr(self, "_paddleocr_wrapper"):
                    self._paddleocr_wrapper = PaddleOCRWrapper(device="cpu")
                result = self._paddleocr_wrapper.run_ocr(image_path)
                text = result.full_text

            ocr_time = time.time() - ocr_start
            logger.info(
                "[OCR] %s | 引擎=%s | 耗时=%.2fs | 文本长度=%d字",
                Path(image_path).name, engine_name, ocr_time, len(text),
            )
            return text
        except Exception as e:
            ocr_time = time.time() - ocr_start
            logger.error(
                "[OCR] 失败 | %s | 引擎=%s | 耗时=%.2fs | 错误=%s",
                Path(image_path).name, engine_name, ocr_time, e,
            )
            return ""

    # ========== 单图处理 ==========

    def process_single(self, image_path: str, ocr_text: str = "") -> Dict[str, Any]:
        """
        处理单张图片：分类 + 提取

        Args:
            image_path: 图片路径
            ocr_text: OCR识别文本（可为空，空时会通过VLM分类兜底）

        Returns:
            包含分类结果、提取结果、Pipeline详情的字典
        """
        img_name = Path(image_path).name
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
                img_name, doc_info.doc_type.value, result.error_message,
            )

        # 3. 构建返回结果
        return {
            "classification": self._build_classification_dict(doc_info),
            "extraction": {
                "success": result.success,
                "layer": result.layer.value if result.layer else "none",
                "fields": result.fields,
                "error_message": result.error_message,
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

                results.append({
                    **result,
                    "file_path": file_path,
                    "expected_type": expected,
                    "page_status": page_status,
                    "is_correct": is_correct,
                    "file_name": Path(file_path).name,
                })
            except Exception as e:
                results.append({
                    "file_path": file_path,
                    "file_name": Path(file_path).name,
                    "expected_type": expected,
                    "page_status": page_status,
                    "is_correct": False,
                    "error": str(e),
                    "classification": {"doc_type": "错误", "confidence": 0, "route": "error"},
                    "extraction": {"success": False, "layer": "none", "fields": {}},
                    "timing": {"total_ms": 0},
                })

        # 批量统计
        correct = sum(1 for r in results if r.get("is_correct"))
        batch_time = time.time() - batch_start
        logger.info(
            "[批量] 完成 | 总数=%d | 正确=%d | 准确率=%.1f%% | 耗时=%.2fs",
            total, correct, (correct / total * 100) if total > 0 else 0, batch_time,
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
        image_files = sorted([
            f for f in dir_p.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
        ])

        if not image_files:
            return {"error": f"目录中没有找到图片文件: {dir_path}"}

        # Phase 1: OCR文本提取
        start_time = time.time()
        images = []
        for f in image_files:
            ocr_text = self.run_ocr(str(f))
            images.append({
                "file_path": str(f),
                "file_name": f.name,
                "text": ocr_text,
                "expected_type": "",
                "page_status": "",
            })
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
            dir_p.name, total, ocr_time, pipeline_time, total_time,
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
            signals = doc_info.metadata.get("primary", []) + doc_info.metadata.get("required", [])
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
        elif route in ("vlm_fallback_required", "vlm_classification"):
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
