#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块单元测试

覆盖：VLMServiceConfig, QwenVLServiceConfig, OCRConfig
"""

import os
import pytest
from ocr_three_layer_hybrid.config import (
    VLMServiceConfig,
    QwenVLServiceConfig,
    OCRConfig,
    SUPPORTED_FILE_EXTENSIONS,
)


class TestVLMServiceConfig:
    """GLM-OCR 服务配置测试"""

    def test_defaults(self):
        cfg = VLMServiceConfig()
        assert cfg.base_url == "http://localhost:8080/v1"
        assert cfg.model_name == "GLM-OCR-Q8_0.gguf"
        assert cfg.timeout == 120.0
        assert cfg.api_key == "not-needed"

    def test_custom_values(self):
        cfg = VLMServiceConfig(base_url="http://custom:9090/v1", timeout=60.0)
        assert cfg.base_url == "http://custom:9090/v1"
        assert cfg.timeout == 60.0


class TestQwenVLServiceConfig:
    """Qwen2.5-VL-7B 服务配置测试"""

    def test_defaults(self):
        cfg = QwenVLServiceConfig()
        assert cfg.base_url == "http://localhost:8082/v1"
        assert cfg.model_name == "qwen2.5-vl-7b"
        assert cfg.timeout == 120.0
        assert cfg.api_key == "not-needed"

    def test_custom_values(self):
        cfg = QwenVLServiceConfig(base_url="http://qwen:9091/v1", model_name="custom-model")
        assert cfg.base_url == "http://qwen:9091/v1"
        assert cfg.model_name == "custom-model"


class TestOCRConfig:
    """OCRConfig 顶层配置测试"""

    def test_defaults(self):
        cfg = OCRConfig()
        # 子配置
        assert isinstance(cfg.vlm_service, VLMServiceConfig)
        assert isinstance(cfg.qwen_vl_service, QwenVLServiceConfig)
        # 功能开关
        assert cfg.enable_position_extraction is True
        assert cfg.enable_vlm_field_fallback is True
        # OCR 引擎
        assert cfg.ocr_engine == "ppocr"
        # VLM 引擎分配
        assert cfg.vlm_extraction_engine == "qwen2_5_vl_7b"
        assert cfg.vlm_fallback_engine == "qwen2_5_vl_7b"
        assert cfg.vlm_ocr_engine == "qwen2_5_vl_7b"
        # 图像预处理
        assert cfg.enable_image_preprocessing is False
        assert cfg.preprocessing_denoise is True
        assert cfg.preprocessing_deskew is False
        assert cfg.preprocessing_contrast is True
        assert cfg.preprocessing_binarize is False

    def test_from_env_glm_url(self, monkeypatch):
        """GLM_OCR_URL 环境变量覆盖"""
        monkeypatch.setenv("GLM_OCR_URL", "http://env-host:8080/v1")
        cfg = OCRConfig.from_env()
        assert cfg.vlm_service.base_url == "http://env-host:8080/v1"
        # qwen_vl_service 保持默认
        assert cfg.qwen_vl_service.base_url == "http://localhost:8082/v1"

    def test_from_env_qwen_url(self, monkeypatch):
        """QWEN_VLM_URL 环境变量覆盖"""
        monkeypatch.setenv("QWEN_VLM_URL", "http://env-host:8082/v1")
        cfg = OCRConfig.from_env()
        assert cfg.qwen_vl_service.base_url == "http://env-host:8082/v1"
        # vlm_service 保持默认
        assert cfg.vlm_service.base_url == "http://localhost:8080/v1"

    def test_from_env_both_urls(self, monkeypatch):
        """两个 URL 同时覆盖"""
        monkeypatch.setenv("GLM_OCR_URL", "http://glm:8080/v1")
        monkeypatch.setenv("QWEN_VLM_URL", "http://qwen:8082/v1")
        cfg = OCRConfig.from_env()
        assert cfg.vlm_service.base_url == "http://glm:8080/v1"
        assert cfg.qwen_vl_service.base_url == "http://qwen:8082/v1"

    def test_from_env_no_vars(self, monkeypatch):
        """无环境变量时使用默认值"""
        monkeypatch.delenv("GLM_OCR_URL", raising=False)
        monkeypatch.delenv("QWEN_VLM_URL", raising=False)
        cfg = OCRConfig.from_env()
        assert cfg.vlm_service.base_url == "http://localhost:8080/v1"
        assert cfg.qwen_vl_service.base_url == "http://localhost:8082/v1"

    def test_get_vlm_config_qwen(self):
        """获取 Qwen VLM 配置"""
        cfg = OCRConfig()
        vlm_cfg = cfg.get_vlm_config("qwen2_5_vl_7b")
        assert isinstance(vlm_cfg, QwenVLServiceConfig)
        assert vlm_cfg.base_url == "http://localhost:8082/v1"

    def test_get_vlm_config_glm(self):
        """获取 GLM-OCR 配置"""
        cfg = OCRConfig()
        vlm_cfg = cfg.get_vlm_config("glm_ocr")
        assert isinstance(vlm_cfg, VLMServiceConfig)
        assert vlm_cfg.base_url == "http://localhost:8080/v1"

    def test_get_vlm_config_invalid(self):
        """不支持的引擎名称抛出 ValueError"""
        cfg = OCRConfig()
        with pytest.raises(ValueError, match="不支持的VLM引擎"):
            cfg.get_vlm_config("unknown_engine")


class TestSupportedFileExtensions:
    """支持的文件扩展名常量测试"""

    def test_common_formats_included(self):
        assert ".jpg" in SUPPORTED_FILE_EXTENSIONS
        assert ".jpeg" in SUPPORTED_FILE_EXTENSIONS
        assert ".png" in SUPPORTED_FILE_EXTENSIONS
        assert ".pdf" in SUPPORTED_FILE_EXTENSIONS

    def test_is_set(self):
        assert isinstance(SUPPORTED_FILE_EXTENSIONS, set)

    def test_no_empty_strings(self):
        assert "" not in SUPPORTED_FILE_EXTENSIONS
