"""
OCR三层混合架构 v2.0

第1层：文档分类器（规则分类器）
第2A层：规则层（固定文档：身份证、户口本、结婚证、发票等）
第2B层：VLM层（半固定文档：离婚证、购房合同、存量房合同、房产证、UNKNOWN等）

v2.0 简化：
- 移除 LLM层（PP-ChatOCRv4）
- 移除 VLM分类兜底
- 移除 PaddleOCR-VL备用引擎
- VLM层增强：支持类型识别+提取、多页文档处理
"""

__version__ = "2.0.0"

from ocr_three_layer_hybrid.interfaces import (
    DocumentType,
    ProcessingLayer,
    DocumentInfo,
    ExtractionResult,
    IDocumentClassifier,
    IExtractionLayer,
)
from ocr_three_layer_hybrid.classifier import KeywordDocumentClassifier
from ocr_three_layer_hybrid.rule_layer import RuleExtractionLayer
from ocr_three_layer_hybrid.vlm_layer import VLMExtractionLayer
from ocr_three_layer_hybrid.pipeline import PlanEPlusPipeline

__all__ = [
    # Interfaces
    "DocumentType",
    "ProcessingLayer",
    "DocumentInfo",
    "ExtractionResult",
    "IDocumentClassifier",
    "IExtractionLayer",
    # Implementations
    "KeywordDocumentClassifier",
    "RuleExtractionLayer",
    "VLMExtractionLayer",
    "PlanEPlusPipeline",
]
