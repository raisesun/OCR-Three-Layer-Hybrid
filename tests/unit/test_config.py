#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置模块单元测试
"""

import os
import pytest
from ocr_three_layer_hybrid.config import (
    VLMServiceConfig,
    ClassificationServiceConfig,
    LLMServiceConfig,
    OCRConfig,
)


class TestVLMServiceConfig:
    def test_defaults(self):
        cfg = VLMServiceConfig()
        assert cfg.base_url == "http://localhost:8080/v1"
        assert cfg.model_name == "GLM-OCR-Q8_0.gguf"
        assert cfg.timeout == 120.0

    def test_custom_values(self):
        cfg = VLMServiceConfig(base_url="http://custom:9090/v1", timeout=60.0)
        assert cfg.base_url == "http://custom:9090/v1"
        assert cfg.timeout == 60.0


class TestClassificationServiceConfig:
    def test_defaults(self):
        cfg = ClassificationServiceConfig()
        assert cfg.base_url == "http://localhost:8081/v1"
        assert "Qwen" in cfg.model_name
        assert cfg.timeout == 120.0


class TestLLMServiceConfig:
    def test_defaults(self):
        cfg = LLMServiceConfig()
        assert cfg.base_url == "http://localhost:11434/v1"
        assert cfg.api_key == "ollama"
        assert cfg.timeout == 180.0
        assert cfg.embed_model == "nomic-embed-text"


class TestOCRConfig:
    def test_defaults(self):
        cfg = OCRConfig()
        assert cfg.enable_vlm_fallback is True
        assert isinstance(cfg.vlm_service, VLMServiceConfig)
        assert isinstance(cfg.classification, ClassificationServiceConfig)
        assert isinstance(cfg.llm_service, LLMServiceConfig)

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("GLM_OCR_URL", "http://env-host:8080/v1")
        monkeypatch.setenv("QWEN_VLM_URL", "http://env-host:8081/v1")
        monkeypatch.setenv("OLLAMA_URL", "http://env-host:11434/v1")
        cfg = OCRConfig.from_env()
        assert cfg.vlm_service.base_url == "http://env-host:8080/v1"
        assert cfg.classification.base_url == "http://env-host:8081/v1"
        assert cfg.llm_service.base_url == "http://env-host:11434/v1"

    def test_from_env_partial(self, monkeypatch):
        monkeypatch.setenv("GLM_OCR_URL", "http://partial:8080/v1")
        monkeypatch.delenv("QWEN_VLM_URL", raising=False)
        monkeypatch.delenv("OLLAMA_URL", raising=False)
        cfg = OCRConfig.from_env()
        assert cfg.vlm_service.base_url == "http://partial:8080/v1"
        assert cfg.classification.base_url == "http://localhost:8081/v1"  # default
