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

    模型文件位置: /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF/
    - 主模型: GLM-OCR-Q8_0.gguf (906M)
    - MMProj: mmproj-GLM-OCR-Q8_0.gguf (462M)

    启动命令:
    cd /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF && llama-server \\
      --model GLM-OCR-Q8_0.gguf --mmproj mmproj-GLM-OCR-Q8_0.gguf \\
      --host 0.0.0.0 --port 8080 --ctx-size 8192
    """

    base_url: str = "http://localhost:8080/v1"
    model_name: str = "GLM-OCR-Q8_0.gguf"
    model_path: str = "/Users/dongsun/Github/models-OCR/GLM-OCR-GGUF"
    timeout: float = 120.0
    api_key: str = "not-needed"


@dataclass
class QwenVLServiceConfig:
    """Qwen2.5-VL-7B 视觉模型服务配置（端口8082）

    用于：
    - VLM提取层 (vlm_layer.py) — 字段提取（备选）

    模型文件位置: /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B/
    - 主模型: Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf (4.4G)
    - MMProj: Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf (814M)

    启动命令:
    cd /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B && llama-server \\
      --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \\
      --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \\
      --host 0.0.0.0 --port 8082 --ctx-size 8192
    """

    base_url: str = "http://localhost:8082/v1"
    model_name: str = "qwen2.5-vl-7b"
    model_path: str = "/Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B"
    timeout: float = 120.0
    api_key: str = "not-needed"


@dataclass
class OCRConfig:
    """顶层配置：聚合所有子配置

    Usage:
        # 默认配置
        config = OCRConfig()

        # 从环境变量加载（支持 GLM_OCR_URL, QWEN_VLM_URL）
        config = OCRConfig.from_env()

        # 自定义
        config = OCRConfig()
        config.vlm_service.base_url = "http://custom-host:8080/v1"
    """

    vlm_service: VLMServiceConfig = field(default_factory=VLMServiceConfig)
    qwen_vl_service: QwenVLServiceConfig = field(default_factory=QwenVLServiceConfig)
    enable_position_extraction: bool = True  # 启用位置标注提取（户口本首页）
    enable_vlm_field_fallback: bool = True  # 启用字段级VLM兜底（校验失败时触发）

    # OCR 引擎配置（Phase 2 优化）
    # 注意：分层策略（tiered）测试失败，准确率下降且速度变慢，不推荐使用
    ocr_engine: str = (
        "ppocr"  # "tiered" | "glm_ocr" | "ppocr" | "paddleocr_vl" | "structure_v3"
    )
    # 说明：
    # - tiered: 分层策略（不推荐，准确率68%，速度66.9秒）
    # - glm_ocr: GLM-OCR（当前生产环境，27秒/张，准确率66%）
    # - ppocr: PP-OCRv6（推荐，41.5秒/张，准确率70%）
    # - paddleocr_vl: PaddleOCR-VL（备用，151秒/张，精度高）
    # - structure_v3: PP-StructureV3（已弃用，性能不稳定）

    # VLM 引擎配置（支持不同场景使用不同模型）
    # 可选值: "glm_ocr" | "qwen2_5_vl_7b"
    # 说明:
    # - qwen2_5_vl_7b: Qwen2.5-VL-7B（默认，端口8082，理解能力强，速度快）
    # - glm_ocr: GLM-OCR（备选，端口8080，速度快但理解能力弱）

    # 1. VLM提取层：分类为"未知"时使用
    vlm_extraction_engine: str = "qwen2_5_vl_7b"

    # 2. VLM兜底处理器：规则层字段校验失败时触发
    vlm_fallback_engine: str = "qwen2_5_vl_7b"

    # 3. VLM纯OCR：用于纯文本提取（如需要）
    vlm_ocr_engine: str = "qwen2_5_vl_7b"

    # 图像预处理配置（Phase 4 新增）
    # 用于在 OCR 前对图像进行增强处理
    enable_image_preprocessing: bool = False  # 是否启用图像预处理
    preprocessing_denoise: bool = True  # 去噪
    preprocessing_deskew: bool = False  # 纠偏（默认禁用，对竖向文档误判）
    preprocessing_contrast: bool = True  # 对比度增强
    preprocessing_binarize: bool = False  # 二值化（默认关闭，会丢失灰度信息）

    @classmethod
    def from_env(cls) -> "OCRConfig":
        """从环境变量加载配置，未设置则使用默认值"""
        cfg = cls()
        if url := os.getenv("GLM_OCR_URL"):
            cfg.vlm_service.base_url = url
        if url := os.getenv("QWEN_VLM_URL"):
            cfg.qwen_vl_service.base_url = url
        return cfg

    def get_vlm_config(self, engine_name: str):
        """根据引擎名称获取对应的VLM配置

        Args:
            engine_name: VLM引擎名称 ("glm_ocr" | "qwen2_5_vl_7b")

        Returns:
            VLMServiceConfig 或 QwenVLServiceConfig

        Raises:
            ValueError: 不支持的引擎名称
        """
        if engine_name == "qwen2_5_vl_7b":
            return self.qwen_vl_service
        elif engine_name == "glm_ocr":
            return self.vlm_service
        else:
            raise ValueError(
                f"不支持的VLM引擎: {engine_name}，可选值: glm_ocr, qwen2_5_vl_7b"
            )


# =============================================================================
# 可用模型清单（模型文件位置: /Users/dongsun/Github/models-OCR/）
# =============================================================================
#
# 1. GLM-OCR（端口8080）✅ 运行中
#    路径: /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF/
#    文件: GLM-OCR-Q8_0.gguf (906M), mmproj-GLM-OCR-Q8_0.gguf (462M)
#    用途: OCR + VLM
#    启动: cd /Users/dongsun/Github/models-OCR/GLM-OCR-GGUF && llama-server \
#            --model GLM-OCR-Q8_0.gguf --mmproj mmproj-GLM-OCR-Q8_0.gguf \
#            --host 0.0.0.0 --port 8080 --ctx-size 8192
#
# 2. Qwen2.5-VL-7B（端口8082）✅ 运行中
#    路径: /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B/
#    文件: Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf (4.4G)
#          Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf (814M)
#    用途: VLM（字段提取）
#    启动: cd /Users/dongsun/Github/models-OCR/Qwen2.5-VL-7B && llama-server \
#            --model Qwen2.5-VL-7B-Instruct-abliterated.Q4_K_M-2.gguf \
#            --mmproj Qwen2.5-VL-7B-Instruct-abliterated.mmproj-Q8_0.gguf \
#            --host 0.0.0.0 --port 8082 --ctx-size 8192
#
# 3. Qwen3.5-4B（待启动）
#    路径: /Users/dongsun/Github/models-OCR/Qwen3.5-4B/
#    文件: Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf (2.5G)
#          mmproj-Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-BF16.gguf (644M)
#    用途: VLM（备选）
#    启动: cd /Users/dongsun/Github/models-OCR/Qwen3.5-4B && llama-server \
#            --model Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf \
#            --mmproj mmproj-Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-BF16.gguf \
#            --host 0.0.0.0 --port 8083 --ctx-size 8192
#
# 4. Qwen3.5-9B（待启动）
#    路径: /Users/dongsun/Github/models-OCR/Qwen3.5-9B/
#    文件: Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf (5.2G)
#          mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf (879M)
#    用途: VLM（备选，精度更高）
#    启动: cd /Users/dongsun/Github/models-OCR/Qwen3.5-9B && llama-server \
#            --model Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf \
#            --mmproj mmproj-Qwen3.5-9B-Uncensored-HauhauCS-Aggressive-BF16.gguf \
#            --host 0.0.0.0 --port 8084 --ctx-size 8192
#
# 5. PaddleOCR-VL-0.9B（PaddlePaddle格式，非GGUF）
#    路径: /Users/dongsun/Github/models-OCR/PaddleOCR-VL-0.9B/
#    文件: model.safetensors (1.9G)
#    用途: OCR（需要PaddlePaddle环境）
#
