"""
方案E+：三层混合OCR文档理解架构

第1层：文档分类器
第2A层：规则层（固定文档）
第2B层：VLM层（半固定文档）
第2C层：LLM层（复杂文档）
"""

__version__ = "1.1.0"

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
from ocr_three_layer_hybrid.llm_layer import PPChatOCRv4Layer
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
    "PPChatOCRv4Layer",
    "PlanEPlusPipeline",
]
