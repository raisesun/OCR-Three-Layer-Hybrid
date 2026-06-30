#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一外部服务客户端

封装所有对外部模型的 HTTP 调用，消除各模块中重复的请求代码。

- VLMClient: GLM-OCR 视觉模型（端口8080），用于字段提取和纯OCR
- ClassificationClient: Qwen VLM 分类模型（端口8081），用于文档分类

注: llm_layer.py 通过 paddleocr 间接调用 Ollama，不走此客户端。
"""

import base64
from pathlib import Path
from typing import Optional

import requests

from .config import VLMServiceConfig, ClassificationServiceConfig


def encode_image_base64(image_path: str) -> str:
    """读取图片文件并返回 base64 编码字符串"""
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


class VLMClient:
    """GLM-OCR 视觉模型客户端

    封装对 llama-server (GLM-OCR) 的 OpenAI 兼容 API 调用。
    用于：
    - VLMExtractionLayer: 字段提取
    - OCRService.run_ocr: 纯文本提取
    """

    def __init__(self, config: Optional[VLMServiceConfig] = None):
        self.config = config or VLMServiceConfig()

    def call(self, prompt: str, image_path: str, max_tokens: int = 1024) -> str:
        """
        发送视觉+文本请求，返回模型响应文本

        Args:
            prompt: 文本提示
            image_path: 图片文件路径
            max_tokens: 最大输出 token 数

        Returns:
            模型响应文本

        Raises:
            requests.exceptions.RequestException: HTTP 请求失败
            FileNotFoundError: 图片文件不存在
        """
        if not Path(image_path).exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        image_b64 = encode_image_base64(image_path)

        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        resp = requests.post(
            f"{self.config.base_url}/chat/completions",
            json=payload,
            timeout=self.config.timeout,
        )
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ""

        return choices[0].get("message", {}).get("content", "")


class ClassificationClient:
    """Qwen VLM 分类客户端

    封装对 llama-server (Qwen3.5-4B) 的 OpenAI 兼容 API 调用。
    用于：
    - VLMDocumentClassifier: 文档分类兜底
    """

    def __init__(self, config: Optional[ClassificationServiceConfig] = None):
        self.config = config or ClassificationServiceConfig()

    def classify(self, prompt: str, image_path: str) -> str:
        """
        发送图片分类请求，返回模型响应文本

        Args:
            prompt: 分类提示词
            image_path: 图片文件路径

        Returns:
            模型响应文本（分类结果）

        Raises:
            requests.exceptions.RequestException: HTTP 请求失败
            FileNotFoundError: 图片文件不存在
        """
        if not Path(image_path).exists():
            raise FileNotFoundError(f"图片不存在: {image_path}")

        image_b64 = encode_image_base64(image_path)

        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": 50,  # 分类任务只需少量 token
        }

        resp = requests.post(
            f"{self.config.base_url}/chat/completions",
            json=payload,
            timeout=self.config.timeout,
        )
        resp.raise_for_status()

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            return ""

        return choices[0].get("message", {}).get("content", "").strip()
