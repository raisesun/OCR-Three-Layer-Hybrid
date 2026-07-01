#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置管理

集中管理所有外部服务地址、超时时间、模型名称。
支持从环境变量覆盖默认值。
"""

import os
from dataclasses import dataclass, field


@dataclass
class VLMServiceConfig:
    """GLM-OCR 视觉模型服务配置（端口8080）

    用于：
    - VLM提取层 (vlm_layer.py) — 字段提取
    - 纯OCR文本提取 (service.run_ocr)
    """
    base_url: str = "http://localhost:8080/v1"
    model_name: str = "GLM-OCR-Q8_0.gguf"
    timeout: float = 120.0
    api_key: str = "not-needed"


@dataclass
class QwenVLServiceConfig:
    """Qwen2.5-VL-7B 视觉模型服务配置（端口8082）

    用于：
    - VLM提取层 (vlm_layer.py) — 字段提取（备选）
    """
    base_url: str = "http://localhost:8082/v1"
    model_name: str = "qwen2.5-vl-7b"
    timeout: float = 120.0
    api_key: str = "not-needed"


@dataclass
class ClassificationServiceConfig:
    """Qwen VLM 分类服务配置（端口8081）

    用于：
    - VLM分类器 (vlm_classifier.py) — 文档分类兜底
    """
    base_url: str = "http://localhost:8081/v1"
    model_name: str = "Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf"
    timeout: float = 120.0


@dataclass
class LLMServiceConfig:
    """Ollama LLM 服务配置（端口11434）

    用于：
    - LLM提取层 (llm_layer.py) — 通过 paddleocr PPChatOCRv4 间接调用
    """
    base_url: str = "http://localhost:11434/v1"
    model_name: str = "qwen2.5:1.5b"
    api_key: str = "ollama"
    timeout: float = 180.0
    embed_model: str = "nomic-embed-text"


@dataclass
class OCRConfig:
    """顶层配置：聚合所有子配置

    Usage:
        # 默认配置
        config = OCRConfig()

        # 从环境变量加载（支持 GLM_OCR_URL, QWEN_VLM_URL, OLLAMA_URL）
        config = OCRConfig.from_env()

        # 自定义
        config = OCRConfig()
        config.vlm_service.base_url = "http://custom-host:8080/v1"
    """
    vlm_service: VLMServiceConfig = field(default_factory=VLMServiceConfig)
    qwen_vl_service: QwenVLServiceConfig = field(default_factory=QwenVLServiceConfig)
    classification: ClassificationServiceConfig = field(default_factory=ClassificationServiceConfig)
    llm_service: LLMServiceConfig = field(default_factory=LLMServiceConfig)
    enable_vlm_fallback: bool = True
    enable_position_extraction: bool = True  # 启用位置标注提取（户口本首页）
    enable_vlm_field_fallback: bool = True   # 启用字段级VLM兜底（校验失败时触发）

    # OCR 引擎配置（Phase 2 优化）
    # 注意：分层策略（tiered）测试失败，准确率下降且速度变慢，不推荐使用
    ocr_engine: str = "ppocr"  # "tiered" | "glm_ocr" | "ppocr" | "paddleocr_vl" | "structure_v3"
    # 说明：
    # - tiered: 分层策略（不推荐，准确率68%，速度66.9秒）
    # - glm_ocr: GLM-OCR（当前生产环境，27秒/张，准确率66%）
    # - ppocr: PP-OCRv6（推荐，41.5秒/张，准确率70%）
    # - paddleocr_vl: PaddleOCR-VL（备用，151秒/张，精度高）
    # - structure_v3: PP-StructureV3（已弃用，性能不稳定）

    # VLM 提取引擎配置（Phase 3 新增）
    # 用于字段提取阶段，支持多种 VLM 模型
    vlm_extraction_engine: str = "glm_ocr"  # "glm_ocr" | "qwen2_5_vl_7b"
    # 说明：
    # - glm_ocr: GLM-OCR（当前默认，端口8080）
    # - qwen2_5_vl_7b: Qwen2.5-VL-7B（待测试，端口8082）

    @classmethod
    def from_env(cls) -> "OCRConfig":
        """从环境变量加载配置，未设置则使用默认值"""
        cfg = cls()
        if url := os.getenv("GLM_OCR_URL"):
            cfg.vlm_service.base_url = url
        if url := os.getenv("QWEN_VLM_URL"):
            cfg.classification.base_url = url
        if url := os.getenv("OLLAMA_URL"):
            cfg.llm_service.base_url = url
        return cfg
